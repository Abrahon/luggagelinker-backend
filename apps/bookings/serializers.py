from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError
from apps.matching.models import Match
from .models import Booking
from .services import BookingService
from django.utils.translation import gettext_lazy as _
from apps.bookings.models import Booking, BookingStatus
from django.utils import timezone

from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError
from .models import Booking
from apps.matching.models import Match

from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError
from .models import Booking
from apps.matching.models import Match
from .services import BookingService  
from apps.wallets.services import WalletService
from django.utils import timezone
from rest_framework import serializers

from apps.bookings.models import Booking, BookingStatus
from apps.packages.models import Package
from apps.packages.models import PackageStatus
from apps.trips.models import Trip, TripStatus
from apps.matching.models import MatchStatus


class BookingSerializer(serializers.ModelSerializer):

    tracking_number = serializers.CharField(
        read_only=True
    )

    package_title = serializers.CharField(
        source="package.title",
        read_only=True
    )

    trip_title = serializers.CharField(
        source="trip.title",
        read_only=True
    )

    escrow_status = serializers.SerializerMethodField()

    sender_name = serializers.SerializerMethodField()

    sender_email = serializers.CharField(
        source="sender.email",
        read_only=True
    )

    sender_profile_picture = serializers.SerializerMethodField()

    traveler_email = serializers.CharField(
        source="traveler.email",
        read_only=True
    )

    traveler_matches_listing = serializers.BooleanField(
        source="package.traveler_matches_listing",
        read_only=True,
    )

    traveler_refusal_reason = serializers.CharField(
        source="package.traveler_refusal_reason",
        read_only=True,
    )

    route = serializers.SerializerMethodField()

    package_image = serializers.SerializerMethodField()

    match_id = serializers.UUIDField(
        write_only=True,
        required=True,
    )

    class Meta:
        model = Booking

        fields = [
            "id",
            "match_id",

            "tracking_number",

            # Package
            "package_title",
            "package_image",

            # Trip
            "trip_title",

            # Sender
            "sender_name",
            "sender_email",
            "sender_profile_picture",

            # Traveler
            "traveler_email",

            # Route
            "route",

            # Booking
            "status",
            "payment_status",
            "escrow_status",

            # Pricing
            "agreed_reward",
            "currency",

            # Weight
            "agreed_weight_kg",

            # Handshake
            "traveler_matches_listing",
            "traveler_refusal_reason",

            # Dates
            "expires_at",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "tracking_number",
            "status",
            "payment_status",
            "agreed_reward",
            "currency",
            "agreed_weight_kg",
            "expires_at",
            "created_at",
            "updated_at",
        ]

    # ------------------------------------------------------
    # SENDER NAME
    # ------------------------------------------------------

    def get_sender_name(self, obj):
        if not obj.sender:
            return ""

        profile = getattr(
            obj.sender,
            "profile",
            None,
        )

        if profile:
            full_name = getattr(
                profile,
                "full_name",
                None,
            )

            if full_name:
                return full_name

        return getattr(
            obj.sender,
            "username",
            obj.sender.email,
        )

    # ------------------------------------------------------
    # ESCROW
    # ------------------------------------------------------

    def get_escrow_status(self, obj):
        return WalletService.get_escrow_status(obj)

    # ------------------------------------------------------
    # PROFILE PICTURE
    # ------------------------------------------------------

    def get_sender_profile_picture(self, obj):
        if not obj.sender:
            return None

        profile = getattr(
            obj.sender,
            "profile",
            None,
        )

        if not profile:
            return None

        picture = getattr(
            profile,
            "profile_picture",
            None,
        )

        if not picture:
            return None

        try:
            return picture.url
        except Exception:
            return str(picture)

    # ------------------------------------------------------
    # ROUTE
    # ------------------------------------------------------

    def get_route(self, obj):
        trip = getattr(
            obj,
            "trip",
            None,
        )

        if trip:
            return {
                "from_country": trip.from_country,
                "from_city": trip.from_city,
                "to_country": trip.to_country,
                "to_city": trip.to_city,
            }

        package = getattr(
            obj,
            "package",
            None,
        )

        if package:
            return {
                "from_country": package.pickup_country,
                "from_city": package.pickup_city,
                "to_country": package.destination_country,
                "to_city": package.destination_city,
            }

        return {}

    # ------------------------------------------------------
    # PACKAGE IMAGE
    # ------------------------------------------------------

    def get_package_image(self, obj):
        package = getattr(
            obj,
            "package",
            None,
        )

        if not package:
            return None

        primary = (
            package.images
            .filter(is_primary=True)
            .first()
        )

        if primary:
            return str(primary.image)

        first = package.images.first()

        if first:
            return str(first.image)

        return None

    # ------------------------------------------------------
    # VALIDATE
    # ------------------------------------------------------

    def validate(self, attrs):

        match_id = attrs.get("match_id")

        if not match_id:
            raise serializers.ValidationError({
                "match_id": "Match ID is required."
            })

        try:
            match = Match.objects.get(
                id=match_id,
                is_active=True,
                status=MatchStatus.AVAILABLE,
            )

        except Match.DoesNotExist:
            raise serializers.ValidationError({
                "match_id": (
                    "The selected match does not exist "
                    "or is no longer available."
                )
            })

        active_exists = Booking.objects.filter(
            match_id=match_id,
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

        if active_exists:
            raise serializers.ValidationError({
                "match_id": (
                    "An active booking request already "
                    "exists for this match."
                )
            })

        return attrs

    # ------------------------------------------------------
    # CREATE
    # ------------------------------------------------------

    def create(self, validated_data):

        match_id = validated_data["match_id"]

        request = self.context.get("request")

        if not request:
            raise serializers.ValidationError(
                "Request context is required."
            )

        try:
            return BookingService.create_booking_request(
                match_id=match_id,
                initiated_by=request.user,
            )

        except DjangoValidationError as e:

            if hasattr(e, "message_dict"):
                raise serializers.ValidationError(
                    e.message_dict
                )

            if hasattr(e, "messages"):
                raise serializers.ValidationError(
                    e.messages[0]
                    if len(e.messages) == 1
                    else e.messages
                )

            raise serializers.ValidationError(
                str(e)
            )

        
class PublicTripBookingRequestSerializer(serializers.Serializer):
    """
    Serializer for booking requests initiated directly from a public trip.

    Flow:
        Public Trip
            ↓
        GET /api/my/package/
            ↓
        User selects a package
            ↓
        POST /api/bookings/public-trip-request/
            ↓
        Validate selected trip + package
            ↓
        BookingService.create_public_booking_request()
    """

    trip_id = serializers.UUIDField(required=True)
    package_id = serializers.UUIDField(required=True)

    # ==========================================================
    # 1. VALIDATE TRIP
    # ==========================================================

    def validate_trip_id(self, value):
        try:
            trip = (
                Trip.objects
                .select_related("traveler")
                .get(
                    id=value,
                    is_public=True,
                    is_active=True,
                )
            )
        except Trip.DoesNotExist:
            raise serializers.ValidationError(
                "The selected public trip does not exist or is no longer available."
            )

        # Trip must still accept booking requests.
        if trip.status != TripStatus.PLANNED:
            raise serializers.ValidationError(
                "This trip is no longer accepting booking requests."
            )

        # Trip cannot already be departed.
        if trip.departure_date < timezone.localdate():
            raise serializers.ValidationError(
                "This trip has already departed."
            )

        # Public trip must have a traveler.
        if not trip.traveler:
            raise serializers.ValidationError(
                "This trip does not have a valid traveler."
            )

        self._trip = trip

        return value

    # ==========================================================
    # 2. VALIDATE PACKAGE + SELECTED TRIP
    # ==========================================================

    def validate(self, attrs):
        request = self.context["request"]
        user = request.user

        trip_id = attrs["trip_id"]
        package_id = attrs["package_id"]

        # ------------------------------------------------------
        # FETCH TRIP
        # ------------------------------------------------------

        trip = getattr(self, "_trip", None)

        if trip is None:
            try:
                trip = (
                    Trip.objects
                    .select_related("traveler")
                    .get(
                        id=trip_id,
                        is_public=True,
                        is_active=True,
                    )
                )
            except Trip.DoesNotExist:
                raise serializers.ValidationError({
                    "trip_id": (
                        "The selected public trip does not exist "
                        "or is no longer available."
                    )
                })

        # ------------------------------------------------------
        # USER CANNOT BOOK OWN TRIP
        # ------------------------------------------------------

        if trip.traveler == user:
            raise serializers.ValidationError({
                "trip_id": (
                    "You cannot send a booking request "
                    "to your own trip."
                )
            })

        # ------------------------------------------------------
        # FETCH USER'S PACKAGE
        # ------------------------------------------------------

        try:
            package = (
                Package.objects
                .select_related("sender")
                .get(
                    id=package_id,
                    sender=user,
                )
            )
        except Package.DoesNotExist:
            raise serializers.ValidationError({
                "package_id": (
                    "Package not found or does not belong to you."
                )
            })

        # ------------------------------------------------------
        # PACKAGE MUST BE PUBLISHED
        # ------------------------------------------------------

        if package.status != PackageStatus.PUBLISHED:
            raise serializers.ValidationError({
                "package_id": (
                    "Your package must be published "
                    "before requesting a booking."
                )
            })

        # ======================================================
        # RULE 1 — ROUTE MUST MATCH SELECTED TRIP
        # ======================================================

        package_pickup_country = (
            (package.pickup_country or "")
            .strip()
            .casefold()
        )

        package_pickup_city = (
            (package.pickup_city or "")
            .strip()
            .casefold()
        )

        package_destination_country = (
            (package.destination_country or "")
            .strip()
            .casefold()
        )

        package_destination_city = (
            (package.destination_city or "")
            .strip()
            .casefold()
        )

        trip_from_country = (
            (trip.from_country or "")
            .strip()
            .casefold()
        )

        trip_from_city = (
            (trip.from_city or "")
            .strip()
            .casefold()
        )

        trip_to_country = (
            (trip.to_country or "")
            .strip()
            .casefold()
        )

        trip_to_city = (
            (trip.to_city or "")
            .strip()
            .casefold()
        )

        # ------------------------------------------------------
        # ORIGIN
        # ------------------------------------------------------

        if package_pickup_country != trip_from_country:
            raise serializers.ValidationError({
                "package_id": (
                    f"Package pickup country "
                    f"({package.pickup_country}) does not match "
                    f"the trip departure country "
                    f"({trip.from_country})."
                )
            })

        if package_pickup_city != trip_from_city:
            raise serializers.ValidationError({
                "package_id": (
                    f"Package pickup city "
                    f"({package.pickup_city}) does not match "
                    f"the trip departure city "
                    f"({trip.from_city})."
                )
            })

        # ------------------------------------------------------
        # DESTINATION
        # ------------------------------------------------------

        if package_destination_country != trip_to_country:
            raise serializers.ValidationError({
                "package_id": (
                    f"Package destination country "
                    f"({package.destination_country}) does not match "
                    f"the trip destination country "
                    f"({trip.to_country})."
                )
            })

        if package_destination_city != trip_to_city:
            raise serializers.ValidationError({
                "package_id": (
                    f"Package destination city "
                    f"({package.destination_city}) does not match "
                    f"the trip destination city "
                    f"({trip.to_city})."
                )
            })

        # ======================================================
        # RULE 2 — DATE MUST MATCH SELECTED TRIP
        # ======================================================

        package_pickup_date = getattr(
            package,
            "pickup_date",
            None,
        )

        if (
            package_pickup_date
            and trip.departure_date
            and package_pickup_date > trip.departure_date
        ):
            raise serializers.ValidationError({
                "package_id": (
                    f"Package pickup date "
                    f"({package_pickup_date}) is after "
                    f"the trip departure date "
                    f"({trip.departure_date})."
                )
            })

        # ------------------------------------------------------
        # Trip arrival vs package latest delivery
        # ------------------------------------------------------

        trip_arrival_date = getattr(
            trip,
            "arrival_date",
            None,
        )

        package_latest_delivery_date = getattr(
            package,
            "latest_delivery_date",
            None,
        )

        if (
            trip_arrival_date
            and package_latest_delivery_date
            and trip_arrival_date > package_latest_delivery_date
        ):
            raise serializers.ValidationError({
                "package_id": (
                    f"Trip arrival date "
                    f"({trip_arrival_date}) is later than "
                    f"the package latest delivery date "
                    f"({package_latest_delivery_date})."
                )
            })

        # ======================================================
        # 3. CAPACITY CHECK
        # ======================================================

        package_weight = package.weight

        if trip.available_weight_kg < package_weight:
            raise serializers.ValidationError({
                "package_id": (
                    f"Insufficient available capacity. "
                    f"Package requires {package_weight}kg, "
                    f"but only {trip.available_weight_kg}kg "
                    f"is available."
                )
            })

        # ======================================================
        # 4. PREVENT DUPLICATE ACTIVE BOOKING
        # ======================================================

        active_statuses = [
            BookingStatus.PENDING,
            BookingStatus.TRAVELER_ACCEPTED,
            BookingStatus.PAYMENT_PENDING,
            BookingStatus.CONFIRMED,
            BookingStatus.PICKED_UP,
            BookingStatus.IN_TRANSIT,
        ]

        duplicate_exists = Booking.objects.filter(
            package=package,
            trip=trip,
            is_active=True,
            status__in=active_statuses,
            expires_at__gt=timezone.now(),
        ).exists()

        if duplicate_exists:
            raise serializers.ValidationError({
                "booking": (
                    "You already have an active booking "
                    "request for this package and trip."
                )
            })

        # ======================================================
        # STORE OBJECTS FOR VIEW / SERVICE
        # ======================================================

        attrs["trip"] = trip
        attrs["package"] = package
        attrs["traveler"] = trip.traveler

        return attrs




class VerifyPickupPinSerializer(serializers.Serializer):
    booking_id = serializers.UUIDField(required=True)

    traveler_matches_listing = serializers.BooleanField(required=True)

    pickup_pin = serializers.CharField(
        max_length=6,
        min_length=6,
        required=False,
        allow_blank=True,
    )

    traveler_refusal_reason = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    def validate(self, attrs):
        booking_id = attrs.get("booking_id")

        try:
            booking = Booking.objects.get(id=booking_id)
        except Booking.DoesNotExist:
            raise serializers.ValidationError(
                {"booking_id": _("Booking not found.")}
            )

        if booking.status == BookingStatus.PAYMENT_PENDING:
            raise serializers.ValidationError(
                {
                    "detail": (
                        "Payment has not been completed yet. "
                        "The sender must complete payment before pickup can be verified."
                    )
                }
            )

        if booking.status != BookingStatus.CONFIRMED:
            raise serializers.ValidationError(
                {
                    "detail": (
                        f"Pickup cannot be performed while the booking is '{booking.status}'. "
                        "Only confirmed bookings are eligible for pickup verification."
                    )
                }
            )

        request_user = self.context["request"].user

        if booking.traveler != request_user:
            raise serializers.ValidationError(
                _("Only the assigned traveler can verify pickup.")
            )

        # ============================================================
        # Traveler refused package
        # ============================================================
        if attrs["traveler_matches_listing"] is False:

            if not attrs.get("traveler_refusal_reason"):
                raise serializers.ValidationError(
                    {
                        "traveler_refusal_reason":
                        _("Please provide the reason for refusing the package.")
                    }
                )

            attrs["booking"] = booking
            return attrs

        # ============================================================
        # Traveler accepted package
        # ============================================================
        pickup_pin = attrs.get("pickup_pin")

        if not pickup_pin:
            raise serializers.ValidationError(
                {
                    "pickup_pin":
                    _("Pickup PIN is required.")
                }
            )

        if booking.pickup_verification_pin != pickup_pin:
            raise serializers.ValidationError(
                {
                    "pickup_pin":
                    _("Invalid pickup PIN.")
                }
            )

        attrs["booking"] = booking
        return attrs


# Transit serilizer for booking pickup verification

class StartTransitSerializer(serializers.Serializer):
    """
    Validates rules required to advance a booking from PICKED_UP to IN_TRANSIT.
    """
    booking_id = serializers.UUIDField(required=True)

    def validate(self, attrs):
        booking_id = attrs.get("booking_id")

        try:
            booking = Booking.objects.get(id=booking_id)
        except Booking.DoesNotExist:
            raise serializers.ValidationError({"booking_id": _("Target booking contract instance not found.")})

        # 1. State Guard: Enforce strict chronological order
        if booking.status != BookingStatus.PICKED_UP:
            raise serializers.ValidationError(
                _("Transit cannot be started. Booking must be in PICKED_UP status.")
            )

        # 2. Authorization Guard: Only the assigned traveler can start their transit routing
        request_user = self.context["request"].user
        if booking.traveler != request_user:
            raise serializers.ValidationError(
                _("Access Denied. Only the designated traveler can declare transit updates.")
            )

        attrs["booking_instance"] = booking
        return attrs




# delivery serilizer for booking pickup verification

class VerifyDeliveryPinSerializer(serializers.Serializer):
    booking_id = serializers.UUIDField(required=True)
    delivery_pin = serializers.CharField(max_length=6, min_length=6, required=True)

    def validate(self, attrs):
        booking_id = attrs.get("booking_id")
        input_pin = attrs.get("delivery_pin")

        try:
            booking = Booking.objects.get(id=booking_id)
        except Booking.DoesNotExist:
            raise serializers.ValidationError({"booking_id": _("Target booking contract instance not found.")})

        # 1. State Guard: Hand-off can only occur mid-route
        if booking.status != BookingStatus.IN_TRANSIT:
            raise serializers.ValidationError(_("Delivery hand-off cannot be verified unless package is IN_TRANSIT."))

        # 2. Authorization Guard: Only the assigned Traveler can input the passcode drop clearance
        request_user = self.context["request"].user
        if booking.traveler != request_user:
            raise serializers.ValidationError(_("Access Denied. Only the designated traveler can execute delivery clearances."))

        # 3. Code Match Verification
        if booking.delivery_verification_pin != input_pin:
            raise serializers.ValidationError({"delivery_pin": _("Invalid delivery security confirmation PIN entry.")})

        attrs["booking_instance"] = booking
        return attrs


# sender dashbaord
# apps/bookings/serializers.py

class SenderDashboardStatsSerializer(serializers.Serializer):
    active_bookings = serializers.IntegerField()
    pending_bookings = serializers.IntegerField()
    completed_bookings = serializers.IntegerField()
    total_spent = serializers.DecimalField(
        max_digits=12,
        decimal_places=2
    )





class SenderPaymentSummarySerializer(serializers.Serializer):
    total_paid = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True,
    )

    escrow_held = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True,
    )

    released = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True,
    )

    refunded = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True,
    )
