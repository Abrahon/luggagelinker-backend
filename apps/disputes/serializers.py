from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Dispute, DisputeEvidence, DisputeMessage
from django.contrib.auth import get_user_model
from .models import DisputeHistory
from rest_framework import serializers
from apps.bookings.models import Booking
from .models import DisputeEvidence
from .enums import EvidenceType, DisputeStatus
# 🟢 Add this right at the top of apps/disputes/serializers.py
from decimal import Decimal
# Near the top of apps/disputes/serializers.py

# 🟢 Add the model imports from your payment app
from apps.payment.models import BookingPayment, BookingPaymentStatus

User = get_user_model()


# ==============================================================================
# 1. DISPUTE EVIDENCE SERIALIZER (Handles Cloudinary Uploads)
# ==============================================================================
from cloudinary.utils import cloudinary_url
from rest_framework import serializers


class DisputeEvidenceSerializer(serializers.ModelSerializer):
    file_attachment = serializers.FileField(write_only=True)
    file_url = serializers.SerializerMethodField(read_only=True)

    evidence_type_display = serializers.CharField(
        source="get_evidence_type_display",
        read_only=True
    )

    uploaded_by_email = serializers.ReadOnlyField(
        source="uploaded_by.email"
    )

    class Meta:
        model = DisputeEvidence
        fields = [
            "id",
            "dispute",
            "uploaded_by",
            "uploaded_by_email",
            "file_attachment",   # upload
            "file_url",          # response
            "evidence_type",
            "evidence_type_display",
            "description",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "dispute",
            "uploaded_by",
            "uploaded_by_email",
            "created_at",
            "file_url",
        ]

    def get_file_url(self, obj):
        if not obj.file_attachment:
            return None

        url, _ = cloudinary_url(obj.file_attachment.public_id)
        return url

    def validate_file_attachment(self, value):
        max_size_mb = 10

        if hasattr(value, "size") and value.size > max_size_mb * 1024 * 1024:
            raise serializers.ValidationError(
                f"Maximum allowed file size is {max_size_mb} MB."
            )

        return value

    def validate(self, attrs):
        dispute = self.context.get("dispute")

        if dispute and dispute.status in [
            DisputeStatus.RESOLVED,
            DisputeStatus.REJECTED,
        ]:
            raise serializers.ValidationError(
                "Evidence cannot be uploaded because this dispute is closed."
            )

        return attrs
# ==============================================================================
# 2. DISPUTE MESSAGE SERIALIZER (Handles Conversation Threads)
# ==============================================================================
class DisputeMessageSerializer(serializers.ModelSerializer):
    sender_email = serializers.ReadOnlyField(source='sender.email')

    class Meta:
        model = DisputeMessage
        fields = [
            'id', 'dispute', 'sender', 'sender_email', 
            'message_text', 'is_admin_note', 'is_read', 'created_at'
        ]
        read_only_fields = ['id', 'sender', 'is_admin_note', 'is_read', 'created_at']

    def validate_dispute(self, value):
        """Guard rail: Ensure the conversation thread belongs to an active, unclosed dispute."""
        if value.status == Dispute.DisputeStatus.CLOSED:
            raise serializers.ValidationError("This ticket has been officially closed. No further communications are permitted.")
        return value


# ==============================================================================
# 3. USER DISPUTE SERIALIZER (For Senders & Travelers)
# ==============================================================================
class DisputeSerializer(serializers.ModelSerializer):
    evidence = DisputeEvidenceSerializer(many=True, read_only=True)
    messages = DisputeMessageSerializer(many=True, read_only=True)
    opened_by_email = serializers.ReadOnlyField(source='opened_by.email')
    against_user_email = serializers.ReadOnlyField(source='against_user.email')

    class Meta:
        model = Dispute
        fields = [
            'id', 'booking', 'opened_by', 'opened_by_email', 'against_user', 'against_user_email',
            'reason', 'status', 'description', 'disputed_amount', 'is_reopened', 
            'created_at', 'updated_at', 'evidence', 'messages'
        ]
        read_only_fields = [
            'id', 'opened_by', 'against_user', 'status', 'is_reopened', 'created_at', 'updated_at'
        ]

    def validate(self, attrs):
        request = self.context.get('request')
        if not request or not request.user:
            raise serializers.ValidationError("Authentication application context is missing.")

        user = request.user
        booking = attrs.get('booking')

        # 1. Guard Rail: Ensure user belongs to the transaction
        if user != booking.sender and user != booking.traveler:
            raise serializers.ValidationError(
                {"booking": "Authorization Error: You must be an active party to this booking to open a dispute."}
            )

        # 2. Guard Rail: Prevent redundant ticketing channels
        if Dispute.objects.filter(booking=booking).exists():
            raise serializers.ValidationError(
                {"booking": "Conflict Error: An active dispute hold is already linked to this transaction record."}
            )

        # 3. Guard Rail: Verify appropriate booking transaction phase parameters
        if booking.status in ["PENDING", "CANCELLED"]:
            raise serializers.ValidationError(
                {"booking": f"Workflow Error: Cannot initiate disputes against bookings with active status: {booking.status}."}
            )

        # Automate routing roles cleanly inside backend memory spaces
        attrs['opened_by'] = user
        attrs['against_user'] = booking.traveler if user == booking.sender else booking.sender
        attrs['last_updated_by'] = user
        return attrs

    def create(self, validated_data):
        try:
            dispute = Dispute(**validated_data)
            dispute.full_clean()
            dispute.save()
            return dispute
        except DjangoValidationError as e:
            raise serializers.ValidationError(serializers.as_serializer_error(e))


