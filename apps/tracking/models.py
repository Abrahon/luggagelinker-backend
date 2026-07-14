from django.db import models

# Create your models here.
import uuid

from django.conf import settings
from django.db import models

from apps.chat.models import ChatRoom


class TrackingStatus(models.TextChoices):
    STARTED = "STARTED", "Started"
    PAUSED = "PAUSED", "Paused"
    COMPLETED = "COMPLETED", "Completed"


class ActiveTracker(models.Model):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    room = models.OneToOneField(
        ChatRoom,
        on_delete=models.CASCADE,
        related_name="tracker",
    )

    tracker_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="active_trackers",
    )

    current_lat = models.FloatField(
        null=True,
        blank=True,
    )

    current_lng = models.FloatField(
        null=True,
        blank=True,
    )

    destination_lat = models.FloatField()

    destination_lng = models.FloatField()

    speed = models.FloatField(
        default=0,
    )

    heading = models.FloatField(
        default=0,
    )

    accuracy = models.FloatField(
        null=True,
        blank=True,
    )

    altitude = models.FloatField(
        null=True,
        blank=True,
    )

    distance_remaining_km = models.FloatField(
        default=0,
    )

    eta_minutes = models.PositiveIntegerField(
        default=0,
    )

    status = models.CharField(
        max_length=20,
        choices=TrackingStatus.choices,
        default=TrackingStatus.STARTED,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:

        ordering = [
            "-updated_at",
        ]

        indexes = [
            models.Index(fields=["room"]),
            models.Index(fields=["tracker_user"]),
            models.Index(fields=["updated_at"]),
        ]

    def __str__(self):

        return f"{self.room_id}"
    


class LocationHistory(models.Model):

    tracker = models.ForeignKey(
        ActiveTracker,
        on_delete=models.CASCADE,
        related_name="history",
    )

    latitude = models.FloatField()

    longitude = models.FloatField()

    speed = models.FloatField(
        default=0,
    )

    heading = models.FloatField(
        default=0,
    )

    accuracy = models.FloatField(
        null=True,
        blank=True,
    )

    altitude = models.FloatField(
        null=True,
        blank=True,
    )

    recorded_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:

        ordering = [
            "recorded_at",
        ]

        indexes = [
            models.Index(
                fields=[
                    "tracker",
                    "recorded_at",
                ]
            ),
        ]