# sender 

class SenderActionRequiredSerializer(serializers.Serializer):
    booking_id = serializers.UUIDField()
    tracking_number = serializers.CharField()
    package_title = serializers.CharField()
    traveler_name = serializers.CharField()
    action = serializers.CharField()
    title = serializers.CharField()
    description = serializers.CharField()
    button_text = serializers.CharField()
    current_status = serializers.CharField()
    reward = serializers.DecimalField(max_digits=10, decimal_places=2)
    currency = serializers.CharField()


# sender
from rest_framework import serializers

from apps.bookings.models import Booking, BookingStatus, PaymentStatus
from apps.wallets.services import WalletService


class MyBookingSerializer(serializers.ModelSerializer):
    tracking_number = serializers.CharField(read_only=True)

    package_title = serializers.CharField(
        source="package.title",
        read_only=True,
    )

    trip_title = serializers.CharField(
        source="trip.title",
        read_only=True,
    )

    traveler_name = serializers.SerializerMethodField()
    traveler_email = serializers.CharField(
        source="traveler.email",
        read_only=True,
    )

    package_image = serializers.SerializerMethodField()
    route = serializers.SerializerMethodField()

    escrow_status = serializers.SerializerMethodField()

    created_date = serializers.SerializerMethodField()

    can_pay = serializers.SerializerMethodField()
    can_track = serializers.SerializerMethodField()
    can_chat = serializers.SerializerMethodField()
    can_verify_delivery = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()
    can_review = serializers.SerializerMethodField()
    can_view_receipt = serializers.SerializerMethodField()

    show_progress = serializers.SerializerMethodField()
    show_payment_required = serializers.SerializerMethodField()
    show_delivery_verification = serializers.SerializerMethodField()

    current_step = serializers.SerializerMethodField()

    class Meta:
        model = Booking

        fields = [
            "id",
            "tracking_number",

            "package_title",
            "trip_title",

            "traveler_name",
            "traveler_email",

            "route",
            "package_image",

            "status",
            "payment_status",
            "escrow_status",

            "currency",
            "agreed_reward",

            "created_date",

            "current_step",

            "can_pay",
            "can_track",
            "can_chat",
            "can_verify_delivery",
            "can_cancel",
            "can_review",
            "can_view_receipt",

            "show_progress",
            "show_payment_required",
            "show_delivery_verification",
        ]

    # --------------------------------------------------
    # Basic Information
    # --------------------------------------------------

    def get_traveler_name(self, obj):
        if (
            hasattr(obj.traveler, "profile")
            and obj.traveler.profile
            and obj.traveler.profile.full_name
        ):
            return obj.traveler.profile.full_name

        return obj.traveler.email

    def get_package_image(self, obj):
        primary = obj.package.images.filter(
            is_primary=True
        ).first()

        if primary:
            return primary.image

        first = obj.package.images.first()

        if first:
            return first.image

        return None

    def get_route(self, obj):
        trip = obj.trip

        return {
            "from_country": trip.from_country,
            "from_city": trip.from_city,
            "to_country": trip.to_country,
            "to_city": trip.to_city,
        }

    def get_created_date(self, obj):
        return obj.created_at.strftime("%Y-%m-%d")

    def get_escrow_status(self, obj):
        return WalletService.get_escrow_status(obj)

    # --------------------------------------------------
    # Button Visibility
    # --------------------------------------------------

    def get_can_pay(self, obj):
        return (
            obj.status == BookingStatus.PAYMENT_PENDING
            and obj.payment_status == PaymentStatus.UNPAID
        )

    def get_can_track(self, obj):
        return obj.status in [
            BookingStatus.CONFIRMED,
            BookingStatus.PICKED_UP,
            BookingStatus.IN_TRANSIT,
            BookingStatus.DELIVERED,
        ]

    def get_can_chat(self, obj):
        return obj.status in [
            BookingStatus.TRAVELER_ACCEPTED,
            BookingStatus.PAYMENT_PENDING,
            BookingStatus.CONFIRMED,
            BookingStatus.PICKED_UP,
            BookingStatus.IN_TRANSIT,
            BookingStatus.DELIVERED,
        ]

    def get_can_verify_delivery(self, obj):
        return obj.status == BookingStatus.DELIVERED

    def get_can_cancel(self, obj):
        return obj.status in [
            BookingStatus.PENDING,
            BookingStatus.TRAVELER_ACCEPTED,
            BookingStatus.PAYMENT_PENDING,
        ]

    def get_can_review(self, obj):
        return obj.status == BookingStatus.COMPLETED

    def get_can_view_receipt(self, obj):
        return obj.status == BookingStatus.COMPLETED

    # --------------------------------------------------
    # UI Sections
    # --------------------------------------------------

    def get_show_progress(self, obj):
        return obj.status in [
            BookingStatus.CONFIRMED,
            BookingStatus.PICKED_UP,
            BookingStatus.IN_TRANSIT,
            BookingStatus.DELIVERED,
            BookingStatus.COMPLETED,
        ]

    def get_show_payment_required(self, obj):
        return (
            obj.status == BookingStatus.PAYMENT_PENDING
            and obj.payment_status == PaymentStatus.UNPAID
        )

    def get_show_delivery_verification(self, obj):
        return obj.status == BookingStatus.DELIVERED

    # --------------------------------------------------
    # Progress Step
    # --------------------------------------------------

    def get_current_step(self, obj):

        mapping = {
            BookingStatus.PENDING: 1,
            BookingStatus.TRAVELER_ACCEPTED: 2,
            BookingStatus.PAYMENT_PENDING: 3,
            BookingStatus.CONFIRMED: 4,
            BookingStatus.PICKED_UP: 5,
            BookingStatus.IN_TRANSIT: 6,
            BookingStatus.DELIVERED: 7,
            BookingStatus.COMPLETED: 8,
            BookingStatus.CANCELLED: 0,
            BookingStatus.REJECTED: 0,
            BookingStatus.EXPIRED: 0,
        }

        return mapping.get(obj.status, 0)



