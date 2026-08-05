from rest_framework import serializers
from .models import Review

from django.db import transaction
from django.utils import timezone
from .models import (
    ReportStatus,
    ActionTaken,
)


from apps.bookings.models import BookingStatus

from .models import (
    Report,
    ReportEvidence,
    UserModerationProfile,
)
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







from .models import ReportEvidence


class ReportEvidenceSerializer(serializers.ModelSerializer):

    file = serializers.SerializerMethodField()

    class Meta:
        model = ReportEvidence
        fields = [
            "id",
            "file",
            "uploaded_at",
        ]

    def get_file(self, obj):
        if obj.file:
            return obj.file.url
        return None


from rest_framework import serializers

from .models import UserModerationProfile


class UserModerationProfileSerializer(serializers.ModelSerializer):

    class Meta:
        model = UserModerationProfile

        fields = [
            "reports_received",
            "valid_reports",
            "warning_count",
            "trust_score",
            "is_suspended",
            "suspended_until",
            "is_banned",
            "banned_at",
            "ban_reason",
        ]

        read_only_fields = fields





class CreateReportSerializer(serializers.ModelSerializer):

    evidence_files = serializers.ListField(
        child=serializers.FileField(),
        required=False,
        write_only=True,
    )

    class Meta:
        model = Report

        fields = [
            "reported_user",
            "booking",
            "reason",
            "description",
            "evidence_files",
        ]

    def validate_description(self, value):

        value = value.strip()

        if len(value) < 15:
            raise serializers.ValidationError(
                "Please provide at least 15 characters."
            )

        return value

    def validate(self, attrs):

        request = self.context["request"]

        reporter = request.user

        booking = attrs.get("booking")

        reported_user = attrs["reported_user"]

        if reporter == reported_user:
            raise serializers.ValidationError(
                {
                    "reported_user":
                    "You cannot report yourself."
                }
            )

        if booking:

            if booking.status not in [
                BookingStatus.DELIVERED,
                BookingStatus.COMPLETED,
            ]:
                raise serializers.ValidationError(
                    {
                        "booking":
                        "Reports can only be submitted after the package has been delivered."
                    }
                )

            if reporter not in [
                booking.sender,
                booking.traveler,
            ]:
                raise serializers.ValidationError(
                    {
                        "booking":
                        "You are not associated with this booking."
                    }
                )

            if reported_user not in [
                booking.sender,
                booking.traveler,
            ]:
                raise serializers.ValidationError(
                    {
                        "reported_user":
                        "Reported user is not associated with this booking."
                    }
                )

            if (
                reporter == booking.sender
                and
                reported_user != booking.traveler
            ):
                raise serializers.ValidationError(
                    {
                        "reported_user":
                        "You can only report the assigned traveler."
                    }
                )

            if (
                reporter == booking.traveler
                and
                reported_user != booking.sender
            ):
                raise serializers.ValidationError(
                    {
                        "reported_user":
                        "You can only report the package sender."
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

    @transaction.atomic
    def create(self, validated_data):

        files = validated_data.pop(
            "evidence_files",
            [],
        )

        reporter = self.context["request"].user

        report = Report.objects.create(
            reporter=reporter,
            **validated_data,
        )

        for file in files:

            ReportEvidence.objects.create(
                report=report,
                file=file,
            )

        moderation, _ = (
            UserModerationProfile.objects.get_or_create(
                user=report.reported_user,
            )
        )

        moderation.reports_received += 1

        moderation.last_reported_at = timezone.now()

        moderation.save(
            update_fields=[
                "reports_received",
                "last_reported_at",
            ]
        )

        return report






class ReportSerializer(serializers.ModelSerializer):

    reporter_name = serializers.CharField(
        source="reporter.profile.full_name",
        read_only=True,
    )

    reported_user_name = serializers.CharField(
        source="reported_user.profile.full_name",
        read_only=True,
    )

    class Meta:
        model = Report

        fields = [
            "id",
            "reason",
            "status",
            "action_taken",
            "reporter_name",
            "reported_user_name",
            "created_at",
        ]

class ReportDetailSerializer(serializers.ModelSerializer):

    reporter_name = serializers.CharField(
        source="reporter.profile.full_name",
        read_only=True,
    )

    reported_user_name = serializers.CharField(
        source="reported_user.profile.full_name",
        read_only=True,
    )

    evidence_files = ReportEvidenceSerializer(
        many=True,
        read_only=True,
    )

    moderation = UserModerationProfileSerializer(
        source="reported_user.moderation_profile",
        read_only=True,
    )

    class Meta:

        model = Report

        fields = [
            "id",
            "reporter_name",
            "reported_user_name",
            "booking",
            "reason",
            "description",
            "status",
            "is_valid",
            "action_taken",
            "admin_notes",
            "evidence_files",
            "moderation",
            "resolved_at",
            "created_at",
            "updated_at",
        ]





class AdminResolveReportSerializer(serializers.Serializer):

    status = serializers.ChoiceField(
        choices=[
            ReportStatus.UNDER_REVIEW,
            ReportStatus.RESOLVED,
            ReportStatus.REJECTED,
            ReportStatus.ESCALATED,
        ]
    )

    is_valid = serializers.BooleanField()

    action_taken = serializers.ChoiceField(
        choices=ActionTaken.choices,
        default=ActionTaken.NONE,
    )

    trust_score = serializers.IntegerField(
        required=False,
        min_value=0,
        max_value=100,
    )

    suspension_days = serializers.IntegerField(
        required=False,
        min_value=1,
    )

    admin_notes = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    ban_reason = serializers.CharField(
        required=False,
        allow_blank=True,
    )