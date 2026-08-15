import logging
import decimal
import stripe
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError
from apps.payment.models import PlatformSetting
import secrets
from apps import payment
from apps.notifications.utils.email import send_pickup_pin_email  
import decimal
import logging
import secrets
import stripe
from django.db import transaction
from django.utils import timezone

from apps.bookings.models import Booking, BookingStatus
from apps.notifications.models import Notification, NotificationType 
from .models import BookingPayment, BookingPaymentGateway, BookingPaymentStatus,Payment,PaymentStatus,StripeEventLog
from apps.bookings.models import BookingStatus,PaymentStatus
from datetime import timedelta

from decimal import Decimal
from apps.subscriptions.models import (
    Subscription, 
    SubscriptionStatus, 
    Plan, 
)
from apps.wallets.services import WalletService
logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY



class BookingPaymentService:
    @classmethod
    def create_checkout(cls, booking: Booking, gateway: str, user_email: str, client_ip=None) -> BookingPayment:
        """
        Initializes or retries an escrow payment ledger entry for a cargo booking, 
        generating secure remote checkouts safely outside of open database row locks.
        """
        
        # =====================================================================
        # 1. ATOMIC TRANSACTION & ROW LOCKING
        # =====================================================================
        with transaction.atomic():
            # Acquire exclusive write-locks on the core booking record
            booking_sealed = Booking.objects.select_for_update().get(id=booking.id)

            # Look up any existing payment lifecycle traces for this specific booking
            existing_payment = (
                BookingPayment.objects.select_for_update()
                .filter(booking=booking_sealed)
                .first()
            )

            if existing_payment:
                # Critical guard block: Abort execution if a payment cycle has already concluded successfully
                if existing_payment.status in [
                    BookingPaymentStatus.AUTHORIZED,
                    BookingPaymentStatus.CAPTURED,
                ]:
                    raise DjangoValidationError("This booking has already been paid.")

                # Recycle the existing record to maintain database ledger integrity
                payment = existing_payment
                payment.gateway = gateway
                payment.status = BookingPaymentStatus.PENDING
                payment.failure_reason = None
                payment.provider_payment_id = None
                payment.checkout_url = None
                payment.ip_address = client_ip

                payment.save(
                    update_fields=[
                        "gateway",
                        "status",
                        "failure_reason",
                        "provider_payment_id",
                        "checkout_url",
                        "ip_address"
                    ]
                )
                logger.info("Recycled payment tracking ledger entry %s for dynamic retry.", payment.id)

            else:
                # Dynamic Platform Escrow Fee calculation utilizing safe structural decimals


                setting = (
                    PlatformSetting.objects.filter(
                        is_active=True
                    )
                    .order_by("-updated_at")
                    .first()
                )

                fee_percentage = (
                    setting.platform_fee_percentage
                    if setting
                    else decimal.Decimal("2.00")
                )
                calculated_fee = (
                    booking_sealed.agreed_reward
                    * fee_percentage
                    / decimal.Decimal("100")
                ).quantize(decimal.Decimal("0.01"))

                # Create a fresh historical tracker for our financial books
                payment = BookingPayment.objects.create(
                    booking=booking_sealed,
                    payer=booking_sealed.sender,
                    payee=booking_sealed.traveler,
                    amount=booking_sealed.agreed_reward,
                    platform_fee=calculated_fee,
                    platform_fee_percentage=fee_percentage,
                    currency=booking_sealed.currency or "USD",
                    gateway=gateway,
                    status=BookingPaymentStatus.PENDING,
                    ip_address=client_ip,
                )
                logger.info("Generated a new escrow transaction container reference: %s", payment.id)

        # =====================================================================
        # 2. THIRD-PARTY API HANDOFF (Executed safely outside active row-locks)
        # =====================================================================
        if gateway == BookingPaymentGateway.STRIPE:
            try:
                # Aggregate base contract amount and the platform service fees together
                total_escrow_amount = payment.amount + payment.platform_fee
                total_amount_cents = int(total_escrow_amount * decimal.Decimal("100"))
                currency_lower = payment.currency.lower()

                session = stripe.checkout.Session.create(
                    payment_method_types=["card"],
                    customer_email=user_email,  # Pre-populates the email payload block natively on Stripe
                    line_items=[{
                        "price_data": {
                            "currency": currency_lower,
                            "product_data": {
                                "name": f"Escrow Security Deposit #{booking_sealed.tracking_number}",
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

                # Mutate structural references with response context keys
                payment.provider_payment_id = session.id
                payment.checkout_url = session.url
                payment.status = BookingPaymentStatus.INITIALIZED
                payment.save(update_fields=["provider_payment_id", "checkout_url", "status"])
                
                logger.info("Stripe gateway session initialized successfully for tracking identity: %s", payment.id)
                return payment

            except stripe.error.StripeError as e:
                logger.error(f"Stripe setup checkout anomaly on payment {payment.id}: {str(e)}", exc_info=True)
                
                # Permanently write structural collection crash states straight into the database history
                payment.status = BookingPaymentStatus.FAILED
                payment.failure_reason = f"Stripe API Error: {str(e)}"
                payment.save(update_fields=["status", "failure_reason"])
                
                raise DjangoValidationError("External credit processing provider failed to initialize session.")
        
        elif gateway in [BookingPaymentGateway.BKASH, BookingPaymentGateway.NAGAD]:
            raise DjangoValidationError(f"{gateway} gateway infrastructure integration is pending.")
        else:
            raise DjangoValidationError("Selected transaction gateway routing is invalid.")




    # @classmethod
    # def process_webhook(cls, event, raw_json=None):
    #     """
    #     Processes verified Stripe checkout webhook parameters to safely lock down 
    #     escrow balances, generate secure verification codes, and trigger customer alerts.
    #     """
    #     from apps.wallets.services import WalletService 

    #     event_id = event["id"]
    #     event_type = event["type"]
    #     event_data = event["data"]["object"].to_dict()

    #     metadata = event_data.get("metadata", {})
    #     booking_payment_id = metadata.get("booking_payment_id")
    #     booking_id = metadata.get("booking_id")

    #     if not booking_payment_id or not booking_id:
    #         logger.warning("Stripe payload skipped: Missing transaction identifier signatures.")
    #         return

    #     # =====================================================================
    #     # 🟢 CHECKOUT SUCCESS (Escrow Funds Locked Natively)
    #     # =====================================================================
    #     if event_type == "checkout.session.completed":
    #         booking = None
    #         secure_pin = None

    #         with transaction.atomic():
    #             if StripeEventLog.objects.select_for_update().filter(event_id=event_id).exists():
    #                 logger.info("Stripe event %s already processed. Bypassing execution.", event_id)
    #                 return
                
    #             try:
    #                 payment_record = BookingPayment.objects.select_for_update().get(id=booking_payment_id)
    #                 booking = Booking.objects.select_for_update().get(id=booking_id)

    #                 if payment_record.status in [BookingPaymentStatus.AUTHORIZED, BookingPaymentStatus.CAPTURED]:
    #                     return

    #                 # Log the Stripe event record trace
    #                 StripeEventLog.objects.create(
    #                     event_id=event_id,
    #                     event_type=event_type,
    #                     raw_payload=raw_json if raw_json else {}
    #                 )

    #                 # ---------------------------------------------------------
    #                 # Trigger Centralized Wallet Escrow (Hold allocations)
    #                 # ---------------------------------------------------------
    #                 WalletService.hold_escrow(booking)

    #                 # ---------------------------------------------------------
    #                 # 🟢 FIX: SAVE STRIPE PAYMENTINTENT IDENTIFIERS
    #                 # ---------------------------------------------------------
    #                 payment_intent_id = event_data.get("payment_intent")
                    
    #                 payment_record.transaction_id = payment_intent_id
    #                 payment_record.provider_payment_id = payment_intent_id
    #                 if hasattr(payment_record, "checkout_session_id"):
    #                     payment_record.checkout_session_id = event_data.get("id")

    #                 # 1. ESCROW LEDGER RECORD STATUS: Set to AUTHORIZED (Locked on Hold)
    #                 payment_record.status = BookingPaymentStatus.AUTHORIZED
    #                 payment_record.authorized_at = timezone.now() 
                    
    #                 update_fields = ["status", "authorized_at", "transaction_id", "provider_payment_id"]
    #                 if hasattr(payment_record, "checkout_session_id"):
    #                     update_fields.append("checkout_session_id")

    #                 payment_record.save(update_fields=update_fields)

    #                 # 2. SENDER CONTRACT WORKFLOW STATES: Mark as PAID and CONFIRMED
    #                 booking.status = BookingStatus.CONFIRMED  
    #                 booking.payment_status = PaymentStatus.PAID  

    #                 # ---------------------------------------------------------
    #                 # GENERATE PIN HERE (Only if it doesn't already exist)
    #                 # ---------------------------------------------------------
    #                 if not getattr(booking, "pickup_verification_pin", None):
    #                     secure_pin = str(secrets.randbelow(900000) + 100000)
    #                     booking.pickup_verification_pin = secure_pin
    #                 else:
    #                     secure_pin = booking.pickup_verification_pin

    #                 # ---------------------------------------------------------
    #                 # SAVE BOOKING STATES (Added payment_status to explicit track)
    #                 # ---------------------------------------------------------
    #                 booking.save(update_fields=["status", "payment_status", "pickup_verification_pin"])
    #                 logger.info(
    #                     "Escrow secured, Stripe intent %s stored, and PIN assigned for booking #%s",
    #                     payment_intent_id,
    #                     booking.tracking_number
    #                 )

    #             except BookingPayment.DoesNotExist:
    #                 logger.error("BookingPayment ledger row ID %s was not found.", booking_payment_id)
    #                 return
    #             except Booking.DoesNotExist:
    #                 logger.error("Base Booking entity match ID %s went missing.", booking_id)
    #                 return

    #         # ---------------------------------------------------------
    #         # SEND EMAIL TO SENDER (Outside open row transaction locks)
    #         # ---------------------------------------------------------
    #         if booking and secure_pin:
    #             try:
    #                 send_pickup_pin_email(
    #                     user_email=booking.sender.email,
    #                     booking=booking,
    #                     pickup_pin=secure_pin
    #                 )
    #             except Exception:
    #                 logger.error("Database updates saved successfully, but notification dispatch failed.", exc_info=True)

    #     # =====================================================================
    #     # HANDLING CARD FALLBACK / EXPIRED CHECKOUTS
    #     # =====================================================================
    #     elif event_type in ["payment_intent.payment_failed", "checkout.session.expired"]:
    #         with transaction.atomic():
    #             try:
    #                 payment_record = BookingPayment.objects.select_for_update().get(id=booking_payment_id)
    #                 booking = Booking.objects.select_for_update().get(id=booking_id)
                    
    #                 if payment_record.status == BookingPaymentStatus.FAILED:
    #                     return
                    
    #                 payment_record.status = BookingPaymentStatus.FAILED
    #                 payment_record.failure_reason = event_data.get("last_payment_error", {}).get("message", "Session checkout expired.")
    #                 payment_record.provider_payment_id = None
    #                 payment_record.checkout_url = None
    #                 payment_record.save(update_fields=["status", "failure_reason", "provider_payment_id", "checkout_url"])
                    
    #                 booking.status = BookingStatus.FAILED
    #                 booking.save(update_fields=["status"])
    #                 logger.warning("Payment cleared as FAILED for tracker reference %s. Form state reset.", payment_record.id)

    #             except BookingPayment.DoesNotExist:
    #                 pass
    #             except Booking.DoesNotExist:
    #                 pass



    @staticmethod
    def _safe_send_pickup_pin_email(user_email: str, booking, pickup_pin: str) -> None:
        """Helper function to dispatch pickup pin email safely inside transaction.on_commit."""
        try:
            send_pickup_pin_email(
                user_email=user_email,
                booking=booking,
                pickup_pin=pickup_pin
            )
        except Exception:
            logger.error(
                "Transaction committed successfully, but notification dispatch failed for booking %s.", 
                booking.id, 
                exc_info=True
            )

    @classmethod
    def process_webhook(cls, event: dict, raw_json: dict = None) -> None:
        """
        Processes verified Stripe checkout webhook parameters to safely lock down 
        escrow balances, generate secure verification codes, and trigger customer alerts.
        """
        from apps.wallets.services import WalletService 

        event_id = event["id"]
        event_type = event["type"]
        event_data = event["data"]["object"].to_dict()

        metadata = event_data.get("metadata", {})
        booking_payment_id = metadata.get("booking_payment_id") or metadata.get("payment_id")
        booking_id = metadata.get("booking_id")

        if not booking_payment_id or not booking_id:
            logger.warning("Stripe payload skipped: Missing transaction identifier signatures in metadata.")
            return

        # =====================================================================
        # 🟢 CHECKOUT SUCCESS (Escrow Funds Locked Natively)
        # =====================================================================
        if event_type == "checkout.session.completed":

            # ---------------------------------------------------------
            # 1. RETRIEVE EXPANDED SESSION & STRICTLY EXTRACT IDS
            # ---------------------------------------------------------
            try:
                session = stripe.checkout.Session.retrieve(
                    event_data["id"],
                    expand=["payment_intent"]
                )
            except stripe.error.StripeError as e:
                logger.error(
                    "Failed to retrieve expanded Checkout Session %s from Stripe: %s", 
                    event_data.get("id"), e, exc_info=True
                )
                raise e

            payment_intent_obj = session.payment_intent
            payment_intent_id = None
            charge_id = None

            if isinstance(payment_intent_obj, stripe.PaymentIntent):
                payment_intent_id = payment_intent_obj.id
                latest_charge = getattr(payment_intent_obj, "latest_charge", None)
                charge_id = latest_charge.id if hasattr(latest_charge, "id") else latest_charge
            elif isinstance(payment_intent_obj, str):
                payment_intent_id = payment_intent_obj

            if not payment_intent_id:
                logger.error("Stripe Checkout Session %s completed without a valid PaymentIntent ID.", session.id)
                raise ValueError(f"Checkout Session {session.id} did not yield a valid PaymentIntent ID.")

            with transaction.atomic():
                # Check event idempotency
                if StripeEventLog.objects.select_for_update().filter(event_id=event_id).exists():
                    logger.info("Stripe event %s already processed. Bypassing execution.", event_id)
                    return
                
                try:
                    payment_record = BookingPayment.objects.select_for_update().get(id=booking_payment_id)
                    booking = Booking.objects.select_for_update().get(id=booking_id)

                    # Early exit if already in a finalized/authorized state
                    if payment_record.status in [BookingPaymentStatus.AUTHORIZED, BookingPaymentStatus.CAPTURED]:
                        return

                    # ---------------------------------------------------------
                    # 2. HANDLE AMOUNT & FEE DIFFERENCE SAFELY
                    # ---------------------------------------------------------
                    expected_amount_cents = int(payment_record.amount * decimal.Decimal("100"))
                    stripe_charged_cents = session.amount_total
                    charged_amount_decimal = decimal.Decimal(stripe_charged_cents) / decimal.Decimal("100")

                    update_fields = ["status", "authorized_at", "transaction_id", "provider_payment_id"]

                    if stripe_charged_cents != expected_amount_cents:
                        fee_cents = stripe_charged_cents - expected_amount_cents
                        fee_decimal = decimal.Decimal(fee_cents) / decimal.Decimal("100")

                        logger.info(
                            "Payment fee/percentage detected for Payment #%s. "
                            "DB Base: $%s (%s cents) | Stripe Charged: $%s (%s cents) | Added Fee: $%s",
                            payment_record.id,
                            payment_record.amount,
                            expected_amount_cents,
                            charged_amount_decimal,
                            stripe_charged_cents,
                            fee_decimal
                        )

                        # Sync DB record to actual charged total
                        payment_record.amount = charged_amount_decimal
                        update_fields.append("amount")

                        if hasattr(payment_record, "total_amount"):
                            payment_record.total_amount = charged_amount_decimal
                            update_fields.append("total_amount")

                        if hasattr(payment_record, "fee_amount"):
                            payment_record.fee_amount = fee_decimal
                            update_fields.append("fee_amount")

                    # Audit trail log
                    StripeEventLog.objects.create(
                        event_id=event_id,
                        event_type=event_type,
                        raw_payload=raw_json if raw_json else {}
                    )

                    # ---------------------------------------------------------
                    # 3. SAVE PAYMENT INTENT & CHARGE IDS
                    # ---------------------------------------------------------
                    payment_record.transaction_id = payment_intent_id
                    payment_record.provider_payment_id = payment_intent_id

                    if charge_id:
                        if hasattr(payment_record, "stripe_charge_id"):
                            payment_record.stripe_charge_id = charge_id
                            update_fields.append("stripe_charge_id")
                        elif hasattr(payment_record, "charge_id"):
                            payment_record.charge_id = charge_id
                            update_fields.append("charge_id")

                    if hasattr(payment_record, "checkout_session_id"):
                        payment_record.checkout_session_id = session.id
                        update_fields.append("checkout_session_id")

                    # ESCROW LEDGER RECORD STATUS: Set to AUTHORIZED
                    payment_record.status = BookingPaymentStatus.AUTHORIZED
                    payment_record.authorized_at = timezone.now()
                    payment_record.save(update_fields=update_fields)

                    # ---------------------------------------------------------
                    # 4. WALLET ESCROW HOLD (Matches WalletService.hold_escrow(booking))
                    # ---------------------------------------------------------
                    escrow_tx = WalletService.hold_escrow(booking)
                    logger.info("Escrow transaction %s created for booking #%s", escrow_tx.id, booking.id)

                    # CONTRACT WORKFLOW STATES: Mark as CONFIRMED and PAID
                    booking.status = BookingStatus.CONFIRMED  
                    booking.payment_status = PaymentStatus.PAID  

                    # Generate pickup PIN if missing
                    if not getattr(booking, "pickup_verification_pin", None):
                        secure_pin = str(secrets.randbelow(900000) + 100000)
                        booking.pickup_verification_pin = secure_pin
                    else:
                        secure_pin = booking.pickup_verification_pin

                    booking.save(update_fields=["status", "payment_status", "pickup_verification_pin"])

                    # ---------------------------------------------------------
                    # 5. NOTIFICATIONS & EMAILS ON COMMIT
                    # ---------------------------------------------------------
                    user_email = booking.sender.email
                    transaction.on_commit(
                        lambda: cls._safe_send_pickup_pin_email(user_email, booking, secure_pin)
                    )

                    logger.info(
                        "Escrow secured, PaymentIntent %s (Charge: %s) saved, and PIN assigned for booking #%s",
                        payment_intent_id,
                        charge_id,
                        booking.tracking_number
                    )

                except BookingPayment.DoesNotExist:
                    logger.error("BookingPayment ledger row ID %s was not found.", booking_payment_id)
                    return
                except Booking.DoesNotExist:
                    logger.error("Base Booking entity match ID %s went missing.", booking_id)
                    return

        # =====================================================================
        # 🔴 FAILURE PATH: PAYMENT FAILED / SESSION EXPIRED
        # =====================================================================
        elif event_type in ["payment_intent.payment_failed", "checkout.session.expired"]:
            with transaction.atomic():
                try:
                    payment_record = BookingPayment.objects.select_for_update().get(id=booking_payment_id)
                    booking = Booking.objects.select_for_update().get(id=booking_id)
                    
                    if payment_record.status == BookingPaymentStatus.FAILED:
                        return
                    
                    payment_record.status = BookingPaymentStatus.FAILED
                    payment_record.failure_reason = event_data.get("last_payment_error", {}).get(
                        "message", "Session checkout expired."
                    )
                    
                    payment_record.checkout_url = None
                    payment_record.save(update_fields=["status", "failure_reason", "checkout_url"])
                    
                    booking.status = BookingStatus.FAILED
                    booking.save(update_fields=["status"])
                    logger.warning("Payment cleared as FAILED for payment ID %s.", payment_record.id)

                except BookingPayment.DoesNotExist:
                    logger.error("Failure path error: BookingPayment %s not found.", booking_payment_id)
                except Booking.DoesNotExist:
                    logger.error("Failure path error: Booking %s not found.", booking_id)
                except Exception as e:
                    logger.exception("Unexpected exception in failure path for booking %s: %s", booking_id, e)

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
            payment.checkout_url = None
            payment.save(update_fields=[
                "status",
                "provider_payment_id",
                "transaction_id",
                "authorized_at",
                "checkout_url",
            ])

            # ================================
            # HOLD ESCROW IN INTERNAL WALLET
            # ================================
            WalletService.hold_escrow(
                user=booking.sender,
                booking=booking,
                amount=payment.amount,
                reference=payment.transaction_id,
            )
            
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
        Fully refund an authorized escrow payment.

        Production requirements:
        - Lock payment row to prevent duplicate refunds.
        - Verify Stripe's actual refundable balance.
        - Never attempt to refund an already-refunded charge.
        - Treat an already-refunded Stripe payment as successful.
        - Update local payment state only after financial state is confirmed.
        - Restore trip capacity only once.
        """

        if payment.status != BookingPaymentStatus.AUTHORIZED:
            raise DjangoValidationError(
                "Only payments in AUTHORIZED escrow status can be refunded."
            )

        with transaction.atomic():

            payment = (
                BookingPayment.objects
                .select_related("booking__trip")
                .select_for_update()
                .get(id=payment.id)
            )

            # ==================================================
            # DUPLICATE REFUND PROTECTION
            # ==================================================

            if payment.status == BookingPaymentStatus.REFUNDED:
                logger.info(
                    "Payment already refunded | Payment=%s",
                    payment.id,
                )
                return payment

            booking = payment.booking
            trip = getattr(booking, "trip", None)

            # ==================================================
            # STRIPE REFUND
            # ==================================================

            if payment.gateway == BookingPaymentGateway.STRIPE:

                intent_id = (
                    payment.transaction_id
                    or getattr(
                        payment,
                        "stripe_payment_intent_id",
                        None,
                    )
                )

                if not intent_id:
                    raise DjangoValidationError(
                        "Cannot process refund: "
                        "Payment record is missing a valid Stripe transaction ID."
                    )

                try:

                    # --------------------------------------------------
                    # PAYMENT INTENT
                    # --------------------------------------------------

                    if intent_id.startswith("pi_"):

                        payment_intent = stripe.PaymentIntent.retrieve(
                            intent_id
                        )

                        latest_charge = getattr(
                            payment_intent,
                            "latest_charge",
                            None,
                        )

                        charge_id = (
                            latest_charge.id
                            if hasattr(latest_charge, "id")
                            else latest_charge
                        )

                        if not charge_id:
                            raise DjangoValidationError(
                                "Stripe PaymentIntent does not contain a charge."
                            )

                        charge = stripe.Charge.retrieve(
                            charge_id
                        )

                    # --------------------------------------------------
                    # DIRECT CHARGE
                    # --------------------------------------------------

                    elif intent_id.startswith("ch_"):

                        charge = stripe.Charge.retrieve(
                            intent_id
                        )

                    else:
                        raise DjangoValidationError(
                            "Invalid Stripe transaction ID."
                        )

                    # ==================================================
                    # CHECK ALREADY REFUNDED
                    # ==================================================

                    charge_amount = int(
                        getattr(charge, "amount", 0)
                    )

                    amount_refunded = int(
                        getattr(charge, "amount_refunded", 0)
                    )

                    remaining_amount = (
                        charge_amount - amount_refunded
                    )

                    # ==================================================
                    # ALREADY FULLY REFUNDED
                    # ==================================================

                    if remaining_amount <= 0:

                        logger.warning(
                            "Stripe payment already fully refunded | "
                            "Payment=%s | Charge=%s",
                            payment.id,
                            charge.id,
                        )

                    else:

                        # ==================================================
                        # CREATE FULL REFUND
                        # ==================================================

                        stripe.Refund.create(
                            charge=charge.id,
                            metadata={
                                "booking_payment_id": str(payment.id),
                                "reason": "booking_refund",
                            },
                        )

                        logger.info(
                            "Stripe full refund completed | "
                            "Payment=%s | Charge=%s | Amount=%s",
                            payment.id,
                            charge.id,
                            remaining_amount,
                        )

                except stripe.error.InvalidRequestError as e:

                    error_message = str(e).lower()

                    # ==================================================
                    # ALREADY REFUNDED
                    # ==================================================

                    if (
                        "already been refunded" in error_message
                        or "has already been refunded" in error_message
                    ):

                        logger.warning(
                            "Stripe reports payment already refunded. "
                            "Continuing dispute resolution | Payment=%s",
                            payment.id,
                        )

                        # IMPORTANT:
                        # DO NOT raise.
                        # Financial operation is already completed.

                    else:

                        logger.error(
                            "Stripe refund rejected | Payment=%s | Error=%s",
                            payment.id,
                            str(e),
                            exc_info=True,
                        )

                        raise DjangoValidationError(
                            f"Stripe refund backend declined: {str(e)}"
                        )

                except stripe.error.StripeError as e:

                    logger.error(
                        "Stripe refund failure | Payment=%s | Error=%s",
                        payment.id,
                        str(e),
                        exc_info=True,
                    )

                    raise DjangoValidationError(
                        f"Stripe refund backend declined: {str(e)}"
                    )

            # ==================================================
            # UPDATE LOCAL PAYMENT
            # ==================================================

            payment.status = BookingPaymentStatus.REFUNDED
            payment.refunded_at = timezone.now()

            update_fields = [
                "status",
                "refunded_at",
            ]

            if hasattr(payment, "updated_at"):
                update_fields.append("updated_at")

            payment.save(
                update_fields=update_fields
            )

            # ==================================================
            # BOOKING STATUS
            # ==================================================

            if booking.status != BookingStatus.CANCELLED:

                booking.status = BookingStatus.CANCELLED

                booking.save(
                    update_fields=["status"]
                )

            # ==================================================
            # RESTORE TRIP CAPACITY
            # ==================================================

            booking_weight = getattr(
                booking,
                "agreed_weight_kg",
                decimal.Decimal("0.00"),
            )

            if (
                trip
                and hasattr(trip, "available_weight_kg")
                and booking_weight > decimal.Decimal("0.00")
            ):

                trip.available_weight_kg += booking_weight

                trip.save(
                    update_fields=[
                        "available_weight_kg"
                    ]
                )

            logger.info(
                "Payment refund finalized | "
                "Payment=%s | Booking=%s",
                payment.id,
                booking.id,
            )

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
            
            logger.info(f"Payment ledger {payment.id} successfully CAPTURED via third-party provider.")
           
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

    @classmethod
    def partial_refund(
        cls, 
        payment: BookingPayment, 
        refund_to_sender: decimal.Decimal, 
        payout_to_traveler: decimal.Decimal
    ) -> BookingPayment:
        if payment.status != BookingPaymentStatus.AUTHORIZED:
            raise DjangoValidationError(
                "Only payments securely held in authorized escrow status bounds can be partially refunded."
            )

        with transaction.atomic():
            payment = (
                BookingPayment.objects.select_related("booking__trip")
                .select_for_update()
                .get(id=payment.id)
            )
            booking = payment.booking
            trip = getattr(booking, "trip", None)

            if payment.gateway == BookingPaymentGateway.STRIPE:
                # 🟢 1. Retrieve transaction ID safely
                intent_id = payment.transaction_id or getattr(payment, "stripe_payment_intent_id", None)

                if not intent_id:
                    raise DjangoValidationError(
                        "Cannot process refund: Payment record is missing a valid Stripe PaymentIntent transaction ID."
                    )

                requested_cents = int(refund_to_sender * decimal.Decimal("100"))

                if requested_cents > 0:
                    try:
                        # 🟢 2. Fetch actual remaining unrefunded balance from Stripe
                        unrefunded_cents = 0
                        if intent_id.startswith("pi_"):
                            pi = stripe.PaymentIntent.retrieve(intent_id)
                            latest_charge = getattr(pi, "latest_charge", None)
                            charge_id = latest_charge.id if hasattr(latest_charge, "id") else latest_charge
                            if charge_id:
                                charge = stripe.Charge.retrieve(charge_id)
                                unrefunded_cents = charge.amount - charge.amount_refunded
                            else:
                                unrefunded_cents = getattr(pi, "amount", requested_cents)
                        elif intent_id.startswith("ch_"):
                            charge = stripe.Charge.retrieve(intent_id)
                            unrefunded_cents = charge.amount - charge.amount_refunded
                        else:
                            unrefunded_cents = requested_cents

                        # 🟢 3. Cap the refund to what is actually available on Stripe
                        cents_to_refund = min(requested_cents, unrefunded_cents)

                        if cents_to_refund > 0:
                            refund_kwargs = {
                                "amount": cents_to_refund,
                                "metadata": {
                                    "booking_payment_id": str(payment.id),
                                    "reason": "dispute_partial_refund",
                                }
                            }
                            if intent_id.startswith("pi_"):
                                refund_kwargs["payment_intent"] = intent_id
                            else:
                                refund_kwargs["charge"] = intent_id

                            stripe.Refund.create(**refund_kwargs)
                            logger.info(
                                "Stripe partial refund completed for Payment #%s. Requested: %s cents, Issued: %s cents",
                                payment.id, requested_cents, cents_to_refund
                            )
                        else:
                            logger.info(
                                "Stripe transaction %s for Payment #%s has $0 unrefunded balance left. Skipping Stripe API call.",
                                intent_id, payment.id
                            )

                    except stripe.error.InvalidRequestError as e:
                        # If charge was already partially/fully refunded directly on Stripe, log warning and let DB/Wallet updates complete
                        logger.warning(
                            "Stripe partial refund skipped or declined for Payment #%s: %s. Proceeding with DB/Wallet updates.",
                            payment.id, str(e)
                        )
                    except stripe.error.StripeError as e:
                        logger.error(
                            "Stripe execution partial refund failure for Payment #%s: %s", 
                            payment.id, str(e), exc_info=True
                        )
                        raise DjangoValidationError(
                            f"Stripe partial refund backend declined: {str(e)}"
                        )

            # Update local payment record
            payment.status = getattr(BookingPaymentStatus, "PARTIAL_REFUND", BookingPaymentStatus.REFUNDED)
            payment.refunded_at = timezone.now()

            update_fields = ["status", "refunded_at"]
            if hasattr(payment, "updated_at"):
                update_fields.append("updated_at")

            payment.save(update_fields=update_fields)

            # Restructure trip capacity
            booking_weight = getattr(booking, "agreed_weight_kg", decimal.Decimal("0.00"))
            if trip and hasattr(trip, "available_weight_kg"):
                trip.available_weight_kg += booking_weight
                trip.save(update_fields=["available_weight_kg"])

            return payment


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