# class SenderBookingDetailSerializer(serializers.ModelSerializer):
#     traveler_matches_listing = serializers.BooleanField(
#     source="package.traveler_matches_listing",
#     read_only=True,
#     )

#     traveler_refusal_reason = serializers.CharField(
#         source="package.traveler_refusal_reason",
#         read_only=True,
#         allow_null=True,
#     )

#     tracking_number = serializers.CharField(read_only=True)

#     package_title = serializers.CharField(
#         source="package.title",
#         read_only=True,
#     )

#     package_description = serializers.CharField(
#         source="package.description",
#         read_only=True,
#     )

#     trip_title = serializers.CharField(
#         source="trip.title",
#         read_only=True,
#     )

#     traveler_name = serializers.SerializerMethodField()

#     traveler_email = serializers.CharField(
#         source="traveler.email",
#         read_only=True,
#     )

#     traveler_phone = serializers.SerializerMethodField()

#     traveler_profile_picture = serializers.SerializerMethodField()

#     package_image = serializers.SerializerMethodField()

#     route = serializers.SerializerMethodField()

#     escrow_status = serializers.SerializerMethodField()

#     class Meta:
#         model = Booking

#         fields = [
#             "id",
#             "tracking_number",

#             "package_title",
#             "package_description",
#             "package_image",
#             "traveler_matches_listing",
#             "traveler_refusal_reason",

