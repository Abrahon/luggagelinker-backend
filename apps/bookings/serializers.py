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
        # ✅ FIXED ISSUE 4: Caught only expected validation errors.
        # Broad Exception block removed to allow unexpected system errors to bubble up naturally.
        except DjangoValidationError as e:
            raise serializers.ValidationError({"detail": e.message if hasattr(e, "message") else str(e)})