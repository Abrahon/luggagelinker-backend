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






    # ... previous methods (verify_and_execute_pickup, execute_start_transit) ...

    @classmethod
    def verify_and_execute_delivery(cls, booking: Booking) -> Booking:
        """
        Executes atomic business transitions for final destination drop-offs.
        Updates state, stamps delivery timing, automatically captures and releases 
        escrow funds via Stripe, and completes the entire booking contract.
        """
        with transaction.atomic():
            # 1. Acquire exclusive row locks across the booking and its related payment ledger
            booking = Booking.objects.select_for_update().get(id=booking.id)
            
            try:
                payment = BookingPayment.objects.select_for_update().get(booking=booking)
            except BookingPayment.DoesNotExist:
                raise DjangoValidationError("No active escrow payment ledger found for this booking context.")

            # 2. Update Delivery Verification Parameters
            booking.status = BookingStatus.DELIVERED
            booking.delivered_at = timezone.now()
            booking.save(update_fields=["status", "delivered_at"])

            # 3. 🟢 AUTOMATICALLY RELEASE PAYMENT & DISBURSE EARNINGS
            # This handles third-party API integration and changes payment status to CAPTURED
            BookingPaymentService.release(payment)

            # 4. Finalize state machine directly to COMPLETED since finances are settled
            booking.status = BookingStatus.COMPLETED
            booking.save(update_fields=["status"])

            # 5. Dispatch Simultaneous Notifications
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

            logger.info(f"Booking {booking.id} and Payment {payment.id} successfully auto-finalized and COMPLETED.")
            return booking