import logging
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone  # 👈 FIXED: Added missing import

from apps.bookings.models import (
    Booking,
    BookingStatus,
    PaymentStatus,
)
from apps.matching.models import Match
import logging
from apps.bookings.models import Booking, BookingStatus
from apps.notifications.models import Notification, NotificationType
from apps.notifications.utils.email import send_delivery_pin_email,send_pickup_pin_email
import logging
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError

from apps.bookings.models import Booking, BookingStatus
from apps.payment.models import BookingPayment, BookingPaymentStatus
from apps.payment.services import BookingPaymentService
from apps.notifications.models import Notification, NotificationType


logger = logging.getLogger(__name__)


class BookingService:

    @staticmethod
    @transaction.atomic
    def create_booking_request(match_id, initiated_by):
        """
        Create a booking request from a valid match.
        """
        # Fetch match with related objects
        try:
            match = Match.objects.select_related(
                "package",
                "trip",
                "package__sender",
                "trip__traveler",
            ).get(id=match_id)

        except Match.DoesNotExist:
            raise ValidationError("Match does not exist.")

        package = match.package
        trip = match.trip

        # --------------------------------------------------
        # BUSINESS VALIDATIONS
        # --------------------------------------------------

        # Match must be active
        if not match.is_active:
            raise ValidationError("This match is no longer active.")

        # Only sender can create booking
        if initiated_by != package.sender:
            raise ValidationError("Only the package sender can create a booking request.")

        # Prevent duplicate booking
        if Booking.objects.filter(match=match).exists():
            raise ValidationError("A booking already exists for this match.")

        # Capacity check
        if trip.available_weight_kg < package.weight:
            raise ValidationError(
                f"Insufficient available capacity. "
                f"Required: {package.weight}kg, "
                f"Available: {trip.available_weight_kg}kg."
            )

        # Optional: Prevent booking own trip
        if package.sender == trip.traveler:
            raise ValidationError("You cannot book your own trip.")

        # --------------------------------------------------
        # CREATE BOOKING
        # --------------------------------------------------
        booking = Booking.objects.create(
            match=match,
            package=package,
            trip=trip,
            sender=package.sender,
            traveler=trip.traveler,
            agreed_reward=package.reward_amount,
            currency=package.currency,
            status=BookingStatus.PENDING,
            payment_status=PaymentStatus.UNPAID,
        )

        logger.info(
            "Booking %s created by user %s",
            booking.tracking_number,
            initiated_by.id,
        )

        # TODO: NotificationService.send_booking_request(booking)
        return booking









    @staticmethod
    @transaction.atomic
    def respond_to_booking_request(booking_id, traveler, action):
        """
        Traveler accepts or rejects a booking request safely (race-condition proof + idempotent).
        Reverts database changes entirely if email system crashes during validation.
        """
        action = action.upper()

        if action not in ["ACCEPT", "REJECT"]:
            raise ValidationError("Invalid action. Must be ACCEPT or REJECT.")

        # Lock booking row safely
        try:
            booking = Booking.objects.select_for_update().select_related(
                "trip", "package", "sender"
            ).get(
                id=booking_id,
                traveler=traveler
            )
        except Booking.DoesNotExist:
            raise ValidationError("Booking not found or you are not authorized.")

        # =========================
        # IDENTITY / STATE GUARD
        # =========================
        if booking.status != BookingStatus.PENDING:
            raise ValidationError(
                f"This booking cannot be modified. It has already been processed and its status is: {booking.status}"
            )

        # =========================
        # EXPIRY CHECK
        # =========================
        if timezone.now() > booking.expires_at:
            booking.status = BookingStatus.EXPIRED
            booking.save(update_fields=["status"])
            raise ValidationError("This booking request has expired.")

        trip = booking.trip

        # =========================
        # ACCEPT FLOW
        # =========================
        if action == "ACCEPT":
            # capacity check
            if trip.available_weight_kg < booking.agreed_weight_kg:
                raise ValidationError(
                    "Not enough available weight capacity on your trip."
                )

            # ⚓ PRE-VALIDATE EMAIL DISPATCH BEFORE COMMIT
            # If the email code or configuration has an issue, it catches it here,
            # throws a clean error, and rolls back the database state entirely!
            try:
                send_pickup_pin_email(
                    user_email=booking.sender.email,
                    booking=booking,
                    pickup_pin=getattr(booking, "pickup_verification_pin", "0000")
                )
            except Exception as email_err:
                logger.error(f"Critical email system failure. Aborting booking accept sequence: {str(email_err)}")
                raise ValidationError(f"Booking could not be accepted because the notification system failed: {str(email_err)}")

            # Deduct capacity safely since email passed
            trip.available_weight_kg -= booking.agreed_weight_kg
            trip.save(update_fields=["available_weight_kg"])

            # Commit booking state variables change
            booking.status = BookingStatus.PAYMENT_PENDING
            booking.traveler_accepted_at = timezone.now()
            booking.save(update_fields=["status", "traveler_accepted_at"])

            logger.info(f"Booking {booking.tracking_number} safely accepted and processed.")

        # =========================
        # REJECT FLOW
        # =========================
        elif action == "REJECT":
            booking.status = BookingStatus.REJECTED
            booking.save(update_fields=["status"])
            logger.info(f"Booking {booking.tracking_number} rejected.")

        return booking



