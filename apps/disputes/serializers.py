from rest_framework import serializers
from django.core.exceptions import ValidationError as DjangoValidationError
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Dispute, DisputeEvidence, DisputeMessage

User = get_user_model()


# ==============================================================================
# 1. DISPUTE EVIDENCE SERIALIZER (Handles Cloudinary Uploads)
# ==============================================================================
class DisputeEvidenceSerializer(serializers.ModelSerializer):
    uploaded_by_email = serializers.ReadOnlyField(source='uploaded_by.email')
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = DisputeEvidence
        fields = [
            'id', 'dispute', 'uploaded_by', 'uploaded_by_email', 
            'evidence_type', 'file_attachment', 'file_url', 
            'description', 'created_at'
        ]
        read_only_fields = ['id', 'uploaded_by', 'created_at']

    def get_file_url(self, obj):
        if obj.file_attachment:
            return obj.file_attachment.url
        return None

    def validate_dispute(self, value):
        """Guard rail: Prevent adding evidence files to dead or locked dispute files."""
        if value.status in [Dispute.DisputeStatus.RESOLVED, Dispute.DisputeStatus.REJECTED, Dispute.DisputeStatus.CLOSED]:
            raise serializers.ValidationError("This case file is finalized and cannot accept additional evidence entries.")
        return value


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