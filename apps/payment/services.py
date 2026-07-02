import logging
import decimal
import stripe
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError

# Adjust these imports according to your exact app paths
from apps.bookings.models import Booking, BookingStatus 
from .models import BookingPayment, BookingPaymentGateway, BookingPaymentStatus

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY


class BookingPaymentService:

    @classmethod
    def create_checkout(cls, booking: Booking, gateway: str, client_ip=None) -> BookingPayment:
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

            # 🟢 UPDATED: Transition status to CONFIRMED and save the pickup verification PIN
            booking.status = BookingStatus.CONFIRMED  
            booking.pickup_verification_pin = pickup_pin  # Ensure this field is added to your Booking model
            booking.save(update_fields=["status", "pickup_verification_pin"])
            
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
        Captures the final payment amount, executing payouts directly to the Payee (traveler).
        Leaves booking lifecycle modifications out of this method.
        """
        if payment.status != BookingPaymentStatus.AUTHORIZED:
            raise DjangoValidationError("No authorized escrow holdings found available for capture release.")

        with transaction.atomic():
            payment = BookingPayment.objects.select_for_update().get(id=payment.id)
            
            payment.status = BookingPaymentStatus.CAPTURED
            payment.captured_at = timezone.now()
            payment.save(update_fields=["status", "captured_at"])

            # 🟢 FIX 5: Do not mark the booking COMPLETED in release(); reserve that for after the delivery flow is finished.
            # No code here touches booking.status anymore.
            
            return payment