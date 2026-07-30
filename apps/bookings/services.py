import logging
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone  # 👈 FIXED: Added missing import
from datetime import timedelta
from django.utils import timezone
from apps.bookings.models import (
    Booking,
    BookingStatus,
    PaymentStatus,
)
from apps.matching.models import Match

from apps.bookings.models import Booking, BookingStatus
from apps.notifications.models import Notification, NotificationType
from apps.notifications.utils.email import send_delivery_pin_email,send_pickup_pin_email
from apps.bookings.models import BookingStatus, PaymentStatus
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError as DjangoValidationError
from apps.packages.models import VerificationStatus
from apps.bookings.models import Booking, BookingStatus
from apps.payment.models import BookingPayment, BookingPaymentStatus
from apps.payment.services import BookingPaymentService
from apps.notifications.models import Notification, NotificationType
from apps.wallets.models import WalletTransaction
from apps.notifications.services import create_notification



logger = logging.getLogger(__name__)


class BookingService:

    @staticmethod
    @transaction.atomic
    def create_booking_request(match_id, initiated_by):
        """
        Create a booking request from a valid match.
        """
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

        # Prevent booking own trip
        if package.sender == trip.traveler:
            raise ValidationError("You cannot book your own trip.")

        # 🟢 Mark old expired pending bookings for this match as inactive
        Booking.objects.filter(
            match=match,
            status=BookingStatus.PENDING,
            expires_at__lte=timezone.now()
        ).update(is_active=False, status=BookingStatus.EXPIRED)

        # 🟢 Check ONLY for active, non-expired, valid bookings
        active_booking_exists = Booking.objects.filter(
            match=match,
            is_active=True,
            status__in=[
                BookingStatus.PENDING,
                BookingStatus.TRAVELER_ACCEPTED,
                BookingStatus.PAYMENT_PENDING,
                BookingStatus.CONFIRMED,
                BookingStatus.PICKED_UP,
                BookingStatus.IN_TRANSIT,
            ],
            expires_at__gt=timezone.now(),
        ).exists()

        if active_booking_exists:
            raise ValidationError("An active booking already exists for this match.")

        # Capacity check
        if trip.available_weight_kg < package.weight:
            raise ValidationError(
                f"Insufficient available capacity. "
                f"Required: {package.weight}kg, "
                f"Available: {trip.available_weight_kg}kg."
            )

        # --------------------------------------------------
        # CREATE BOOKING (NO DELETE REQUIRED!)
        # --------------------------------------------------
        booking = Booking.objects.create(
            match=match,
            package=package,
            trip=trip,
            sender=package.sender,
            traveler=trip.traveler,
            agreed_reward=package.reward_amount,
            agreed_weight_kg=package.weight,
            currency=package.currency,
            status=BookingStatus.PENDING,
            payment_status=PaymentStatus.UNPAID,
            is_active=True,
            # Set a clear expiration window (e.g., 7 days or 30 days)
            expires_at=timezone.now() + timedelta(days=7),
        )

        logger.info(
            "Booking %s created by user %s",
            booking.tracking_number,
            initiated_by.id,
        )

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
        Executes atomic business transitions for package pickup.
        """

        with transaction.atomic():

            booking = Booking.objects.select_for_update().get(id=booking.id)

            if booking.status == BookingStatus.PICKED_UP:
                return booking

            if booking.status != BookingStatus.CONFIRMED:
                raise DjangoValidationError(
                    f"Cannot execute pickup from status: {booking.status}"
                )

            booking.status = BookingStatus.PICKED_UP
            booking.picked_up_at = timezone.now()
            booking.save(update_fields=["status", "picked_up_at"])

            create_notification(
                user=booking.sender,
                title="Package Picked Up",
                message=(
                    f"Traveler successfully picked up your package "
                    f"({booking.tracking_number}). "
                    "Delivery is now in progress."
                ),
                notification_type=NotificationType.BOOKING,
                object_id=booking.id,
                action_url=f"/bookings/{booking.id}/",
            )

            create_notification(
                user=booking.traveler,
                title="Pickup Confirmed",
                message=(
                    f"You successfully picked up package "
                    f"{booking.tracking_number}. "
                    "Please deliver it to the destination."
                ),
                notification_type=NotificationType.BOOKING,
                object_id=booking.id,
                action_url=f"/bookings/{booking.id}/",
            )

            send_delivery_pin_email(
                user_email=booking.sender.email,
                booking=booking,
                delivery_pin=booking.delivery_verification_pin,
            )

            logger.info(
                "Booking %s successfully transitioned to PICKED_UP.",
                booking.id,
            )

            return booking

        

    @classmethod
    def refuse_pickup(cls, booking: Booking, reason: str):

        from apps.wallets.services import WalletService

        with transaction.atomic():

            booking = Booking.objects.select_for_update().select_related(
                "package",
                "trip",
                "sender",
                "traveler",
            ).get(id=booking.id)

            if booking.status != BookingStatus.CONFIRMED:
                raise DjangoValidationError(
                    "Only confirmed bookings can be refused."
                )

            package = booking.package

            package.traveler_matches_listing = False
            package.traveler_refusal_reason = reason
            package.verification_status = VerificationStatus.MANUAL_REVIEW

            package.save(
                update_fields=[
                    "traveler_matches_listing",
                    "traveler_refusal_reason",
                    "verification_status",
                ]
            )

            booking.status = BookingStatus.CANCELLED
            booking.save(update_fields=["status"])

            # Restore trip capacity
            booking.trip.available_weight_kg += booking.agreed_weight_kg
            booking.trip.save(update_fields=["available_weight_kg"])

            # Refund sender escrow
            WalletService.refund(booking)

            # Notify sender
            create_notification(
                user=booking.sender,
                title="Pickup Rejected",
                message=(
                    f"The traveler rejected package "
                    f"{booking.tracking_number}.\n\n"
                    f"Reason: {reason}\n\n"
                    "The booking has been cancelled and your escrow has been refunded."
                ),
                notification_type=NotificationType.BOOKING,
                object_id=booking.id,
                action_url=f"/bookings/{booking.id}/",
            )

            # Notify traveler
            create_notification(
                user=booking.traveler,
                title="Pickup Rejected",
                message=(
                    f"You rejected package "
                    f"{booking.tracking_number}.\n\n"
                    "The booking has been cancelled."
                ),
                notification_type=NotificationType.BOOKING,
                object_id=booking.id,
                action_url=f"/bookings/{booking.id}/",
            )

            logger.info(
                "Booking %s cancelled because traveler refused pickup.",
                booking.id,
            )

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
        from apps.wallets.services import WalletService
        from apps.bookings.models import BookingStatus

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

            # 2. Accept validation directly from the IN_TRANSIT workflow status state
            if booking.status != BookingStatus.IN_TRANSIT:
                raise ValidationError(
                    f"Booking is not in a valid state for delivery confirmation. "
                    f"Current status is: {booking.status}"
                )

            # 3 & 4. 🟢 UPDATED: Let your clean central service layer handle escrow validation and payout logic safely
            WalletService.release_escrow(booking)

            # 5. Update both delivery and completion timestamps at the same time
            # booking.payment_status = PaymentStatus.PAID
            booking.status = BookingStatus.COMPLETED
            booking.delivered_at = timezone.now()  
            booking.completed_at = timezone.now()  
            
            booking.save(update_fields=["status", "delivered_at", "completed_at"])

            return booking


    @classmethod
    def cancel_booking(cls, booking_or_id, initiating_user):

        from django.db import transaction
        from rest_framework.exceptions import ValidationError

        from apps.wallets.services import WalletService
        from apps.bookings.models import Booking, BookingStatus
        from apps.matching.models import MatchStatus

        with transaction.atomic():

            # -----------------------------
            # Load Booking
            # -----------------------------
            if isinstance(booking_or_id, Booking):
                booking = Booking.objects.select_for_update().get(
                    id=booking_or_id.id
                )
            else:
                booking = Booking.objects.select_for_update().select_related(
                    "trip",
                    "match",
                    "sender",
                    "traveler",
                ).get(id=booking_or_id)

            # -----------------------------
            # Permission
            # Sender OR Traveler can cancel
            # -----------------------------
            if initiating_user not in [
                booking.sender,
                booking.traveler,
            ]:
                raise ValidationError(
                    "You are not authorized to cancel this booking."
                )

            # -----------------------------
            # Already Finished
            # -----------------------------
            if booking.status == BookingStatus.CANCELLED:
                raise ValidationError(
                    "This booking has already been cancelled."
                )

            if booking.status == BookingStatus.COMPLETED:
                raise ValidationError(
                    "Completed bookings cannot be cancelled."
                )

            # -----------------------------
            # After Pickup → No Cancellation
            # -----------------------------
            if booking.status in [
                BookingStatus.PICKED_UP,
                BookingStatus.IN_TRANSIT,
                BookingStatus.DELIVERED,
            ]:
                raise ValidationError(
                    "This booking cannot be cancelled after pickup. Please open a dispute."
                )

            # =====================================================
            # CASE 1
            # PENDING / PAYMENT_PENDING
            # No escrow exists
            # =====================================================
            if booking.status in [
                BookingStatus.PENDING,
                BookingStatus.PAYMENT_PENDING,
            ]:

                booking.trip.restore_capacity(
                    booking.agreed_weight_kg
                )

                booking.match.status = MatchStatus.AVAILABLE
                booking.match.save(update_fields=["status"])

            # =====================================================
            # CASE 2
            # CONFIRMED
            # Escrow already exists
            # =====================================================
            elif booking.status == BookingStatus.CONFIRMED:

                WalletService.refund(booking)

                booking.trip.restore_capacity(
                    booking.agreed_weight_kg
                )

                booking.match.status = MatchStatus.AVAILABLE
                booking.match.save(update_fields=["status"])

            # -----------------------------
            # Finalize Booking
            # -----------------------------
            booking.status = BookingStatus.CANCELLED
            booking.is_active = False

            booking.save(
                update_fields=[
                    "status",
                    "is_active",
                ]
            )

            return booking