class BookingLifecycleService:

    @classmethod
    def verify_and_execute_pickup(cls, booking: Booking) -> Booking:
        """
        Executes atomic business transitions for package handoffs.
        Updates state, stamps timing, and registers user notifications.
        """
        with transaction.atomic():
            # Re-fetch with a row lock to guarantee absolute concurrency protection
            booking = Booking.objects.select_for_update().get(id=booking.id)
            
            # 🟢 Set status and the requested timestamp
            booking.status = BookingStatus.PICKED_UP
            booking.picked_up_at = timezone.now()
            booking.save(update_fields=["status", "picked_up_at"])

            # 🟢 Dispatch automated notifications from the service layer
            Notification.objects.create(
                user=booking.sender,
                title="Package Handed Over Successfully",
                message=f"Traveler verified the pickup token for order #{booking.tracking_number}. Status updated to PICKED_UP.",
                notification_type=NotificationType.DELIVERY,
                object_id=booking.id,
            )
            Notification.objects.create(
                user=booking.traveler,
                title="Handoff Confirmed",
                message=f"Pickup verified successfully for order #{booking.tracking_number}. You may now begin delivery routing.",
                notification_type=NotificationType.DELIVERY,
                object_id=booking.id,
            )
            send_delivery_pin_email(
                user_email=booking.sender.email, 
                booking=booking,
                delivery_pin=booking.delivery_verification_pin
            )

            logger.info(f"Booking {booking.id} successfully transitioned to PICKED_UP by service orchestration.")
            return booking


    @classmethod
    def execute_start_transit(cls, booking: Booking) -> Booking:
        """
        Executes atomic business transitions for beginning the shipment journey.
        Updates state, stamps timing logs, and registers sender notifications.
        """
        with transaction.atomic():
            # Re-fetch with a row lock to guarantee absolute concurrency protection
            booking = Booking.objects.select_for_update().get(id=booking.id)
            
            # 🟢 Set status and the requested timestamp
            booking.status = BookingStatus.IN_TRANSIT
            booking.in_transit_at = timezone.now()
            booking.save(update_fields=["status", "in_transit_at"])

            # 🟢 Dispatch automated notifications from the service layer
            Notification.objects.create(
                user=booking.sender,
                title="Package In Transit",
                message=f"Your traveler has started their journey! Order #{booking.tracking_number} is now IN_TRANSIT.",
                notification_type=NotificationType.DELIVERY,
                object_id=booking.id,
                action_url=f"/bookings/{booking.id}/"
            )

            logger.info(f"Booking {booking.id} successfully transitioned to IN_TRANSIT by service orchestration.")
            return booking



    @classmethod
    def verify_and_execute_delivery(cls, booking: Booking) -> Booking:
        """
        Orchestrates the entire atomic business transition for final destination drop-offs.
        Controls the sequential lifecycle flow: DELIVERED -> Stripe Capture -> Wallet Release -> COMPLETED.
        """
        # Dynamic import to break circular reference chains cleanly
        from apps.wallets.services import WalletService

        with transaction.atomic():
            # 1. Acquire exclusive database row locks across both primary tables
            booking = Booking.objects.select_for_update().get(id=booking.id)
            
            try:
                payment = BookingPayment.objects.select_for_update().get(booking=booking)
            except BookingPayment.DoesNotExist:
                raise DjangoValidationError("No active escrow payment ledger found for this booking context.")

            # 2. Stage 1: Transition booking state to DELIVERED
            booking.status = BookingStatus.DELIVERED
            booking.delivered_at = timezone.now()
            booking.save(update_fields=["status", "delivered_at"])

            # 3. Stage 2: Capture Stripe funds safely
            BookingPaymentService.release(payment)

            # 4. Stage 3: Internal ledger settlement hook
            # Safely shifts funds from sender's pending vault to traveler's liquid wallet balance
            WalletService.release_escrow_to_traveler(booking)

            # 5. Stage 4: Finalize the booking contract state machine to COMPLETED
            booking.status = BookingStatus.COMPLETED
            booking.save(update_fields=["status"])

            # 6. Stage 5: Dispatch real-time cross-user unified notification events
            Notification.objects.create(
                user=booking.sender,
                title="Delivery Confirmed & Funds Released",
                message=f"Success! Order #{booking.tracking_number} has been delivered and your escrowed reward payment has been securely transferred to the traveler.",
                notification_type=NotificationType.PAYMENT,
                object_id=booking.id,
            )
            Notification.objects.create(
                user=booking.traveler,
                title="Earnings Captured & Disbursed",
                message=f"Drop-off verified! Your reward earnings for order #{booking.tracking_number} have been deposited directly into your wallet balance.",
                notification_type=NotificationType.WALLET,
                object_id=booking.id,
            )

            logger.info(f"Booking {booking.id} has successfully processed all transactional stages to COMPLETED.")
            return booking