#             "trip_title",

#             "traveler_name",
#             "traveler_email",
#             "traveler_phone",
#             "traveler_profile_picture",

#             "route",

#             "status",
#             "payment_status",
#             "escrow_status",

#             "currency",
#             "agreed_reward",
#             "agreed_weight_kg",

#             "traveler_matches_listing",
#             "traveler_refusal_reason",

#             "created_at",
#             "picked_up_at",
#             "in_transit_at",
#             "delivered_at",
#             "completed_at",

#             "expires_at",
#         ]

#     def get_traveler_name(self, obj):
#         profile = getattr(obj.traveler, "profile", None)

#         if profile:
#             return profile.full_name

#         return obj.traveler.email


#     def get_traveler_phone(self, obj):
#         profile = getattr(obj.traveler, "profile", None)

#         if profile:
#             return profile.phone

#         return ""


#     def get_traveler_profile_picture(self, obj):
#         profile = getattr(obj.traveler, "profile", None)

#         if profile and profile.profile_picture:
#             return profile.profile_picture.url

#         return None

#     def get_package_image(self, obj):
#         image = obj.package.images.filter(
#             is_primary=True
#         ).first()

#         if image:
#             return image.image

#         image = obj.package.images.first()

#         if image:
#             return image.image

#         return None

#     def get_route(self, obj):