# ==============================================================================
# 4. ADMINISTRATIVE DISPUTE SERIALIZER (For Moderation Teams)
# ==============================================================================
class AdminDisputeSerializer(serializers.ModelSerializer):
    evidence = DisputeEvidenceSerializer(many=True, read_only=True)
    messages = DisputeMessageSerializer(many=True, read_only=True)
    opened_by_email = serializers.ReadOnlyField(source='opened_by.email')
    against_user_email = serializers.ReadOnlyField(source='against_user.email')
    assigned_admin_email = serializers.ReadOnlyField(source='assigned_admin.email')
    resolved_by_email = serializers.ReadOnlyField(source='resolved_by.email')

    class Meta:
        model = Dispute
        fields = [
            'id', 'booking', 'opened_by', 'opened_by_email', 'against_user', 'against_user_email',
            'assigned_admin', 'assigned_admin_email', 'resolved_by', 'resolved_by_email', 
            'last_updated_by', 'reason', 'status', 'resolution', 'description', 'admin_notes', 
            'disputed_amount', 'is_reopened', 'sender_notified', 'traveler_notified', 
            'created_at', 'updated_at', 'resolved_at', 'evidence', 'messages'
        ]
        read_only_fields = ['id', 'booking', 'opened_by', 'against_user', 'created_at', 'updated_at']

    def validate(self, attrs):
        request = self.context.get('request')
        if not request or not request.user:
            raise serializers.ValidationError("Authentication validation context missing.")

        admin = request.user
        attrs['last_updated_by'] = admin

        # Capture status transitions state machine rules
        current_status = self.instance.status if self.instance else None
        new_status = attrs.get('status', current_status)
        new_resolution = attrs.get('resolution', self.instance.resolution if self.instance else "")

        # 1. State Enforcement: If moving to RESOLVED, a structural Resolution Type MUST be selected.
        if new_status == Dispute.DisputeStatus.RESOLVED and not new_resolution:
            raise serializers.ValidationError(
                {"resolution": "Workflow Constraint: A clear Resolution Type must be applied to execute a RESOLVED execution state."}
            )

        # 2. Automation: Log timestamp and administrator signatures when marking a ticket as finalized
        if new_status in [Dispute.DisputeStatus.RESOLVED, Dispute.DisputeStatus.REJECTED] and current_status not in [Dispute.DisputeStatus.RESOLVED, Dispute.DisputeStatus.REJECTED]:
            attrs['resolved_by'] = admin
            attrs['resolved_at'] = timezone.now()

        return attrs





class DisputeHistorySerializer(serializers.ModelSerializer):
    """
    Read-only audit serializer transforming the immutable structural history 
    timeline logs for admin dashboards and client tracking states.
    """
    # Expose the human-readable display titles from your TextChoices enums
    action_display = serializers.CharField(source="get_action_display", read_only=True)
    status_from_display = serializers.CharField(source="get_status_from_display", read_only=True)
    status_to_display = serializers.CharField(source="get_status_to_display", read_only=True)
    
    # Audit participant signatures
    actor_email = serializers.ReadOnlyField(source="actor.email")
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = DisputeHistory
        fields = [
            "id",
            "dispute",
            "actor",
            "actor_email",
            "actor_name",
            "action",
            "action_display",
            "status_from",
            "status_from_display",
            "status_to",
            "status_to_display",
            "notes",
            "created_at"
        ]
        # Audit trails must remain read-only across all endpoints to prevent system tampering
        read_only_fields = fields

    def get_actor_name(self, obj):
        """Safely generates a fallback name for UI presentation."""
        actor = obj.actor
        full_name = f"{actor.get_full_name()}".strip()
        if full_name:
            return full_name
        return actor.username if hasattr(actor, "username") else actor.email


class AdminDisputeSerializer(serializers.ModelSerializer):
    # 👇 Add this nested relationship line right here
    history = DisputeHistorySerializer(many=True, read_only=True)
    
    evidence = DisputeEvidenceSerializer(many=True, read_only=True)
    messages = DisputeMessageSerializer(many=True, read_only=True)
    # ... keep your existing attributes ...

    class Meta:
        model = Dispute
        fields = [
            'id', 'booking', 'opened_by', 'against_user', 'status',
            'evidence', 'messages', 'history', # 👈 Make sure it's added here
            # ... keep your remaining field declarations ...
        ]





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
# ==============================================================================
# USER INITIALIZATION FIELD GENERATION SERIALIZER
# ==============================================================================
class CreateDisputeSerializer(serializers.ModelSerializer):
    """Validates structural balance and authority limitations on creation endpoints."""
    booking_id = serializers.UUIDField(write_only=True)
    
    # 🟢 Explicitly defined with a proper Decimal instance to silence the UserWarning
    disputed_amount = serializers.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        min_value=Decimal("0.01")
    )

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