from django.db import models

# Create your models here.
import uuid

from django.conf import settings
from django.db import models


class NotificationType(models.TextChoices):

    MATCH = "MATCH", "Match"
    REQUEST = "REQUEST", "Request"
    BOOKING = "BOOKING", "Booking"
    DELIVERY = "DELIVERY", "Delivery"
    PAYMENT = "PAYMENT", "Payment"
    WALLET = "WALLET", "Wallet"
    REVIEW = "REVIEW", "Review"
    CHAT = "CHAT", "Chat"
    SYSTEM = "SYSTEM", "System"


class Notification(models.Model):

    # ==========================================================
    # BASIC INFO
    # ==========================================================

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )

    # ==========================================================
    # CONTENT
    # ==========================================================

    title = models.CharField(
        max_length=255,
    )

    message = models.TextField()

    notification_type = models.CharField(
        max_length=30,
        choices=NotificationType.choices,
        default=NotificationType.SYSTEM,
    )

    # ==========================================================
    # OPTIONAL LINKING
    # ==========================================================

    object_id = models.UUIDField(
        null=True,
        blank=True,
    )

    action_url = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    # ==========================================================
    # STATUS
    # ==========================================================

    is_read = models.BooleanField(
        default=False,
    )

    is_active = models.BooleanField(
        default=True,
    )

    # ==========================================================
    # TIMESTAMPS
    # ==========================================================

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:

        db_table = "notifications"

        ordering = [
            "-created_at",
        ]

        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["notification_type"]),
            models.Index(fields=["is_read"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):

        return f"{self.user.email} - {self.title}"