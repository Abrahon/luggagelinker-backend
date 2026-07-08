import logging
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.bookings.models import Booking, BookingStatus
from apps.payment.models import BookingPayment, BookingPaymentStatus
from apps.notifications.services import notify_dispute_opened

from .models import Dispute, DisputeMessage, DisputeEvidence, DisputeHistory
from apps.disputes.enums import DisputeStatus, DisputeHistoryAction
# user disputes serializsrs
from decimal import Decimal, InvalidOperation
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError

from apps.bookings.models import Booking
from apps.payment.models import BookingPayment, BookingPaymentStatus
from .models import Dispute, DisputeMessage, DisputeEvidence, DisputeHistory
from apps.disputes.enums import DisputeStatus, DisputeReason, ResolutionType, DisputeHistoryAction

User = get_user_model()

logger = logging.getLogger(__name__)


class DisputeService:

    @staticmethod
    def get_dispute(dispute_id, user) -> Dispute:
        """
        Retrieves a specific dispute file safely.
        Guarantees that only the opening user, the opposing party, or an admin can access it.
        """
        try:
            dispute = Dispute.objects.select_related('booking', 'assigned_admin', 'opened_by', 'against_user').get(id=dispute_id)
        except Dispute.DoesNotExist:
            raise ValidationError("The requested dispute record does not exist.")

        # Guard layer: Check permissions explicitly
        if user != dispute.opened_by and user != dispute.against_user and not user.is_staff and not user.is_superuser:
            raise ValidationError("Access Denied: You are not an active party to this dispute mediation file.")

        return dispute

    @staticmethod
    @transaction.atomic
    def create_dispute(booking_id, user, reason, description, disputed_amount) -> Dispute:
        """
        Initializes a formal dispute and sets an escrow protection lock on the underlying payment.
        Validates timeline barriers and checks user permissions.
        """
        try:
            booking = Booking.objects.select_for_update().get(id=booking_id)
        except Booking.DoesNotExist:
            raise ValidationError("Target booking reference tracking point not found.")

        # 1. Authority validation: Only the sender or traveler can open a dispute
        if user != booking.sender and user != booking.traveler:
            raise ValidationError("Permission Denied: You must be an explicit party to this booking contract to file a claim.")

        # 2. Check if a dispute already exists for this booking
        if Dispute.objects.filter(booking=booking).exists():
            raise ValidationError("Conflict Error: An open or resolved dispute case file already exists for this booking tracking allocation.")

        # 3. Check workflow eligibility: Ensure the payment is securely held in escrow
        try:
            payment = BookingPayment.objects.get(booking=booking)
        except BookingPayment.DoesNotExist:
            raise ValidationError("Payment record tracing failed for the target transaction ledger.")

        if payment.status != BookingPaymentStatus.AUTHORIZED:
            raise ValidationError(f"Escrow Protection Violation: Cannot open a dispute if funds are not safely held. Current Status: {payment.status}")

        # Determine the opposing party
        against_user = booking.traveler if user == booking.sender else booking.sender

        # 4. Initialize the dispute record
        dispute = Dispute.objects.create(
            booking=booking,
            opened_by=user,
            against_user=against_user,
            reason=reason,
            description=description,
            disputed_amount=disputed_amount,
            status=DisputeStatus.OPEN,
            last_updated_by=user
        )

        # 5. Document structural timeline history record
        DisputeHistory.objects.create(
            dispute=dispute,
            actor=user,
            action=DisputeHistoryAction.OPENED,
            status_from=DisputeStatus.OPEN,
            status_to=DisputeStatus.OPEN,
            notes=f"Dispute opened autonomously by {user.email} due to: {dispute.get_reason_display()}."
        )

        # 6. Log structured system event metrics
        logger.info(
            "Dispute instance %s initiated for Booking %s",
            dispute.id,
            booking.id,
            extra={
                "opened_by": str(user.id),
                "against_user": str(against_user.id),
                "amount": str(disputed_amount)
            }
        )

        # 7. Dispatch asynchronous background notifications
        transaction.on_commit(lambda: notify_dispute_opened(user=against_user, dispute=dispute))

        return dispute

    @staticmethod
    @transaction.atomic
    def add_message(dispute_id, sender, message_text) -> DisputeMessage:
        """
        Appends an interactive conversational record or response payload directly to the dispute thread.
        Automatically updates workflow tracking statuses depending on who sent the message.
        """
        dispute = DisputeService.get_dispute(dispute_id=dispute_id, user=sender)

        if dispute.status in [DisputeStatus.RESOLVED, DisputeStatus.REJECTED]:
            raise ValidationError("Modification Error: Cannot add communication records to a finalized arbitration vault entry.")

        # Instantiate message
        message = DisputeMessage.objects.create(
            dispute=dispute,
            sender=sender,
            message_text=message_text
        )

        # Update core timestamps and structural track metrics
        old_status = dispute.status
        dispute.last_updated_by = sender
        
        # If a user provides an update while waiting for feedback, flip the status back to under review
        if dispute.status == DisputeStatus.WAITING_FOR_USER and not sender.is_staff and not sender.is_superuser:
            dispute.status = DisputeStatus.UNDER_REVIEW
            dispute.save(update_fields=["status", "updated_at", "last_updated_by"])
            
            DisputeHistory.objects.create(
                dispute=dispute,
                actor=sender,
                action=DisputeHistoryAction.EVIDENCE_SUBMITTED,
                status_from=old_status,
                status_to=DisputeStatus.UNDER_REVIEW,
                notes=f"User {sender.email} provided comments. Workflow returned to review processing queue."
            )
        else:
            dispute.save(update_fields=["updated_at", "last_updated_by"])

        logger.info("Communication record entry %s added to dispute %s by user %s", message.id, dispute.id, sender.id)
        return message

    @staticmethod
    @transaction.atomic
    def add_evidence(dispute_id, uploaded_by, file_object, evidence_type, notes="") -> DisputeEvidence:
        """
        Saves uploaded file proof layers into the database record securely.
        Guarantees that files match valid workflow states and links them cleanly.
        """
        dispute = DisputeService.get_dispute(dispute_id=dispute_id, user=uploaded_by)

        if dispute.status in [DisputeStatus.RESOLVED, DisputeStatus.REJECTED]:
            raise ValidationError("Operational Error: File vault uploads are permanently locked for archived cases.")

        # Create the evidence data entry boundary record
        evidence = DisputeEvidence.objects.create(
            dispute=dispute,
            uploaded_by=uploaded_by,
            file=file_object,
            evidence_type=evidence_type,
            notes=notes
        )

        # Update tracking status parameters across the transaction block bounds
        old_status = dispute.status
        dispute.last_updated_by = uploaded_by

        if dispute.status == DisputeStatus.WAITING_FOR_USER:
            dispute.status = DisputeStatus.UNDER_REVIEW
            dispute.save(update_fields=["status", "updated_at", "last_updated_by"])

            DisputeHistory.objects.create(
                dispute=dispute,
                actor=uploaded_by,
                action=DisputeHistoryAction.EVIDENCE_SUBMITTED,
                status_from=old_status,
                status_to=DisputeStatus.UNDER_REVIEW,
                notes=f"Document file matrix attached by {uploaded_by.email}. Review state restored."
            )
        else:
            dispute.save(update_fields=["updated_at", "last_updated_by"])

        logger.info(
            "Evidence payload file %s uploaded successfully", 
            evidence.id, 
            extra={
                "dispute": str(dispute.id),
                "type": evidence_type,
                "user": str(uploaded_by.id)
            }
        )
        return evidence