#         trip = obj.trip

#         return {
#             "from_country": trip.from_country,
#             "from_city": trip.from_city,
#             "to_country": trip.to_country,
#             "to_city": trip.to_city,
#         }

#     def get_escrow_status(self, obj):
#         return WalletService.get_escrow_status(obj)

from datetime import timedelta


# Make sure to import your Booking model, BookingStatus enum, and WalletService
# from .models import Booking, BookingStatus
# from .services import WalletService


class SenderBookingDetailSerializer(serializers.ModelSerializer):
    traveler_matches_listing = serializers.BooleanField(
        source="package.traveler_matches_listing",
        read_only=True,
    )

    traveler_refusal_reason = serializers.CharField(
        source="package.traveler_refusal_reason",
        read_only=True,
        allow_null=True,
    )

    tracking_number = serializers.CharField(read_only=True)

    package_title = serializers.CharField(
        source="package.title",
        read_only=True,
    )

    package_description = serializers.CharField(
        source="package.description",
        read_only=True,
    )

    trip_title = serializers.CharField(
        source="trip.title",
        read_only=True,
    )

    traveler_name = serializers.SerializerMethodField()

    traveler_email = serializers.CharField(
        source="traveler.email",
        read_only=True,
    )

    traveler_phone = serializers.SerializerMethodField()

    traveler_profile_picture = serializers.SerializerMethodField()

    package_image = serializers.SerializerMethodField()

    route = serializers.SerializerMethodField()

    escrow_status = serializers.SerializerMethodField()

    progress_percentage = serializers.SerializerMethodField()

    current_step = serializers.SerializerMethodField()

    estimated_delivery = serializers.SerializerMethodField()

    latest_update = serializers.SerializerMethodField()

    show_tracking = serializers.SerializerMethodField()

    class Meta:
        model = Booking

        fields = [
            "id",
            "tracking_number",
            "package_title",
            "package_description",
            "package_image",
            "traveler_matches_listing",
            "traveler_refusal_reason",
            "trip_title",
            "traveler_name",
            "traveler_email",
            "traveler_phone",
            "traveler_profile_picture",
            "route",
            "status",
            "payment_status",
            "escrow_status",
            "progress_percentage",
            "current_step",
            "estimated_delivery",
            "latest_update",
            "show_tracking",
            "currency",
            "agreed_reward",
            "agreed_weight_kg",
            "created_at",
            "picked_up_at",
            "in_transit_at",
            "delivered_at",
            "completed_at",
            "expires_at",
        ]

    def get_traveler_name(self, obj):
        profile = getattr(obj.traveler, "profile", None)
        if profile and profile.full_name:
            return profile.full_name
        return obj.traveler.email

    def get_traveler_phone(self, obj):
        profile = getattr(obj.traveler, "profile", None)
        if profile:
            return profile.phone
        return ""

    def get_traveler_profile_picture(self, obj):
        profile = getattr(obj.traveler, "profile", None)
        if profile and profile.profile_picture:
            return profile.profile_picture.url
        return None

    def get_package_image(self, obj):
        image = obj.package.images.filter(is_primary=True).first()
        if image:
            return image.image.url if hasattr(image.image, "url") else image.image

        image = obj.package.images.first()
        if image:
            return image.image.url if hasattr(image.image, "url") else image.image

        return None

    def get_route(self, obj):
        trip = obj.trip
        return {
            "from_country": trip.from_country,
            "from_city": trip.from_city,
            "to_country": trip.to_country,
            "to_city": trip.to_city,
        }

    def get_escrow_status(self, obj):
        return WalletService.get_escrow_status(obj)

    def get_current_step(self, obj):
        steps = {
            BookingStatus.PENDING: 1,
            BookingStatus.TRAVELER_ACCEPTED: 2,
            BookingStatus.PAYMENT_PENDING: 3,
            BookingStatus.CONFIRMED: 4,
            BookingStatus.PICKED_UP: 5,
            BookingStatus.IN_TRANSIT: 6,
            BookingStatus.DELIVERED: 7,
            BookingStatus.COMPLETED: 8,
            BookingStatus.CANCELLED: 0,
            BookingStatus.REJECTED: 0,
            BookingStatus.EXPIRED: 0,
        }
        return steps.get(obj.status, 0)

    def get_progress_percentage(self, obj):
        progress = {
            BookingStatus.PENDING: 10,
            BookingStatus.TRAVELER_ACCEPTED: 20,
            BookingStatus.PAYMENT_PENDING: 30,
            BookingStatus.CONFIRMED: 40,
            BookingStatus.PICKED_UP: 55,
            BookingStatus.IN_TRANSIT: 75,
            BookingStatus.DELIVERED: 90,
            BookingStatus.COMPLETED: 100,
            BookingStatus.CANCELLED: 0,
            BookingStatus.REJECTED: 0,
            BookingStatus.EXPIRED: 0,
        }
        return progress.get(obj.status, 0)

    def get_estimated_delivery(self, obj):
        if hasattr(obj.trip, "arrival_date") and obj.trip.arrival_date:
            return obj.trip.arrival_date

        if obj.status == BookingStatus.IN_TRANSIT:
            return (obj.in_transit_at + timedelta(days=3)) if obj.in_transit_at else None

        return None

    def get_show_tracking(self, obj):
        return obj.status in [
            BookingStatus.CONFIRMED,
            BookingStatus.PICKED_UP,
            BookingStatus.IN_TRANSIT,
            BookingStatus.DELIVERED,
        ]

    def get_latest_update(self, obj):
        if obj.status == BookingStatus.PENDING:
            return {
                "title": "Booking Created",
                "description": "Waiting for traveler acceptance.",
                "time": obj.created_at,
            }

        if obj.status == BookingStatus.TRAVELER_ACCEPTED:
            return {
                "title": "Traveler Accepted",
                "description": "Traveler accepted your booking.",
                "time": getattr(obj, "traveler_accepted_at", None),
            }

        if obj.status == BookingStatus.PAYMENT_PENDING:
            return {
                "title": "Waiting For Payment",
                "description": "Complete payment to confirm this shipment.",
                "time": None,
            }

        if obj.status == BookingStatus.CONFIRMED:
            return {
                "title": "Booking Confirmed",
                "description": "Payment completed successfully.",
                "time": getattr(obj, "confirmed_at", None),
            }

        if obj.status == BookingStatus.PICKED_UP:
            return {
                "title": "Package Picked Up",
                "description": "Traveler collected your package.",
                "time": obj.picked_up_at,
            }

        if obj.status == BookingStatus.IN_TRANSIT:
            return {
                "title": "Package In Transit",
                "description": "Traveler is transporting your package.",
                "time": obj.in_transit_at,
            }

        if obj.status == BookingStatus.DELIVERED:
            return {
                "title": "Delivered",
                "description": "Traveler marked the package as delivered.",
                "time": obj.delivered_at,
            }

        if obj.status == BookingStatus.COMPLETED:
            return {
                "title": "Completed",
                "description": "Booking completed successfully.",
                "time": obj.completed_at,
            }

        if obj.status == BookingStatus.CANCELLED:
            return {
                "title": "Booking Cancelled",
                "description": "Booking was cancelled.",
                "time": getattr(obj, "updated_at", None),
            }

        if obj.status == BookingStatus.REJECTED:
            return {
                "title": "Traveler Rejected Package",
                "description": getattr(obj.package, "traveler_refusal_reason", None)
                or "Traveler rejected the package.",
                "time": getattr(obj, "updated_at", None),
            }

        if obj.status == BookingStatus.EXPIRED:
            return {
                "title": "Booking Expired",
                "description": "Booking request expired.",
                "time": getattr(obj, "updated_at", None),
            }

        return None
    

