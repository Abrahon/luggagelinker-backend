from django.db import models

# Create your models here.
import uuid
import string
import random
from datetime import timedelta
from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from apps.packages.models import Package
from apps.trips.models import Trip
from apps.matching.models import Match

class BookingStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    TRAVELER_ACCEPTED = "TRAVELER_ACCEPTED", "Traveler Accepted"
    PAYMENT_PENDING = "PAYMENT_PENDING", "Payment Pending"
    CONFIRMED = "CONFIRMED", "Confirmed"
    PICKED_UP = "PICKED_UP", "Picked Up"
    IN_TRANSIT = "IN_TRANSIT", "In Transit"
    DELIVERED = "DELIVERED", "Delivered"
    COMPLETED = "COMPLETED", "Completed"
    REJECTED = "REJECTED", "Rejected"
    CANCELLED = "CANCELLED", "Cancelled"
    EXPIRED = "EXPIRED", "Expired"

class PaymentStatus(models.TextChoices):
    UNPAID = "UNPAID", "Unpaid"
    PENDING = "PENDING", "Pending"
    PAID = "PAID", "Paid"
    REFUNDED = "REFUNDED", "Refunded"
    

class Booking(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tracking_number = models.CharField(max_length=30, unique=True, editable=False)

    # Relations
    match = models.OneToOneField(Match, on_delete=models.PROTECT, related_name="booking")
    package = models.ForeignKey(Package, on_delete=models.PROTECT, related_name="bookings")
    trip = models.ForeignKey(Trip, on_delete=models.PROTECT, related_name="bookings")

    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sent_bookings")
    traveler = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="travel_bookings")

    # Status & Snapshots
    status = models.CharField(max_length=30, choices=BookingStatus.choices, default=BookingStatus.PENDING)
    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID)

    agreed_reward = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default="USD")
    agreed_weight_kg = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    # Pins
    pickup_verification_pin = models.CharField(max_length=6, editable=False, blank=True)
    delivery_verification_pin = models.CharField(max_length=6, editable=False, blank=True)

    # Expirations & Analytical Timestamps
    expires_at = models.DateTimeField(null=True, blank=True)
    traveler_accepted_at = models.DateTimeField(null=True, blank=True)
    payment_received_at = models.DateTimeField(null=True, blank=True)
    
    confirmed_at = models.DateTimeField(null=True, blank=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    in_transit_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="cancelled_bookings")
    cancellation_reason = models.TextField(blank=True, null=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "bookings"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.tracking_number} | {self.status}"

    def clean(self):
        if self.package != self.match.package or self.trip != self.match.trip:
            raise ValidationError("Package or Trip does not match with the linked Match instance.")
        if self.sender == self.traveler:
            raise ValidationError("Sender and Traveler cannot be the same user.")

    def generate_tracking_number(self):
        chars = string.ascii_uppercase + string.digits
        current_year = timezone.now().year
        while True:
            random_code = "".join(random.choices(chars, k=8))
            tracking = f"LL-{current_year}-{random_code}"
            if not Booking.objects.filter(tracking_number=tracking).exists():
                return tracking

    def save(self, *args, **kwargs):
        # ✅ BUG 1 FIXED: Clean condition checking handling fallback initialization
        if not self.tracking_number:
            self.tracking_number = self.generate_tracking_number()
            self.pickup_verification_pin = "".join(random.choices(string.digits, k=6))
            self.delivery_verification_pin = "".join(random.choices(string.digits, k=6))
            
        # ✅ BUG 2 FIXED: Tight 20-minute expiry window for interactive operations
        if self.expires_at is None:
            self.expires_at = timezone.now() + timedelta(minutes=20)
            
        if self.agreed_weight_kg is None and self.package is not None:
            self.agreed_weight_kg = self.package.weight

        self.full_clean()
        super().save(*args, **kwargs)