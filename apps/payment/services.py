import logging
import decimal
import stripe
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError

# Adjust these imports according to your exact app paths
from apps.bookings.models import Booking, BookingStatus
from apps.notifications.models import Notification, NotificationType 
from .models import BookingPayment, BookingPaymentGateway, BookingPaymentStatus,Payment,PaymentStatus
from datetime import timedelta
# Replace these import paths with your actual project structure
from apps.subscriptions.models import (
    Subscription, 
    SubscriptionStatus, 
    Plan, 
)

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY


class BookingPaymentService:

    @classmethod
    def create_checkout(cls, booking: Booking, gateway: str, user_email: str, client_ip=None) -> BookingPayment:
        """
        Registers a fresh payment contract record and provisions the gateway session.
        Prevents duplicate entries via atomic database isolation locks.
        """
        #  FIX 2: Strict prevention of duplicate BookingPayment creation at the thread layer
        with transaction.atomic():
            # Acquire a row-level database lock to eliminate concurrent API spam race conditions
            booking_sealed = Booking.objects.select_for_update().get(id=booking.id)
            
            if hasattr(booking_sealed, "booking_payment"):
                existing_payment = booking_sealed.booking_payment
                # If a session already exists and hasn't explicitly failed, reuse it rather than duplicating rows
                if existing_payment.status != BookingPaymentStatus.FAILED:
                    return existing_payment

            #  FIX 1: Platform fee calculation correction (/ 100)
            fee_percentage = getattr(settings, "PLATFORM_FEE_PERCENTAGE", decimal.Decimal("0.00"))
            calculated_fee = ((booking_sealed.agreed_reward * fee_percentage) / decimal.Decimal("100.00")).quantize(decimal.Decimal("0.01"))

            payment = BookingPayment.objects.create(
                booking=booking_sealed,
                payer=booking_sealed.sender,
                payee=booking_sealed.traveler,
                amount=booking_sealed.agreed_reward,
                platform_fee=calculated_fee,
                currency=booking_sealed.currency or "USD",
                gateway=gateway,
                status=BookingPaymentStatus.PENDING,
                ip_address=client_ip,
            )

        # 3Third-Party API calls execute safely outside row locks to avoid connection pool starvation
        if gateway == BookingPaymentGateway.STRIPE:
            try:
                total_amount_cents = int(booking_sealed.agreed_reward * 100)
                currency_lower = booking_sealed.currency.lower() if booking_sealed.currency else "usd"

                session = stripe.checkout.Session.create(
                    payment_method_types=["card"],
                    customer_email=user_email,
                    line_items=[{
                        "price_data": {
                            "currency": currency_lower,
                            "product_data": {
                                "name": f"Escrow Payment for Order #{booking_sealed.tracking_number}",
                                "description": f"Securing escrow collateral for delivery routing.",
                            },
                            "unit_amount": total_amount_cents,
                        },
                        "quantity": 1,
                    }],
                    mode="payment",
                    metadata={
                        "payment_type": "booking",
                        "booking_payment_id": str(payment.id),
                        "booking_id": str(booking_sealed.id)
                    },
                    success_url=f"{settings.FRONTEND_URL}/payments/success?session_id={{CHECKOUT_SESSION_ID}}",
                    cancel_url=f"{settings.FRONTEND_URL}/payments/cancel",
                )

                payment.provider_payment_id = session.id
                payment.checkout_url = session.url
                payment.status = BookingPaymentStatus.INITIALIZED
                payment.save(update_fields=["provider_payment_id", "checkout_url", "status"])
                return payment

            except stripe.error.StripeError as e:
                logger.error(f"Stripe setup checkout anomaly: {str(e)}", exc_info=True)
                cls.mark_failed(payment, reason=f"Stripe API Error: {str(e)}")
                raise DjangoValidationError("External credit processing provider failed to initialize session.")
        
        elif gateway in [BookingPaymentGateway.BKASH, BookingPaymentGateway.NAGAD]:
            raise DjangoValidationError(f"{gateway} gateway infrastructure integration is pending.")
        else:
            raise DjangoValidationError("Selected transaction gateway routing is invalid.")



    @classmethod
    def verify_checkout(cls, payment: BookingPayment, provider_session_id: str, final_transaction_id: str) -> BookingPayment:
        """
        Transition payment ledger into secure Escrow Authorization upon confirmation from webhooks.
        Deducts trip luggage capacity and provisions a secure 6-digit pickup verification PIN.
        """
        import secrets  # Make sure this is imported at the top of your file

        with transaction.atomic():
            # Refresh and lock related records across tables to guarantee numerical accuracy
            payment = BookingPayment.objects.select_related("booking__trip").select_for_update().get(id=payment.id)
            booking = payment.booking
            trip = booking.trip

            # Avoid processing webhooks multiple times
            if payment.status == BookingPaymentStatus.AUTHORIZED:
                return payment

            payment.status = BookingPaymentStatus.AUTHORIZED
            payment.provider_payment_id = provider_session_id
            payment.transaction_id = final_transaction_id
            payment.authorized_at = timezone.now()
            payment.save(update_fields=["status", "provider_payment_id", "transaction_id", "authorized_at"])
            
            # 🟢 UPDATED: Generate a secure, unguessable 6-digit numerical pickup PIN
            pickup_pin = "".join(secrets.choice("0123456789") for _ in range(6))
            delivery_pin = "".join(secrets.choice("0123456789") for _ in range(6))

            # 🟢 UPDATED: Transition status to CONFIRMED and save the pickup verification PIN
            booking.status = BookingStatus.CONFIRMED  
            booking.pickup_verification_pin = pickup_pin  # Ensure this field is added to your Booking model
            booking.delivery_verification_pin = delivery_pin  # Ensure this field is added to your Booking model
            booking.save(update_fields=["status", "pickup_verification_pin", "delivery_verification_pin"])
            
            # Move trip capacity reduction into verify_checkout() after payment succeeds
            booking_weight = getattr(booking, "agreed_weight_kg", decimal.Decimal("0.00"))
            if trip and hasattr(trip, "available_weight_kg"):
                if trip.available_weight_kg < booking_weight:
                    raise DjangoValidationError("Cannot complete settlement: Trip remaining weight capacity exhausted.")
                
                trip.available_weight_kg -= booking_weight
                trip.save(update_fields=["available_weight_kg"])
            
            return payment
        

    @classmethod
    def mark_failed(cls, payment: BookingPayment, reason: str) -> BookingPayment:
        """
        Cleanly transitions state flags to record exceptions without halting thread executions.
        """
        payment.status = BookingPaymentStatus.FAILED
        payment.failure_reason = reason
        payment.save(update_fields=["status", "failure_reason"])
        return payment

    @classmethod
    def refund(cls, payment: BookingPayment) -> BookingPayment:
        """
        Reverses escrow hold, returning collected balances securely back to the original Payer.
        """
        if payment.status != BookingPaymentStatus.AUTHORIZED:
            raise DjangoValidationError("Only payments securely held in authorized escrow status bounds can be refunded.")

        with transaction.atomic():
            payment = BookingPayment.objects.select_related("booking__trip").select_for_update().get(id=payment.id)
            booking = payment.booking
            trip = booking.trip

            if payment.gateway == BookingPaymentGateway.STRIPE:
                try:
                    stripe.Refund.create(payment_intent=payment.transaction_id)
                except stripe.error.StripeError as e:
                    logger.error(f"Stripe execution refund failure: {str(e)}", exc_info=True)
                    raise DjangoValidationError(f"Stripe refund backend declined: {str(e)}")

            payment.status = BookingPaymentStatus.REFUNDED
            payment.refunded_at = timezone.now()
            payment.save(update_fields=["status", "refunded_at"])

            # 🟢 FIX 3: Replaced hardcoded booking status strings with BookingStatus enum
            booking.status = BookingStatus.CANCELLED
            booking.save(update_fields=["status"])
            
            # Return package weight allocation back into the pool since the transaction was abandoned
            booking_weight = getattr(booking, "agreed_weight_kg", decimal.Decimal("0.00"))
            if trip and hasattr(trip, "available_weight_kg"):
                trip.available_weight_kg += booking_weight
                trip.save(update_fields=["available_weight_kg"])

            return payment

    @classmethod
    def release(cls, payment: BookingPayment) -> BookingPayment:
        """
        Executes financial escrow capture while updating the contract ledger states 
        and dispatching transactional notification events.
        """
        with transaction.atomic():
            # ... Your existing third-party Stripe capture API integration logic ...
            
            # 1. Update your local payment tracking ledger row status
            payment.status = BookingPaymentStatus.CAPTURED
            payment.captured_at = timezone.now()
            payment.save(update_fields=["status", "captured_at"])

            # 2. 🟢 MOVE HERE: Update the Booking state directly within the finance service
            booking = payment.booking
            booking.status = BookingStatus.COMPLETED
            booking.save(update_fields=["status"])

            # 3. 🟢 MOVE HERE: Dispatch the real-time cross-user system notifications
            Notification.objects.create(
                user=booking.sender,
                title="Escrow Released Successfully",
                message=f"Payment for order #{booking.tracking_number} has been released to the traveler. Thank you!",
                notification_type=NotificationType.PAYMENT,
                object_id=booking.id,
            )
            Notification.objects.create(
                user=booking.traveler,
                title="Earnings Disbursed",
                message=f"Success! Reward earnings of {payment.amount} {payment.currency} for order #{booking.tracking_number} have been deposited to your balance.",
                notification_type=NotificationType.WALLET,
                object_id=booking.id,
            )

            return payment





