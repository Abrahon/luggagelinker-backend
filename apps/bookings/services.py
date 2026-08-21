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
from apps.trips.services import TripStatusService
from apps.trips.models import Trip, TripStatus
from apps.matching.models import Match
from apps.packages.models import PackageStatus
from apps.trips.models import Trip
from apps.packages.models import PackageStatus,Package
from apps.packages.services import PackageService

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
from apps.chat.services import ChatService

from apps.notifications.services import (
    create_booking_request_notification,
)

from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from apps.matching.models import MatchStatus

from apps.matching.models import Match
from apps.bookings.models import (
    Booking,
    BookingStatus,
    PaymentStatus,
)

logger = logging.getLogger(__name__)


class BookingService:




    @staticmethod
    @transaction.atomic
    def create_booking_request(match_id, initiated_by):

        try:
            match = (
                Match.objects
                .select_related(
                    "package",
                    "trip",
                    "package__sender",
                    "trip__traveler",
                )
                .select_for_update()
                .get(id=match_id)
            )

        except Match.DoesNotExist:
            raise ValidationError("Match does not exist.")

        package = match.package
        trip = match.trip

        # ======================================================
        # MATCH VALIDATION
        # ======================================================

        if not match.is_active:
            raise ValidationError(
                "This match is no longer active."
            )

        if (
            package.status != PackageStatus.PUBLISHED
            or not package.is_active
        ):
            raise ValidationError(
                "This package is not currently published."
            )

        if not trip.is_public or not trip.is_active:
            raise ValidationError(
                "This trip is not currently available."
            )

        if initiated_by != package.sender:
            raise ValidationError(
                "Only the package sender can create a booking request."
            )

        if package.sender_id == trip.traveler_id:
            raise ValidationError(
                "You cannot book your own trip."
            )

        # ======================================================
        # CAPACITY VALIDATION
        # ======================================================

        if trip.available_weight_kg < package.weight:
            raise ValidationError(
                f"Insufficient available capacity. "
                f"Required: {package.weight}kg, "
                f"Available: {trip.available_weight_kg}kg."
            )

        # ======================================================
        # EXPIRE OLD BOOKINGS
        # ======================================================

        now = timezone.now()

        Booking.objects.filter(
            match=match,
            status=BookingStatus.PENDING,
            expires_at__lte=now,
        ).update(
            is_active=False,
            status=BookingStatus.EXPIRED,
        )

        # ======================================================
        # CHECK ACTIVE BOOKING
        # ======================================================

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
            expires_at__gt=now,
        ).exists()

        if active_booking_exists:
            raise ValidationError(
                "An active booking already exists for this match."
            )

        # ======================================================
        # CALCULATE REWARD
        # ======================================================

        reward_per_kg = Decimal(
            str(trip.reward_per_kg)
        )

        weight = Decimal(
            str(package.weight)
        )

        agreed_reward = (
            reward_per_kg * weight
        ).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

        # ======================================================
        # CREATE BOOKING
        # ======================================================

        booking = Booking.objects.create(
            match=match,
            package=package,
            trip=trip,
            sender=package.sender,
            traveler=trip.traveler,

            # IMPORTANT
            agreed_reward=agreed_reward,

            agreed_weight_kg=weight,

            currency=trip.currency,

            status=BookingStatus.PENDING,

            payment_status=PaymentStatus.UNPAID,

            is_active=True,

            expires_at=now + timedelta(days=7),
        )

        # ======================================================
        # CREATE / REUSE CHAT ROOM
        # ======================================================

        chat_room, chat_created = (
            ChatService.get_or_create_booking_room(
                booking=booking,
            )
        )

        chat_message = (
            ChatService.create_booking_request_message(
                booking=booking,
                room=chat_room,
            )
        )

        notification = (
            create_booking_request_notification(
                booking=booking,
                chat_room=chat_room,
                chat_message=chat_message,
            )
        )

        logger.info(
            "Booking %s created | Match=%s | Package=%s | Trip=%s | "
            "Weight=%s | RewardPerKg=%s | AgreedReward=%s | ChatRoom=%s",
            booking.tracking_number,
            match.id,
            package.id,
            trip.id,
            weight,
            reward_per_kg,
            agreed_reward,
            chat_room.id,
        )

        return booking


    @staticmethod
    @transaction.atomic
    def create_public_booking_request(
        trip_id,
        package_id,
        initiated_by,
    ):
        """
        Create a booking request directly from a public trip.

        Flow:
            1. Validate selected trip
            2. Validate selected package ownership
            3. Validate traveler/sender
            4. Validate trip availability
            5. Validate package <-> trip compatibility
            6. Validate duplicate booking
            7. Find/create Match
            8. Create booking
        """

        # ==========================================================
        # 1. FETCH TRIP
        # ==========================================================

        try:
            trip = (
                Trip.objects
                .select_for_update()
                .select_related("traveler")
                .get(
                    id=trip_id,
                    is_public=True,
                )
            )
        except Trip.DoesNotExist:
            raise ValidationError(
                "The selected public trip does not exist."
            )

        # Sync PLANNED → ACTIVE → COMPLETED
        TripStatusService.sync_status(trip)

        # Get latest status after sync
        trip.refresh_from_db()

        # ==========================================================
        # 2. FETCH PACKAGE
        # ==========================================================

        try:
            package = (
                Package.objects
                .select_for_update()
                .select_related("sender")
                .get(id=package_id)
            )
        except Package.DoesNotExist:
            raise ValidationError(
                "Package does not exist."
            )

        # ==========================================================
        # 3. PACKAGE OWNER
        # ==========================================================

        if package.sender_id != initiated_by.id:
            raise ValidationError(
                "You can only use your own package for a booking request."
            )

        # ==========================================================
        # 4. CANNOT BOOK OWN TRIP
        # ==========================================================

        if trip.traveler_id == initiated_by.id:
            raise ValidationError(
                "You cannot book your own trip."
            )

        # ==========================================================
        # 5. PACKAGE MUST BE PUBLISHED
        # ==========================================================

        if package.status != PackageStatus.PUBLISHED:
            raise ValidationError(
                "Your package must be published before you can request this trip."
            )

        if not package.is_active:
            raise ValidationError(
                "This package is no longer active."
            )

        # ==========================================================
        # 6. TRIP MUST BE BOOKABLE
        # ==========================================================

        if not trip.is_public:
            raise ValidationError(
                "This trip is not public."
            )

        if not trip.is_active:
            raise ValidationError(
                "This trip is no longer available."
            )

        if trip.status != TripStatus.PLANNED:
            raise ValidationError(
                "This trip is not currently accepting booking requests."
            )

        if trip.departure_date < timezone.localdate():
            raise ValidationError(
                "This trip has already departed."
            )

        # ==========================================================
        # 7. PACKAGE ↔ TRIP COMPATIBILITY
        # ==========================================================
        #
        # This is the important part.
        #
        # Do NOT duplicate route/date/weight matching here.
        # PackageService is responsible for that logic.
        #

        if not PackageService.package_matches_trip(
            package=package,
            trip=trip,
            sender=initiated_by,
        ):
            raise ValidationError(
                "This package is not compatible with the selected trip. "
                "The package route, dates, or weight do not match the trip."
            )

        # ==========================================================
        # 8. DUPLICATE BOOKING CHECK
        # ==========================================================

        active_booking = Booking.objects.filter(
            package=package,
            trip=trip,
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

        if active_booking:
            raise ValidationError(
                "You already have an active booking request for this trip."
            )


        # ==========================================================
        # 9. FIND / CREATE MATCH
        # ==========================================================

        match, _ = Match.objects.get_or_create(
            package=package,
            trip=trip,
            defaults={
                "is_active": True,
            },
        )

        if not match.is_active:
            match.is_active = True
            match.save(update_fields=["is_active"])


        # ==========================================================
        # 10. CREATE BOOKING
        # ==========================================================

        return BookingService.create_booking_request(
            match_id=match.id,
            initiated_by=initiated_by,
        )
    

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
                    f"({booking.tracking_number})."
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
                    f"{booking.tracking_number}."
                ),
                notification_type=NotificationType.BOOKING,
                object_id=booking.id,
                action_url=f"/bookings/{booking.id}/",
            )

            # 🟢 Delivery PIN email moved from here to execute_start_transit

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
        Updates state, stamps timing logs, registers sender notifications, 
        and dispatches the delivery verification PIN.
        """
        with transaction.atomic():
            # Re-fetch with a row lock to guarantee absolute concurrency protection
            booking = Booking.objects.select_for_update().get(id=booking.id)
            
            # 🟢 Set status and timestamp
            booking.status = BookingStatus.IN_TRANSIT
            booking.in_transit_at = timezone.now()
            booking.save(update_fields=["status", "in_transit_at"])

            # 🟢 Dispatch automated notifications
            Notification.objects.create(
                user=booking.sender,
                title="Package In Transit",
                message=f"Your traveler has started their journey! Order #{booking.tracking_number} is now IN_TRANSIT.",
                notification_type=NotificationType.DELIVERY,
                object_id=booking.id,
                action_url=f"/bookings/{booking.id}/"
            )

            # 🟢 Dispatch Delivery PIN email ONLY after successful DB commit
            transaction.on_commit(
                lambda: send_delivery_pin_email(
                    user_email=booking.sender.email,
                    booking=booking,
                    delivery_pin=booking.delivery_verification_pin,
                )
            )

            logger.info(
                "Booking %s successfully transitioned to IN_TRANSIT by service orchestration.",
                booking.id,
            )
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