# ==============================================================================
# AUDIT TRAIL LOG SERIALIZER (READ-ONLY)
# ==============================================================================
class DisputeHistorySerializer(serializers.ModelSerializer):
    """Read-only log output trace displaying historical system transitions."""
    action_display = serializers.CharField(source="get_action_display", read_only=True)
    status_from_display = serializers.CharField(source="get_status_from_display", read_only=True)
    status_to_display = serializers.CharField(source="get_status_to_display", read_only=True)
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = DisputeHistory
        fields = [
            "id", "actor", "actor_name", "action", "action_display",
            "status_from", "status_from_display", "status_to", "status_to_display",
            "notes", "created_at"
        ]
        read_only_fields = fields

    def get_actor_name(self, obj):
        actor = obj.actor
        full_name = f"{actor.get_full_name()}".strip() if hasattr(actor, "get_full_name") else ""
        return full_name if full_name else (getattr(actor, "username", "") or actor.email)


# ==============================================================================
# DISPUTE EVIDENCE SERIALIZER
# ==============================================================================
class DisputeEvidenceSerializer(serializers.ModelSerializer):
    """Handles secure payload uploads and verification for dispute evidence files."""
    # 🟢 Use your custom EvidenceType choice boundaries for safe validation parsing
    evidence_type = serializers.ChoiceField(choices=EvidenceType.choices)
    evidence_type_display = serializers.CharField(source="get_evidence_type_display", read_only=True)
    uploaded_by_email = serializers.ReadOnlyField(source="uploaded_by.email")

    class Meta:
        model = DisputeEvidence
        fields = [
            "id", "dispute", "uploaded_by", "uploaded_by_email",
            "file", "evidence_type", "evidence_type_display", "notes", "created_at"
        ]
        read_only_fields = ["id", "uploaded_by", "created_at"]

    def validate_file(self, value):
        """File guard checking attachment size constraints."""
        max_size_mb = 10
        if value.size > max_size_mb * 1024 * 1024:
            raise serializers.ValidationError(f"File sizing limits exceeded. Maximum payload boundary: {max_size_mb}MB.")
        return value

    def validate(self, attrs):
        """Validates that evidence can only be added to open or active disputes."""
        dispute = attrs.get("dispute")
        if dispute and dispute.status in [DisputeStatus.RESOLVED, DisputeStatus.REJECTED]:
            raise serializers.ValidationError("File upload failure: Case file is permanently closed and archived.")
        return attrs


