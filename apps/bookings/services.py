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
            agreed_reward=package.reward,
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

    # 🟢 FIXED: Adjusted indentation to place method inside the class block
    @staticmethod
    @transaction.atomic
    def respond_to_booking_request(booking_id, traveler, action):
        """
        Processes a traveler's response to an initialized pending booking request.
        """
        # Lock the row using select_for_update to prevent race conditions during weight manipulation
        try:
            booking = Booking.objects.select_for_update().select_related("trip", "package").get(
                id=booking_id, 
                traveler=traveler, 
                status=BookingStatus.PENDING
            )
        except Booking.DoesNotExist:
            # 🟢 FIXED: Removed invalid 'booking.status' modification which triggered a NameError
            raise ValidationError("Booking request not found, already processed, or expired.")

        # Check if the 20-minute window has closed
        if timezone.now() > booking.expires_at:
            booking.status = BookingStatus.EXPIRED
            booking.save()
            raise ValidationError("This booking request has expired.")

        trip = booking.trip

        if action == "ACCEPT":
            # Re-verify weight inventory capacity under transaction lock
            if trip.available_weight_kg < booking.agreed_weight_kg:
                raise ValidationError("You no longer have enough available weight capacity on your trip to accept this package.")

            # Deduct capacity from the traveler's trip allocation ledger
            trip.available_weight_kg -= booking.agreed_weight_kg
            trip.save()

            # Advance state variables
            booking.status = BookingStatus.PAYMENT_PENDING
            booking.traveler_accepted_at = timezone.now()
            booking.save()
            
            logger.info(f"Booking {booking.tracking_number} accepted by traveler. Awaiting sender payment.")
            # TODO: NotificationService.send_payment_required_notification(booking)

        elif action == "REJECT":
            booking.status = BookingStatus.REJECTED
            booking.save()
            
            logger.info(f"Booking {booking.tracking_number} rejected by traveler.")
            # TODO: NotificationService.send_booking_rejected_notification(booking)

        return booking