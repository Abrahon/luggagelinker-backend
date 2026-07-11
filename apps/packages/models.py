from django.db import models

# Create your models here.
import uuid

from django.conf import settings
from django.db import models


import uuid
from django.conf import settings
from django.db import models


class PackageStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    PUBLISHED = "PUBLISHED", "Published"
    MATCHED = "MATCHED", "Matched"
    BOOKED = "BOOKED", "Booked"
    IN_TRANSIT = "IN_TRANSIT", "In Transit"
    DELIVERED = "DELIVERED", "Delivered"
    CANCELLED = "CANCELLED", "Cancelled"
    EXPIRED = "EXPIRED", "Expired"


class PackageCategory(models.TextChoices):
    DOCUMENT = "DOCUMENT", "Document"
    ELECTRONICS = "ELECTRONICS", "Electronics"
    CLOTHING = "CLOTHING", "Clothing"
    FOOD = "FOOD", "Food"
    MEDICINE = "MEDICINE", "Medicine"
    COSMETICS = "COSMETICS", "Cosmetics"
    BOOKS = "BOOKS", "Books"
    OTHER = "OTHER", "Other"


class VerificationStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    AUTO_APPROVED = "AUTO_APPROVED", "Auto Approved"
    VERIFIED = "VERIFIED", "Admin Verified"  
    MANUAL_REVIEW = "MANUAL_REVIEW", "Manual Review"
    REJECTED = "REJECTED", "Rejected"


class RiskRule(models.Model):
    """
    Dynamic Risk Parameters configurable by Admins via Django Admin.
    Allows changing weights for categories or thresholds without changing code.
    """
    category = models.CharField(max_length=30, choices=PackageCategory.choices, unique=True)
    base_risk_score = models.IntegerField(default=0)
    requires_receipt_above = models.DecimalField(max_digits=10, decimal_places=2, default=500.00)

    class Meta:
        db_table = "package_risk_rules"

    def __str__(self):
        return f"{self.category} Rule (+{self.base_risk_score})"


class Package(models.Model):
    # --- ORIGINAL STRUCTURAL FIELDS ---
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="packages")
    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.CharField(max_length=30, choices=PackageCategory.choices)
    weight = models.DecimalField(max_digits=6, decimal_places=2, help_text="Weight in KG")
    declared_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    reward_amount = models.DecimalField(max_digits=10, decimal_places=2, help_text="Amount sender will pay traveler")
    currency = models.CharField(max_length=10, default="USD")
    
    pickup_country = models.CharField(max_length=100)
    pickup_city = models.CharField(max_length=100)
    pickup_address = models.TextField()
    destination_country = models.CharField(max_length=100)
    destination_city = models.CharField(max_length=100)
    destination_address = models.TextField()
    
    pickup_date = models.DateField()
    latest_delivery_date = models.DateField()
    is_fragile = models.BooleanField(default=False)
    requires_signature = models.BooleanField(default=False)
    is_public = models.BooleanField(default=True)
    status = models.CharField(max_length=20, choices=PackageStatus.choices, default=PackageStatus.DRAFT)
    is_active = models.BooleanField(default=True)

    # --- ENHANCED RISK MANAGEMENT FIELDS ---
    declared_as_legal = models.BooleanField(default=False)
    terms_accepted = models.BooleanField(default=False)
    verification_status = models.CharField(max_length=20, choices=VerificationStatus.choices, default=VerificationStatus.PENDING)
    risk_score = models.IntegerField(default=0)
    
    # Clean Split File Validation Inputs
    purchase_receipt = models.FileField(upload_to="package_receipts/", blank=True, null=True)
    serial_number = models.CharField(max_length=100, blank=True, null=True)
    imei = models.CharField(max_length=15, blank=True, null=True)
    
    # Handshake Hand-off Control Properties
    traveler_matches_listing = models.BooleanField(null=True, blank=True)
    traveler_refusal_reason = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "packages"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["sender"]),
            models.Index(fields=["status"]),
            models.Index(fields=["verification_status"]),
            models.Index(fields=["risk_score"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.verification_status})"



class PackageImage(models.Model):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    package = models.ForeignKey(
        Package,
        on_delete=models.CASCADE,
        related_name="images",
    )

    image = models.URLField()

    is_primary = models.BooleanField(
        default=False,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        db_table = "package_images"

    def __str__(self):
        return self.package.title