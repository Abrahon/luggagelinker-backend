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
from apps.wallets.models import WalletTransaction


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
    def verify_and_execute_delivery(cls, booking_or_id) -> Booking:

        from django.db import transaction
        from django.utils import timezone
        from rest_framework.exceptions import ValidationError
        from apps.wallets.models import WalletTransaction
        from apps.wallets.services import WalletService
        from apps.bookings.models import BookingStatus # Ensure this is imported

        with transaction.atomic():
            
            # 🟢 FIXED: Extract UUID cleanly if instance object is passed
            if isinstance(booking_or_id, Booking):
                booking_id = booking_or_id.id
            else:
                booking_id = booking_or_id

            booking = Booking.objects.select_for_update().get(id=booking_id)

            # 1. Prevent double execution
            if booking.status == BookingStatus.COMPLETED:
                raise ValidationError("This delivery is already completed.")

            # 2. 🟢 MODIFIED: Accept validation directly from the IN_TRANSIT workflow status state
            if booking.status != BookingStatus.IN_TRANSIT:
                raise ValidationError(
                    f"Booking is not in a valid state for delivery confirmation. "
                    f"Current status is: {booking.status}"
                )

            # 3. Ensure escrow exists
            # 3. Ensure escrow exists
            escrow_exists = WalletTransaction.objects.filter(
                booking=booking,
                type="ESCROW_HOLD",
                status="PENDING"
            ).exists()

            if not escrow_exists:
                raise ValidationError("No escrow found for this booking.")

            # 4. Release escrow to traveler
            WalletService.release_escrow_to_traveler(booking)

            # 5. 🟢 MODIFIED: Update both delivery and completion timestamps at the same time
            booking.status = BookingStatus.COMPLETED
            booking.delivered_at = timezone.now()  # Marks physical drop-off time
            booking.completed_at = timezone.now()  # Marks wallet settlement time
            
            booking.save(update_fields=["status", "delivered_at", "completed_at"])

            return booking