# ==============================================================================
# DISPUTE CONVERSATION THREAD MESSAGE SERIALIZER
# ==============================================================================
class DisputeMessageSerializer(serializers.ModelSerializer):
    """Transforms raw textual inputs into chronological dispute messaging feeds."""
    sender_email = serializers.ReadOnlyField(source="sender.email")
    sender_name = serializers.SerializerMethodField()

    class Meta:
        model = DisputeMessage
        fields = ["id", "dispute", "sender", "sender_email", "sender_name", "message_text", "created_at"]
        read_only_fields = ["id", "sender", "created_at"]

    def get_sender_name(self, obj):
        sender = obj.sender
        full_name = f"{sender.get_full_name()}".strip() if hasattr(sender, "get_full_name") else ""
        return full_name if full_name else (getattr(sender, "username", "") or sender.email)

    def validate(self, attrs):
        """Enforces message thread restrictions on finalized archives."""
        dispute = attrs.get("dispute")
        if dispute and dispute.status in [DisputeStatus.RESOLVED, DisputeStatus.REJECTED]:
            raise serializers.ValidationError("Thread Locked: Cannot transmit updates on a resolved dispute ledger.")
        return attrs


# ==============================================================================
# USER INITIALIZATION FIELD GENERATION SERIALIZER
# ==============================================================================
class CreateDisputeSerializer(serializers.ModelSerializer):
    """Validates structural balance and authority limitations on creation endpoints."""
    booking_id = serializers.UUIDField(write_only=True)

    class Meta:
        model = Dispute
        fields = ["booking_id", "reason", "description", "disputed_amount"]

    def validate(self, attrs):
        user = self.context["request"].user
        booking_id = attrs["booking_id"]
        disputed_amount = attrs["disputed_amount"]

        # 1. Look up target reference context object mapping
        try:
            booking = Booking.objects.get(id=booking_id)
        except Booking.DoesNotExist:
            raise serializers.ValidationError({"booking_id": "Target booking reference location went missing."})

        # 2. Authority context checking
        if user != booking.sender and user != booking.traveler:
            raise serializers.ValidationError("Access Denied: You must be an explicit party to this transaction to claim a dispute.")

        # 3. Duplicate checks
        if Dispute.objects.filter(booking=booking).exists():
            raise serializers.ValidationError("A dispute ledger already exists for this package routing contract assignment.")

        # 4. Escrow status locking check
        try:
            payment = BookingPayment.objects.get(booking=booking)
        except BookingPayment.DoesNotExist:
            raise serializers.ValidationError("Financial ledger transaction trace error: Payment not logged.")

        if payment.status != BookingPaymentStatus.AUTHORIZED:
            raise serializers.ValidationError(f"Escrow Hold Missing: Cannot dispute unless funds are locked. Current Status: {payment.status}")

        # 5. Financial volume checks
        if disputed_amount <= Decimal("0.00"):
            raise serializers.ValidationError({"disputed_amount": "Disputed monetary allocations must be greater than zero."})
        
        if disputed_amount > booking.agreed_reward:
            raise serializers.ValidationError({"disputed_amount": f"Disputed value limits exceeded. Bound max ceiling: {booking.agreed_reward}"})

        # Attach booking into validated data context output pipeline
        attrs["booking"] = booking
        return attrs


