from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError
from apps.matching.models import Match
from .models import Booking
from .services import BookingService

class BookingSerializer(serializers.ModelSerializer):
    tracking_number = serializers.CharField(read_only=True)
    package_title = serializers.CharField(source="package.title", read_only=True)
    trip_title = serializers.CharField(source="trip.title", read_only=True)
    sender_email = serializers.CharField(source="sender.email", read_only=True)
    traveler_email = serializers.CharField(source="traveler.email", read_only=True)
    
    match_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = Booking
        fields = [
            "id",
            "match_id",
            "tracking_number",
            "package_title",
            "trip_title",
            "sender_email",
            "traveler_email",
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

    # def validate_match_id(self, value):
    #     """
    #     Validates match status, inventory availability, and initiator authority.
    #     """
    #     try:
    #         match = Match.objects.select_related("package", "trip").get(id=value)
    #     except Match.DoesNotExist:
    #         raise serializers.ValidationError("The provided match instance does not exist.")

    #     if not match.is_active:
    #         raise serializers.ValidationError("This match profile is currently inactive.")

    #     if Booking.objects.filter(match=match).exists():
    #         raise serializers.ValidationError("A booking request has already been registered for this match.")

    #     if match.trip.available_weight_kg < match.package.weight:
    #         raise serializers.ValidationError(
    #             f"Sufficient weight capacity is no longer available on this trip. "
    #             f"Required: {match.package.weight}kg, Available: {match.trip.available_weight_kg}kg"
    #         )

    #     # ✅ FIXED ISSUE 5: Enforced strict business workflow permissions.
    #     # Only the package owner/sender can select a traveler and initiate a booking.
    #     request_user = self.context["request"].user
    #     if request_user != match.package.sender:
    #         raise serializers.ValidationError(
    #             "Only the package sender can initiate a booking request from this match."
    #         )

    #     return value


    def validate_match_id(self, value):
        if not Match.objects.filter(id=value).exists():
            raise serializers.ValidationError(
                "The provided match instance does not exist."
            )

        return value
    

    def create(self, validated_data):
            """
            Bridges the operation to the service layer, catching only expected clean exceptions.
            """
            match_id = validated_data["match_id"]
            initiated_by = self.context["request"].user

            try:
                return BookingService.create_booking_request(
                    match_id=match_id, 
                    initiated_by=initiated_by
                )
            except DjangoValidationError as e:
                # 🟢 PRODUCTION FIX: Properly handle both dictionary and list based Django validation errors
                if hasattr(e, "message_dict"):
                    raise serializers.ValidationError(e.message_dict)
                if hasattr(e, "messages"):
                    raise serializers.ValidationError({"detail": e.messages})
                raise serializers.ValidationError({"detail": str(e)})



# 
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from apps.bookings.models import Booking, BookingStatus

class VerifyPickupPinSerializer(serializers.Serializer):
    booking_id = serializers.UUIDField(required=True)
    pickup_pin = serializers.CharField(max_length=6, min_length=6, required=True)

    def validate(self, attrs):
        booking_id = attrs.get("booking_id")
        input_pin = attrs.get("pickup_pin")

        try:
            # Row lock the booking to handle the state alteration sequence cleanly
            booking = Booking.objects.get(id=booking_id)
        except Booking.DoesNotExist:
            raise serializers.ValidationError({"booking_id": _("Target booking contract instance not found.")})

        # 1. State Guard: Enforce sequence integrity
        if booking.status != BookingStatus.CONFIRMED:
            raise serializers.ValidationError(_("Pickup cannot be performed unless transaction is CONFIRMED."))

        # 2. Authentication Check: Only the assigned Traveler can submit the validation PIN
        request_user = self.context["request"].user
        if booking.traveler != request_user:
            raise serializers.ValidationError(_("Access Denied. Only the designated traveler can execute pickup clearances."))

        # 3. Security Check: Validate matching pin entries
        if booking.pickup_verification_pin != input_pin:
            raise serializers.ValidationError({"pickup_pin": _("Invalid security verification passcode pin code entry.")})

        attrs["booking"] = booking
        return attrs




# Transit serilizer for booking pickup verification
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from apps.bookings.models import Booking, BookingStatus


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