from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError
from apps.matching.models import Match
from .models import Booking
from .services import BookingService
from django.utils.translation import gettext_lazy as _
from apps.bookings.models import Booking, BookingStatus


# class BookingSerializer(serializers.ModelSerializer):
#     tracking_number = serializers.CharField(read_only=True)
#     package_title = serializers.CharField(source="package.title", read_only=True)
#     trip_title = serializers.CharField(source="trip.title", read_only=True)
#     sender_email = serializers.CharField(source="sender.email", read_only=True)
#     traveler_email = serializers.CharField(source="traveler.email", read_only=True)
    
#     match_id = serializers.UUIDField(write_only=True)

#     class Meta:
#         model = Booking
#         fields = [
#             "id",
#             "match_id",
#             "tracking_number",
#             "package_title",
#             "trip_title",
#             "sender_email",
#             "traveler_email",
#             "status",
#             "payment_status",
#             "agreed_reward",
#             "currency",
#             "agreed_weight_kg",
#             "expires_at",
#             "created_at",
#             "updated_at",
#         ]
#         read_only_fields = [
#             "id",
#             "status",
#             "payment_status",
#             "agreed_reward",
#             "currency",
#             "agreed_weight_kg",
#             "expires_at",
#             "created_at",
#             "updated_at",
#         ]




#     def validate_match_id(self, value):
#         if not Match.objects.filter(id=value).exists():
#             raise serializers.ValidationError(
#                 "The provided match instance does not exist."
#             )

#         return value
    

#     def create(self, validated_data):
#             """
#             Bridges the operation to the service layer, catching only expected clean exceptions.
#             """
#             match_id = validated_data["match_id"]
#             initiated_by = self.context["request"].user

#             try:
#                 return BookingService.create_booking_request(
#                     match_id=match_id, 
#                     initiated_by=initiated_by
#                 )
#             except DjangoValidationError as e:
#                 # 🟢 PRODUCTION FIX: Pass messages directly without manual dict nesting to prevent 500 crashes
#                 if hasattr(e, "message_dict"):
#                     raise serializers.ValidationError(e.message_dict)
#                 if hasattr(e, "messages"):
#                     # If there's only one message, extract it as a clean string error message
#                     raise serializers.ValidationError(e.messages[0] if len(e.messages) == 1 else e.messages)
#                 raise serializers.ValidationError(str(e))

from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError
from .models import Booking
from apps.matching.models import Match

from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError
from .models import Booking
from apps.matching.models import Match
from .services import BookingService  # Adjust import based on your project structure


class BookingSerializer(serializers.ModelSerializer):
    tracking_number = serializers.CharField(read_only=True)
    package_title = serializers.CharField(source="package.title", read_only=True)
    trip_title = serializers.CharField(source="trip.title", read_only=True)
    
    # 🟢 Sender Profile & Contact Details
    sender_name = serializers.SerializerMethodField()
    sender_email = serializers.CharField(source="sender.email", read_only=True)
    sender_profile_picture = serializers.SerializerMethodField()
    traveler_email = serializers.CharField(source="traveler.email", read_only=True)
    
    # 🟢 Route and Package Image details
    route = serializers.SerializerMethodField()
    package_image = serializers.SerializerMethodField()

    match_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = Booking
        fields = [
            "id",
            "match_id",
            "tracking_number",
            "package_title",
            "trip_title",
            "sender_name",
            "sender_email",
            "sender_profile_picture",
            "traveler_email",
            "route",
            "package_image",
            "status",
            "payment_status",
            "agreed_reward",
            "currency",
            "agreed_weight_kg",
            "expires_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "payment_status",
            "agreed_reward",
            "currency",
            "agreed_weight_kg",
            "expires_at",
            "created_at",
            "updated_at",
        ]

    def get_sender_name(self, obj) -> str:
        """Pulls the sender's name from their related Profile instance using the full_name property."""
        if not obj.sender:
            return ""

        if hasattr(obj.sender, "profile") and obj.sender.profile:
            name = obj.sender.profile.full_name
            if name:
                return name

        return getattr(obj.sender, "username", obj.sender.email)

    def get_sender_profile_picture(self, obj) -> str | None:
        """Pulls the sender's profile picture URL from Cloudinary if present."""
        if not obj.sender or not hasattr(obj.sender, "profile") or not obj.sender.profile:
            return None
            
        profile_picture = obj.sender.profile.profile_picture
        return profile_picture.url if profile_picture else None

    def get_route(self, obj) -> dict:
        """Extracts route details from the trip or falls back to package details."""
        trip = obj.trip
        if trip:
            return {
                "from_country": getattr(trip, "from_country", ""),
                "from_city": getattr(trip, "from_city", ""),
                "to_country": getattr(trip, "to_country", ""),
                "to_city": getattr(trip, "to_city", ""),
            }

        package = obj.package
        if package:
            return {
                "from_country": getattr(package, "from_country", ""),
                "from_city": getattr(package, "from_city", ""),
                "to_country": getattr(package, "to_country", ""),
                "to_city": getattr(package, "to_city", ""),
            }

        return {}

    def get_package_image(self, obj) -> str | None:
        """Fetches the primary or first image associated with the package."""
        if not obj.package:
            return None
        
        if hasattr(obj.package, "images"):
            primary_image = obj.package.images.filter(is_primary=True).first()
            if primary_image:
                return str(primary_image.image)
            
            first_image = obj.package.images.first()
            if first_image:
                return str(first_image.image)

        if hasattr(obj.package, "image") and obj.package.image:
            return str(obj.package.image)

        return None

    def validate_match_id(self, value):
        if not Match.objects.filter(id=value).exists():
            raise serializers.ValidationError(
                "The provided match instance does not exist."
            )
        return value

    def create(self, validated_data):
        match_id = validated_data["match_id"]
        initiated_by = self.context["request"].user

        try:
            return BookingService.create_booking_request(
                match_id=match_id, 
                initiated_by=initiated_by
            )
        except DjangoValidationError as e:
            if hasattr(e, "message_dict"):
                raise serializers.ValidationError(e.message_dict)
            if hasattr(e, "messages"):
                raise serializers.ValidationError(
                    e.messages[0] if len(e.messages) == 1 else e.messages
                )
            raise serializers.ValidationError(str(e))

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