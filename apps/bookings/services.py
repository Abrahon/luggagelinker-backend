import logging

from django.db import transaction
from django.core.exceptions import ValidationError

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
            raise ValidationError(
                "This match is no longer active."
            )

        # Only sender can create booking
        if initiated_by != package.sender:
            raise ValidationError(
                "Only the package sender can create a booking request."
            )

        # Prevent duplicate booking
        if Booking.objects.filter(match=match).exists():
            raise ValidationError(
                "A booking already exists for this match."
            )

        # Capacity check
        if trip.available_weight_kg < package.weight:
            raise ValidationError(
                f"Insufficient available capacity. "
                f"Required: {package.weight}kg, "
                f"Available: {trip.available_weight_kg}kg."
            )

        # Optional: Prevent booking own trip
        if package.sender == trip.traveler:
            raise ValidationError(
                "You cannot book your own trip."
            )

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

        # TODO:
        # NotificationService.send_booking_request(booking)

        return booking