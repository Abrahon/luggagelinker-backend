from django.db import models

# Create your models here.
import uuid

from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError


class Review(models.Model):
    """
    Production-grade model storing ratings and descriptive reviews submitted
    by booking senders regarding their assigned luggage travelers.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    booking = models.OneToOneField(
        "bookings.Booking",
        on_delete=models.CASCADE,
        related_name="traveler_review",
        help_text="The verified transactional booking linked to this specific rating execution."
    )

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="submitted_reviews",
        help_text="The cargo owner/sender who is writing the review evaluation."
    )

    traveler = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_reviews",
        help_text="The traveler whose delivery execution performance is being graded."
    )

    rating = models.PositiveSmallIntegerField(
        validators=[
            MinValueValidator(1),
            MaxValueValidator(5),
        ],
        help_text="Rating score out of 5 stars."
    )

    comment = models.TextField(
        max_length=1000,
        blank=True,
        help_text="Optional descriptive feedback outlining delivery context behavior."
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["-created_at"]

        verbose_name = "Review & Rating"
        verbose_name_plural = "Reviews & Ratings"

        constraints = [
            models.UniqueConstraint(
                fields=["booking", "sender"],
                name="unique_sender_booking_review",
            )
        ]

        indexes = [
            models.Index(fields=["sender"]),
            models.Index(fields=["traveler"]),
            models.Index(fields=["booking"]),
            models.Index(fields=["rating"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return (
            f"Review {self.id} | "
            f"Booking {self.booking.tracking_number} | "
            f"{self.rating}★"
        )

    def clean(self):
        super().clean()

        if self.booking.sender != self.sender:
            raise ValidationError(
                "Only the booking sender can submit this review."
            )

        if self.booking.traveler != self.traveler:
            raise ValidationError(
                "Selected traveler does not belong to this booking."
            )

        if self.booking.status != "COMPLETED":
            raise ValidationError(
                "Reviews can only be submitted after the booking is completed."
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


# report model
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from cloudinary.models import CloudinaryField


class ReportReason(models.TextChoices):
    SCAM = "SCAM", "Scam / Fraud"
    HARASSMENT = "HARASSMENT", "Harassment"
    ABUSE = "ABUSE", "Abusive Behaviour"
    FAKE_IDENTITY = "FAKE_IDENTITY", "Fake Identity"
    OFF_PLATFORM_PAYMENT = "OFF_PLATFORM_PAYMENT", "Requested Off-platform Payment"
    INAPPROPRIATE_BEHAVIOR = "INAPPROPRIATE_BEHAVIOR", "Inappropriate Behaviour"
    OTHER = "OTHER", "Other"


class ReportStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    UNDER_REVIEW = "UNDER_REVIEW", "Under Review"
    ESCALATED = "ESCALATED", "Escalated"
    RESOLVED = "RESOLVED", "Resolved"
    REJECTED = "REJECTED", "Rejected"


class ActionTaken(models.TextChoices):
    NONE = "NONE", "No Action"
    WARNING = "WARNING", "Issue Warning"
    REMOVE_LISTING = "REMOVE_LISTING", "Remove Listing / Booking"
    SUSPEND = "SUSPEND", "Suspend Account"
    PERMANENT_BAN = "PERMANENT_BAN", "Permanent Ban"


class UserModerationProfile(models.Model):
    """
    Tracks safety metrics, moderation history, suspensions, bans, 
    and a dynamic trust score for each user.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="moderation_profile",
    )
    
    # Report tracking caches
    reports_received = models.PositiveIntegerField(
        default=0,
        help_text="Total number of reports submitted against this user."
    )
    valid_reports = models.PositiveIntegerField(
        default=0,
        help_text="Number of reports confirmed as valid by an admin."
    )
    warning_count = models.PositiveIntegerField(default=0)
    last_reported_at = models.DateTimeField(null=True, blank=True)

    # Dynamic Trust Score (0 to 100)
    trust_score = models.PositiveSmallIntegerField(
        default=100,
        help_text="Flexible score (0-100) used for ranking and match priority."
    )

    # Suspension tracking
    is_suspended = models.BooleanField(default=False)
    suspended_until = models.DateTimeField(null=True, blank=True)

    # Permanent Ban tracking
    is_banned = models.BooleanField(default=False)
    banned_at = models.DateTimeField(null=True, blank=True)
    ban_reason = models.TextField(blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Moderation Profile for {self.user.email} (Trust Score: {self.trust_score})"

    def check_suspension_status(self):
        """Auto-release temporary suspension if the duration has expired."""
        if self.is_suspended and self.suspended_until:
            if timezone.now() >= self.suspended_until:
                self.is_suspended = False
                self.suspended_until = None
                self.save(update_fields=["is_suspended", "suspended_until"])
        return self.is_suspended


class Report(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="submitted_reports",
    )
    reported_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_reports",
    )
    booking = models.ForeignKey(
        "bookings.Booking",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reports",
        help_text="Optional booking related to this report.",
    )
    reason = models.CharField(
        max_length=50,
        choices=ReportReason.choices,
    )
    description = models.TextField(
        max_length=2000,
    )
    status = models.CharField(
        max_length=30,
        choices=ReportStatus.choices,
        default=ReportStatus.PENDING,
    )
    is_valid = models.BooleanField(
        null=True,
        blank=True,
        help_text="Admin decision on whether this report is genuine/valid.",
    )
    action_taken = models.CharField(
        max_length=30,
        choices=ActionTaken.choices,
        default=ActionTaken.NONE,
    )
    assigned_admin = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_reports",
    )
    admin_notes = models.TextField(
        blank=True,
    )
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["reporter"]),
            models.Index(fields=["reported_user"]),
            models.Index(fields=["booking"]),
            models.Index(fields=["created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["reporter", "reported_user", "booking"],
                name="unique_booking_report",
                condition=models.Q(booking__isnull=False),
            )
        ]

    def __str__(self):
        return f"{self.reporter.email} reported {self.reported_user.email} ({self.status})"

    def clean(self):
        if self.reporter == self.reported_user:
            raise ValidationError("You cannot report yourself.")


class ReportEvidence(models.Model):
    """
    Stores evidence file uploads associated with a report using Cloudinary.
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    report = models.ForeignKey(
        Report,
        on_delete=models.CASCADE,
        related_name="evidence_files",
    )
    file = CloudinaryField(
        "report_evidence",
        folder="reports",
        resource_type="auto",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Evidence {self.id} for Report {self.report.id}"