# timeline 
# serializers.py


class BookingTimelineItemSerializer(serializers.Serializer):
    title = serializers.CharField()
    status = serializers.CharField()
    completed = serializers.BooleanField()
    timestamp = serializers.DateTimeField(allow_null=True)





class SenderRecentBookingSerializer(serializers.ModelSerializer):

    package_title = serializers.CharField(
        source="package.title",
        read_only=True,
    )

    traveler_name = serializers.SerializerMethodField()

    package_image = serializers.SerializerMethodField()

    escrow_status = serializers.SerializerMethodField()

    class Meta:
        model = Booking

        fields = [
            "id",
            "tracking_number",
            "package_title",
            "traveler_name",
            "status",
            "payment_status",
            "escrow_status",
            "currency",
            "agreed_reward",
            "created_at",
            "package_image",
        ]

    def get_traveler_name(self, obj):

        profile = getattr(obj.traveler, "profile", None)

        if profile and profile.full_name:
            return profile.full_name

        return obj.traveler.email

    def get_package_image(self, obj):

        image = obj.package.images.filter(
            is_primary=True
        ).first()

        if image:
            return image.image

        image = obj.package.images.first()

        if image:
            return image.image

        return None

    def get_escrow_status(self, obj):

        return WalletService.get_escrow_status(obj)


