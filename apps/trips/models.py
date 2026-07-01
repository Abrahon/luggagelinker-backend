from django.db import models

# Create your models here.
import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from decimal import Decimal
from django.core.exceptions import ValidationError
from decimal import Decimal


class TripStatus(models.TextChoices):
    PLANNED = "PLANNED", "Planned"
    ACTIVE = "ACTIVE", "Active"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"


class Trip(models.Model):

    # =========================
    # BASIC INFO
    # =========================
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    traveler = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="trips",
    )

    title = models.CharField(
        max_length=200,
    )

    description = models.TextField(
        blank=True,
        null=True,
    )

    # =========================
    # ROUTE INFO
    # =========================
    from_country = models.CharField(max_length=100)
    from_city = models.CharField(max_length=100)

    to_country = models.CharField(max_length=100)
    to_city = models.CharField(max_length=100)

    # =========================
    # DATE INFO
    # =========================
    departure_date = models.DateField()
    arrival_date = models.DateField()

    # =========================
    # CAPACITY (VERY IMPORTANT)
    # =========================
    max_weight_kg = models.DecimalField(
        max_digits=6,
        decimal_places=2,
    )

    available_weight_kg = models.DecimalField(
        max_digits=6,
        decimal_places=2,
    )

    # =========================
    # PAYMENT EXPECTATION
    # =========================
    reward_per_kg = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
    )

    currency = models.CharField(
        max_length=10,
        default="USD",
    )

    # =========================
    # STATUS
    # =========================
    status = models.CharField(
        max_length=20,
        choices=TripStatus.choices,
        default=TripStatus.PLANNED,
    )

    is_active = models.BooleanField(
        default=True,
    )

    is_public = models.BooleanField(
        default=True,
    )

    # =========================
    # SYSTEM FIELDS
    # =========================
    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = "trips"
        ordering = ["-created_at"]

        indexes = [
            models.Index(fields=["traveler"]),
            models.Index(fields=["from_city"]),
            models.Index(fields=["to_city"]),
            models.Index(fields=["departure_date"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.traveler.email} | {self.from_city} → {self.to_city}"

    # =========================
    # BUSINESS LOGIC
    # =========================
    @property
    def is_available(self):
        return (
            self.status == TripStatus.ACTIVE
            and self.is_active
            and self.available_weight_kg > 0
        )


    def reduce_capacity(self, weight):

        weight = Decimal(weight)

        if weight <= 0:
            raise ValidationError(
                "Weight must be greater than zero."
            )

        if weight > self.available_weight_kg:
            raise ValidationError(
                "Not enough available luggage capacity."
            )

        self.available_weight_kg -= weight

        self.save(update_fields=["available_weight_kg"])
    


# restore capacity after cancelled booking

    def restore_capacity(self, weight):

        weight = Decimal(weight)

        self.available_weight_kg += weight

        if self.available_weight_kg > self.max_weight_kg:
            self.available_weight_kg = self.max_weight_kg

        self.save(update_fields=["available_weight_kg"])