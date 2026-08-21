from django.db import models

# Create your models here.
import uuid

from django.conf import settings
from django.db import models

from apps.bookings.models import Booking

from .enums import (
    NegotiationStatus,
    OfferStatus,
)


class Negotiation(models.Model):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    booking = models.OneToOneField(
        Booking,
        on_delete=models.CASCADE,
        related_name="negotiation",
    )

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sender_negotiations",
    )

    traveler = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="traveler_negotiations",
    )

    original_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    agreed_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    currency = models.CharField(
        max_length=10,
    )

    status = models.CharField(
        max_length=20,
        choices=NegotiationStatus.choices,
        default=NegotiationStatus.ACTIVE,
    )

    started_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "negotiations"

    def __str__(self):

        return (
            f"Negotiation {self.id} "
            f"- Booking {self.booking_id}"
        )