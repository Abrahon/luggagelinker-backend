from django.db import models

# Create your models here.
import uuid

from cloudinary.models import CloudinaryField
from django.db import models

from apps.accounts.models import User


class KYCStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    UNDER_REVIEW = "under_review", "Under Review"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class IDType(models.TextChoices):
    NATIONAL_ID = "national_id", "National ID"
    PASSPORT = "passport", "Passport"
    DRIVING_LICENSE = "driving_license", "Driving License"


class KYC(models.Model):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="kyc",
    )

    # -----------------------------
    # Identity
    # -----------------------------
    id_type = models.CharField(
        max_length=30,
        choices=IDType.choices,
    )

    id_number = models.CharField(
        max_length=100,
    )

    date_of_birth = models.DateField()

    # -----------------------------
    # Documents
    # -----------------------------
    document_front = CloudinaryField(
        "kyc/document_front",
        blank=True,
        null=True,
    )

    document_back = CloudinaryField(
        "kyc/document_back",
        blank=True,
        null=True,
    )

    selfie = CloudinaryField(
        "kyc/selfie",
        blank=True,
        null=True,
    )

    # -----------------------------
    # Verification
    # -----------------------------
    status = models.CharField(
        max_length=20,
        choices=KYCStatus.choices,
        default=KYCStatus.PENDING,
    )

    rejection_reason = models.TextField(
        blank=True,
        null=True,
    )

    verified_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    verified_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="verified_kycs",
    )

    # -----------------------------
    # Audit
    # -----------------------------
    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = "kyc"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email} - {self.status}"