# delivery history
from rest_framework import serializers

from apps.bookings.models import Booking
from apps.wallets.services import WalletService


class SenderDeliveryHistorySerializer(serializers.ModelSerializer):

    tracking_number = serializers.CharField(read_only=True)

    package_title = serializers.CharField(
        source="package.title",
        read_only=True,
    )

    traveler = serializers.PrimaryKeyRelatedField(read_only=True)

    traveler_name = serializers.SerializerMethodField()

    package_image = serializers.SerializerMethodField()

    escrow_status = serializers.SerializerMethodField()

    completed_date = serializers.SerializerMethodField()

    payment_status_display = serializers.CharField(
        source="get_payment_status_display",
        read_only=True,
    )

    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    has_dispute = serializers.SerializerMethodField()

    dispute_id = serializers.SerializerMethodField()

    dispute_status = serializers.SerializerMethodField()

    dispute_status_display = serializers.SerializerMethodField()

    class Meta:
        model = Booking

        fields = [
            "id",
            "tracking_number",
            "package_title",
            "package_image",

            "traveler",
            "traveler_name",

            "status",
            "status_display",

            "payment_status",
            "payment_status_display",

            "escrow_status",

            "currency",
            "agreed_reward",

            "completed_date",

            "has_dispute",
            "dispute_id",
            "dispute_status",
            "dispute_status_display",
        ]

    # ----------------------------------------------------
    # Traveler
    # ----------------------------------------------------

    def get_traveler_name(self, obj):

        if not obj.traveler:
            return "N/A"

        profile = getattr(obj.traveler, "profile", None)

        if profile and profile.full_name:
            return profile.full_name

        return obj.traveler.email

    # ----------------------------------------------------
    # Package Image
    # ----------------------------------------------------

    def get_package_image(self, obj):

        image = obj.package.images.filter(
            is_primary=True
        ).first()

        if not image:
            image = obj.package.images.first()

        if image:
            return image.image.url if hasattr(image.image, "url") else str(image.image)

        return None

    # ----------------------------------------------------
    # Completed Date
    # ----------------------------------------------------

    def get_completed_date(self, obj):

        if obj.completed_at:
            return obj.completed_at.strftime("%Y-%m-%d")

        if obj.updated_at:
            return obj.updated_at.strftime("%Y-%m-%d")

        return None

    # ----------------------------------------------------
    # Escrow
    # ----------------------------------------------------

    def get_escrow_status(self, obj):
        return WalletService.get_escrow_status(obj)

    # ----------------------------------------------------
    # Dispute Helpers
    # ----------------------------------------------------

    def _get_dispute(self, obj):
        """
        Booking -> OneToOne -> Dispute
        """

        return getattr(obj, "dispute", None)

    def get_has_dispute(self, obj):

        return self._get_dispute(obj) is not None

    def get_dispute_id(self, obj):

        dispute = self._get_dispute(obj)

        return str(dispute.id) if dispute else None

    def get_dispute_status(self, obj):

        dispute = self._get_dispute(obj)

        return dispute.status if dispute else None

    def get_dispute_status_display(self, obj):

        dispute = self._get_dispute(obj)

        return dispute.get_status_display() if dispute else None


