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
from django.db import models


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
    RESOLVED = "RESOLVED", "Resolved"
    REJECTED = "REJECTED", "Rejected"


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
        help_text="Optional booking related to this report."
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

    def __str__(self):
        return f"{self.reporter.email} reported {self.reported_user.email}"

    def clean(self):
        if self.reporter == self.reported_user:
            from django.core.exceptions import ValidationError
            raise ValidationError("You cannot report yourself.")