# ==============================================================================
# CLIENT STANDARD DATA PRESENTATION DISPUTE SERIALIZER
# ==============================================================================
class DisputeSerializer(serializers.ModelSerializer):
    """Clean data view optimized for client-side presentation layers (Senders & Travelers)."""
    reason_display = serializers.CharField(source="get_reason_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    resolution_display = serializers.CharField(source="get_resolution_display", read_only=True)
    
    messages = DisputeMessageSerializer(many=True, read_only=True)
    evidence = DisputeEvidenceSerializer(many=True, read_only=True)

    class Meta:
        model = Dispute
        fields = [
            "id", "booking", "opened_by", "against_user", "reason", "reason_display",
            "description", "disputed_amount", "status", "status_display",
            "resolution", "resolution_display", "messages", "evidence", "created_at", "updated_at"
        ]
        read_only_fields = fields # All mutations for users go through discrete action endpoints


# ==============================================================================
# PLATFORM ADMINISTRATIVE MODERATION DISPUTE SERIALIZER
# ==============================================================================
class AdminDisputeSerializer(serializers.ModelSerializer):
    """Full-visibility management serializer tailored for administrative back-office panels."""
    reason_display = serializers.CharField(source="get_reason_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    resolution_display = serializers.CharField(source="get_resolution_display", read_only=True)
    
    opened_by_email = serializers.ReadOnlyField(source="opened_by.email")
    against_user_email = serializers.ReadOnlyField(source="against_user.email")
    assigned_admin_email = serializers.ReadOnlyField(source="assigned_admin.email")
    
    messages = DisputeMessageSerializer(many=True, read_only=True)
    evidence = DisputeEvidenceSerializer(many=True, read_only=True)
    history = DisputeHistorySerializer(many=True, read_only=True)

    class Meta:
        model = Dispute
        fields = [
            "id", "booking", "opened_by", "opened_by_email", "against_user", "against_user_email",
            "assigned_admin", "assigned_admin_email", "reason", "reason_display", "description", 
            "disputed_amount", "status", "status_display", "resolution", "resolution_display", 
            "admin_notes", "resolved_by", "resolved_at", "messages", "evidence", "history", 
            "created_at", "updated_at"
        ]
        # Admin interfaces manipulate rows through deliberate class services, not raw model binding
        read_only_fields = [f for f in fields if f not in ["admin_notes"]]