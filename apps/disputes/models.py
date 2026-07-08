from django.db import models

# Create your models here.
import uuid
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from cloudinary.models import CloudinaryField  

# Ensure you import your actual Booking model's choice enum class
# Example: from apps.bookings.models import BookingStatus


class Dispute(models.Model):
    """
    Production-grade management engine tracking transactional escrow holds, 
    operational life cycles, and administrative arbitrations.
    """
    class DisputeStatus(models.TextChoices):
        OPEN = "OPEN", "Open"
        UNDER_REVIEW = "UNDER_REVIEW", "Under Review"
        WAITING_FOR_USER = "WAITING_FOR_USER", "Waiting for User"
        RESOLVED = "RESOLVED", "Resolved"
        REJECTED = "REJECTED", "Rejected"
        CLOSED = "CLOSED", "Closed"

    class DisputeReason(models.TextChoices):
        DAMAGED_CARGO = "DAMAGED_CARGO", "Items Damaged Upon Delivery"
        MISSING_ITEMS = "MISSING_ITEMS", "Items Missing From Shipment"
        NO_SHOW = "NO_SHOW", "Traveler Failed to Meet/Deliver"
        DELAYED_DELIVERY = "DELAYED_DELIVERY", "Unacceptable Delivery Delay"
        OTHER = "OTHER", "Other Policy Violation"

    class ResolutionType(models.TextChoices):
        REFUND = "REFUND", "Refund Sender"
        RELEASE_ESCROW = "RELEASE_ESCROW", "Release Escrow"
        PARTIAL_REFUND = "PARTIAL_REFUND", "Partial Refund"
        NO_ACTION = "NO_ACTION", "No Action"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    booking = models.OneToOneField(
        "bookings.Booking",
        on_delete=models.PROTECT,
        related_name="dispute",
        help_text="The transaction under active escrow dispute contention."
    )
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="initiated_disputes",
        help_text="The user filing the complaint."
    )
    against_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="received_disputes",
        help_text="The user whom the complaint is raised against."
    )
    assigned_admin = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moderated_disputes",
        help_text="Platform customer manager mediating the case file."
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_disputes",
        help_text="The specific administrator who executed the final verdict action."
    )
    last_updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="last_modified_disputes",
        help_text="Audit tracker of the last user or admin to alter this ticket state."
    )
    
    reason = models.CharField(max_length=30, choices=DisputeReason.choices, default=DisputeReason.OTHER)
    status = models.CharField(max_length=30, choices=DisputeStatus.choices, default=DisputeStatus.OPEN)
    resolution = models.CharField(max_length=30, choices=ResolutionType.choices, blank=True)
    
    description = models.TextField(max_length=2000, help_text="Detailed narrative describing the incident.")
    admin_notes = models.TextField(max_length=2000, blank=True, help_text="Internal confidential workspace logs for admins.")
    
    disputed_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
        help_text="The exact escrow funds total frozen under this hold."
    )
    
    # Flags & Metas
    is_reopened = models.BooleanField(default=False)
    sender_notified = models.BooleanField(default=False)
    traveler_notified = models.BooleanField(default=False)
    
    # Audit trail
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Dispute Ticket"
        verbose_name_plural = "Dispute Tickets"
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["opened_by"]),
            models.Index(fields=["assigned_admin"]),
        ]

    def __str__(self):
        return f"Dispute {self.id} | Booking {self.booking.id} [{self.status}]"

    def clean(self):
        """Validates systemic constraints, participant scopes, and matching statuses."""
        super().clean()
        
        # 1. Enforce participant bounds matching
        valid_participants = [self.booking.sender, self.booking.traveler]
        if self.opened_by not in valid_participants:
            raise ValidationError("Authorization Error: You must be an active party to this booking to open a dispute.")
        
        if self.against_user not in valid_participants:
            raise ValidationError("Validation Error: The targeted user must be a structural party to this booking.")
            
        if self.opened_by == self.against_user:
            raise ValidationError("Validation Error: You cannot open an operational dispute ticket against yourself.")
            
        # 2. Guard rails against un-funded or unassigned models logic
        # 💡 Cleanly using your exact model enum fields instead of raw strings
        if self.booking.status in ["PENDING", "CANCELLED"]:  # 🔄 Substitute with BookingStatus.PENDING / BookingStatus.CANCELLED
            raise ValidationError("Workflow Error: Cannot dispute an unfunded or closed transaction framework.")


class DisputeEvidence(models.Model):
    """
    Verification files and assets submitted via Cloudinary by ecosystem users 
    to back up claims.
    """
    class EvidenceType(models.TextChoices):
        IMAGE = "IMAGE", "Image Proof"
        VIDEO = "VIDEO", "Video Recording"
        DOCUMENT = "DOCUMENT", "Document Verification"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dispute = models.ForeignKey(Dispute, on_delete=models.CASCADE, related_name="evidence")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    
    evidence_type = models.CharField(max_length=15, choices=EvidenceType.choices, default=EvidenceType.IMAGE)
    file_attachment = CloudinaryField("file", folder="disputes/evidence/")  
    
    description = models.CharField(max_length=255, blank=True, help_text="Briefly explain what this proof substantiates.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Dispute Evidence"
        verbose_name_plural = "Dispute Evidence Items"

    def __str__(self):
        return f"Evidence {self.id} on Dispute {self.dispute.id}"


class DisputeMessage(models.Model):
    """
    Communication records tracking active threads between senders, travelers, 
    and administrators.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    dispute = models.ForeignKey(Dispute, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    
    message_text = models.TextField(max_length=1500)
    
    is_admin_note = models.BooleanField(default=False, help_text="Distinguishes platform moderator input text visual styles.")
    is_read = models.BooleanField(default=False, help_text="Tracks active unread badge status flags for counter loops.")
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Dispute Message"
        verbose_name_plural = "Dispute Messages"

    def __str__(self):
        return f"Message by {self.sender.email} on Dispute {self.dispute.id}"



import uuid
from django.db import models
from django.conf import settings

# Import the enums you created
from apps.disputes.enums import DisputeHistoryAction,DisputeStatus

class DisputeHistory(models.Model):
    """
    Immutable audit ledger capturing every atomic transition, status shift, 
    and monetary modification executed on a dispute case file.
    """
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Note: Use a string 'Dispute' if the Dispute model is defined below this one to avoid reference errors
    dispute = models.ForeignKey('Dispute', on_delete=models.CASCADE, related_name="history")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    
    action = models.CharField(
        max_length=50, 
        choices=DisputeHistoryAction.choices,
        help_text="System-level action captured in the audit trail."
    )
    status_from = models.CharField(
        max_length=30, 
        choices=DisputeStatus.choices,
        blank=True, 
        null=True, 
        help_text="Previous status before the action."
    )
    status_to = models.CharField(
        max_length=30, 
        choices=DisputeStatus.choices,
        help_text="New status after the action."
    )
    
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Dispute History Log"
        verbose_name_plural = "Dispute History Logs"
        indexes = [
            models.Index(fields=["dispute", "created_at"]),
        ]

    def __str__(self):
        return f"{self.get_action_display()} on Dispute {self.dispute_id} by User {self.actor_id}"