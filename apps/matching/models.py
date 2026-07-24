from django.db import models

# Create your models here.
import uuid

from django.db import models


class MatchStatus(models.TextChoices):
    AVAILABLE = "AVAILABLE", "Available"
    REQUESTED = "REQUESTED", "Requested"
    ACCEPTED = "ACCEPTED", "Accepted"
    REJECTED = "REJECTED", "Rejected"
    EXPIRED = "EXPIRED", "Expired"


class Match(models.Model):

    # ==========================================================
    # BASIC INFO
    # ==========================================================

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    package = models.ForeignKey(
        "packages.Package",
        on_delete=models.CASCADE,
        related_name="matches",
    )

    trip = models.ForeignKey(
        "trips.Trip",
        on_delete=models.CASCADE,
        related_name="matches",
    )

    # ==========================================================
    # MATCH SCORE
    # ==========================================================

    score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
    )

    # ==========================================================
    # STATUS
    # ==========================================================

    status = models.CharField(
        max_length=20,
        choices=MatchStatus.choices,
        default=MatchStatus.AVAILABLE,
    )

    # ==========================================================
    # SYSTEM
    # ==========================================================

    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:

        db_table = "matches"

        ordering = [
            "-score",
            "-created_at",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "package",
                    "trip",
                ],
                name="unique_package_trip_match",
            )
        ]

        indexes = [
            models.Index(fields=["package"]),
            models.Index(fields=["trip"]),
            models.Index(fields=["status"]),
            models.Index(fields=["score"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):

        return (
            f"{self.package.title} ↔ "
            f"{self.trip.title} "
            f"({self.score})"
        )