class SenderBookingStatsSerializer(serializers.Serializer):
    pending_requests = serializers.IntegerField()
    active_bookings = serializers.IntegerField()
    completed_bookings = serializers.IntegerField()
    total_escrow_held = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
    )





class SenderDeliveryHistoryStatsSerializer(serializers.Serializer):
    completed = serializers.IntegerField()
    cancelled = serializers.IntegerField()
    refunded = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
    )
    total_paid = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
    )



from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from .models import (
    Booking,
    BookingPriceOffer,
    BookingPriceOfferStatus,
)


class BookingPriceOfferSerializer(
    serializers.ModelSerializer
):

    class Meta:
        model = BookingPriceOffer

        fields = [
            "id",
            "booking",
            "traveler",
            "offer_reward",
            "currency",
            "message",
            "status",
            "expires_at",
            "responded_at",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "booking",
            "traveler",
            "currency",
            "status",
            "expires_at",
            "responded_at",
            "created_at",
            "updated_at",
        ]

    def validate_offer_reward(self, value):

        if value <= Decimal("0"):
            raise serializers.ValidationError(
                "Offer reward must be greater than zero."
            )

        return value

    def validate(self, attrs):

        request = self.context["request"]
        booking = self.context["booking"]

        # -----------------------------------------
        # Only traveler can create offer
        # -----------------------------------------

        if booking.traveler_id != request.user.id:
            raise serializers.ValidationError(
                "Only the traveler can create a price offer."
            )

        # -----------------------------------------
        # Booking must still allow negotiation
        # -----------------------------------------

        if booking.status not in [
            BookingStatus.PENDING,
            BookingStatus.TRAVELER_ACCEPTED,
        ]:
            raise serializers.ValidationError(
                "Price negotiation is no longer available for this booking."
            )

        return attrs