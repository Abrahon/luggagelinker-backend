from rest_framework import serializers
from .models import Review
# Assuming your Booking model is accessible like this, adjust if necessary
# from bookings.models import Booking 

class ReviewSerializer(serializers.ModelSerializer):
    # Read-only fields to prevent tampering during creation
    id = serializers.UUIDField(read_only=True)
    sender = serializers.PrimaryKeyRelatedField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Review
        fields = [
            'id',
            'booking',
            'sender',
            'traveler',
            'rating',
            'comment',
            'created_at',
            'updated_at',
        ]

    def validate(self, attrs):
        """
        Object-level validation to enforce business rules before database hits.
        """
        # 1. Fetch the sender from the request context
        request = self.context.get('request')
        if not request or not request.user:
            raise serializers.ValidationError(
                {"detail": "Authentication credentials were not provided."}
            )
        
        sender = request.user
        booking = attrs.get('booking')
        traveler = attrs.get('traveler')

        # If performing an update, partial data might be passed
        if self.instance:
            booking = booking or self.instance.booking
            traveler = traveler or self.instance.traveler
            sender = self.instance.sender  # Senders shouldn't change on update

        # 2. Verify that the sender owns the booking
        if booking.sender != sender:
            raise serializers.ValidationError(
                {"booking": "Only the verified booking sender can submit this review."}
            )

        # 3. Verify that the traveler matches the booking
        if booking.traveler != traveler:
            raise serializers.ValidationError(
                {"traveler": "The selected traveler does not match the traveler assigned to this booking."}
            )

        # 4. Verify booking completion status
        # Note: If your status field is a ChoiceField/Enum, ensure 'COMPLETED' matches exactly
        if booking.status != "COMPLETED":
            raise serializers.ValidationError(
                {"booking": "Reviews can only be submitted after the booking has been marked as COMPLETED."}
            )

        # 5. Check for UniqueConstraint on creation
        if not self.instance:
            if Review.objects.filter(booking=booking, sender=sender).exists():
                raise serializers.ValidationError(
                    {"booking": "You have already submitted a review for this booking."}
                )

        return attrs

    def create(self, validated_data):
        """
        Inject the authenticated request user as the sender automatically.
        """
        validated_data['sender'] = self.context['request'].user
        return super().create(validated_data)




from rest_framework import serializers
from django.utils import timezone

from .models import Report
from apps.bookings.models import Booking


class ReportSerializer(serializers.ModelSerializer):
    reporter_email = serializers.ReadOnlyField(source="reporter.email")
    reported_user_email = serializers.ReadOnlyField(source="reported_user.email")
    reason_display = serializers.CharField(source="get_reason_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Report
        fields = [
            "id",
            "reporter",
            "reporter_email",
            "reported_user",
            "reported_user_email",
            "booking",
            "reason",
            "reason_display",
            "description",
            "status",
            "status_display",
            "assigned_admin",
            "admin_notes",
            "resolved_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = (
            "id",
            "reporter",
            "status",
            "assigned_admin",
            "admin_notes",
            "resolved_at",
            "created_at",
            "updated_at",
        )


class CreateReportSerializer(serializers.ModelSerializer):

    class Meta:
        model = Report
        fields = (
            "reported_user",
            "booking",
            "reason",
            "description",
        )

    def validate_description(self, value):
        value = value.strip()

        if len(value) < 15:
            raise serializers.ValidationError(
                "Please provide a detailed description (minimum 15 characters)."
            )

        return value

    def validate(self, attrs):

        request = self.context["request"]
        reporter = request.user

        reported_user = attrs["reported_user"]
        booking = attrs.get("booking")

        if reporter == reported_user:
            raise serializers.ValidationError(
                {"reported_user": "You cannot report yourself."}
            )

        if booking:

            if booking.status != "COMPLETED":
                raise serializers.ValidationError(
                    {
                        "booking": "Reports can only be submitted for completed bookings."
                    }
                )

            if reporter not in [booking.sender, booking.traveler]:
                raise serializers.ValidationError(
                    {
                        "booking": "You are not associated with this booking."
                    }
                )

            if reported_user not in [booking.sender, booking.traveler]:
                raise serializers.ValidationError(
                    {
                        "reported_user": "Reported user is not part of this booking."
                    }
                )

            if reporter == booking.sender and reported_user != booking.traveler:
                raise serializers.ValidationError(
                    {
                        "reported_user": "Sender can only report the assigned traveler."
                    }
                )

            if reporter == booking.traveler and reported_user != booking.sender:
                raise serializers.ValidationError(
                    {
                        "reported_user": "Traveler can only report the sender."
                    }
                )

        exists = Report.objects.filter(
            reporter=reporter,
            reported_user=reported_user,
            booking=booking,
        ).exists()

        if exists:
            raise serializers.ValidationError(
                "You have already submitted a report for this booking."
            )

        return attrs

    def create(self, validated_data):
        validated_data["reporter"] = self.context["request"].user
        return super().create(validated_data)