from decimal import Decimal


class SubscriptionWebhookService:

    @staticmethod
    def process(event):
        event_type = event["type"]
        data = event["data"]["object"]

        logger.info("Subscription webhook received: %s", event_type)

        # ============================================
        # CHECKOUT SESSION COMPLETED (Initial Purchase)
        # ============================================
        if event_type == "checkout.session.completed":
            metadata = data.get("metadata", {}) or {}

            payment_id = metadata.get("payment_id")
            user_id = metadata.get("user_id")
            plan_id = metadata.get("plan_id")

            if not all([payment_id, user_id, plan_id]):
                logger.warning("Missing subscription session metadata.")
                return

            with transaction.atomic():
                try:
                    payment = Payment.objects.select_for_update().get(id=payment_id)
                except Payment.DoesNotExist:
                    logger.error("Payment ID %s not found for checkout session.", payment_id)
                    return

                if payment.status == PaymentStatus.SUCCEEDED:
                    return

                try:
                    plan = Plan.objects.get(id=plan_id)
                except Plan.DoesNotExist:
                    logger.error("Plan ID %s not found.", plan_id)
                    return

                # 1. Update initial payment ledger
                payment.status = PaymentStatus.SUCCEEDED
                payment.stripe_payment_intent_id = data.get("payment_intent")
                payment.stripe_customer_id = data.get("customer")
                payment.stripe_subscription_id = data.get("subscription")
                payment.stripe_invoice_id = data.get("invoice")  # Captured invoice ID
                payment.paid_at = timezone.now()
                payment.save()

                # 2. Deactivate any existing active subscriptions
                Subscription.objects.filter(
                    user_id=user_id,
                    is_current=True,
                ).update(
                    is_current=False,
                    status=SubscriptionStatus.EXPIRED,
                )

                # 3. Provision new active subscription
                Subscription.objects.create(
                    user_id=user_id,
                    plan=plan,
                    status=SubscriptionStatus.ACTIVE,
                    started_at=timezone.now(),
                    expires_at=timezone.now() + timedelta(days=plan.duration_days),
                    is_current=True,
                    stripe_subscription_id=data.get("subscription")
                )
                logger.info("Successfully provisioned initial subscription for User %s", user_id)

        # ============================================
        # INVOICE PAID (Automated Recurring Renewals)
        # ============================================
        elif event_type == "invoice.paid":
            subscription_id = data.get("subscription")
            stripe_customer_id = data.get("customer")
            
            # Skip checkout invoices since 'checkout.session.completed' handles them
            if data.get("billing_reason") == "subscription_create":
                logger.info("Skipping invoice.paid for initial creation step.")
                return

            with transaction.atomic():
                try:
                    subscription = Subscription.objects.select_for_update().get(
                        stripe_subscription_id=subscription_id,
                        is_current=True
                    )
                except Subscription.DoesNotExist:
                    logger.error("Subscription %s not found for renewal invoice.", subscription_id)
                    return

                # 1. Safe monetary value tracking using Decimal
                amount_paid = Decimal(data.get("amount_paid", 0)) / Decimal("100")

                # 2. Log a completely new ledger item tracking renewal history
                Payment.objects.create(
                    user_id=subscription.user_id,
                    plan=subscription.plan,
                    amount=amount_paid,
                    status=PaymentStatus.SUCCEEDED,
                    stripe_customer_id=stripe_customer_id,
                    stripe_subscription_id=subscription_id,
                    stripe_payment_intent_id=data.get("payment_intent"),  # Captured payment intent
                    stripe_invoice_id=data.get("id"),                     # Captured invoice ID
                    paid_at=timezone.now()
                )

                # 3. Extend expiration cleanly from their current end date—not from now
                subscription.status = SubscriptionStatus.ACTIVE
                subscription.expires_at = subscription.expires_at + timedelta(days=subscription.plan.duration_days)
                subscription.save()
                
                logger.info("Successfully processed recurring invoice renewal for sub: %s", subscription_id)

        # ============================================
        # INVOICE PAYMENT FAILED (Card Declined / Lapsed)
        # ============================================
        elif event_type == "invoice.payment_failed":
            subscription_id = data.get("subscription")

            with transaction.atomic():
                try:
                    subscription = Subscription.objects.select_for_update().get(
                        stripe_subscription_id=subscription_id,
                        is_current=True
                    )
                except Subscription.DoesNotExist:
                    logger.warning("No active subscription found for broken invoice hook: %s", subscription_id)
                    return

                # 1. Gracefully transition subscription state
                subscription.status = SubscriptionStatus.PAST_DUE
                subscription.save()

                # 2. Format failed amount cleanly using Decimal
                amount_due = Decimal(data.get("amount_due", 0)) / Decimal("100")

                # 3. Create a failed payment ledger item to retain historical paper trail
                Payment.objects.create(
                    user_id=subscription.user_id,
                    plan=subscription.plan,
                    amount=amount_due,
                    status=PaymentStatus.FAILED,
                    stripe_subscription_id=subscription_id,
                    stripe_customer_id=data.get("customer"),
                    stripe_invoice_id=data.get("id"),
                    failure_reason="Stripe recurring payment failed."
                )
                logger.warning("Subscription invoice collection failed logged in ledger for ID: %s", subscription_id)

        else:
            logger.info("Ignoring subscription event: %s", event_type)