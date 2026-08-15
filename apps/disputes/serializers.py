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
from apps.disputes.enums import ResolutionType
from decimal import Decimal
from apps.accounts.serializers import UserBriefSerializer


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

    opened_by = UserBriefSerializer(read_only=True)
    against_user = UserBriefSerializer(read_only=True)
    assigned_admin = UserBriefSerializer(read_only=True)

    reason_display = serializers.CharField(
        source="get_reason_display",
        read_only=True,
    )

    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    resolution_display = serializers.CharField(
        source="get_resolution_display",
        read_only=True,
    )

    messages = DisputeMessageSerializer(
        many=True,
        read_only=True,
    )
    disputed_amount = serializers.SerializerMethodField()

    evidence = DisputeEvidenceSerializer(
        many=True,
        read_only=True,
    )

    class Meta:
        model = Dispute

        fields = [
            "id",
            "booking",
            "opened_by",
            "against_user",
            "assigned_admin",
            "reason",
            "reason_display",
            "description",
            "disputed_amount",
            "status",
            "status_display",
            "resolution",
            "resolution_display",
            "is_reopened",
            "messages",
            "evidence",
            "created_at",
            "updated_at",
            "resolved_at",
        ]

        read_only_fields = fields


    def get_disputed_amount(self, obj):
            amount_str = str(obj.disputed_amount)
            request = self.context.get("request")

            # Show sign only when status is RESOLVED and request user is present
            if obj.status != "RESOLVED" or not request or not request.user:
                return amount_str

            current_user = request.user

            # Refund resolutions: Sender/OpenedBy gets refunded (+), Traveler/AgainstUser pays (-)
            if obj.resolution in ["FULL_REFUND", "PARTIAL_REFUND"]:
                if current_user == obj.opened_by:
                    return f"+{amount_str}"
                elif current_user == obj.against_user:
                    return f"-{amount_str}"

            # Non-refund/release resolutions: Traveler gets paid (+), Sender loses (-)
            elif obj.resolution in ["RELEASE_TO_TRAVELER", "PAY_TRAVELER", "NO_REFUND"]:
                if current_user == obj.against_user:
                    return f"+{amount_str}"
                elif current_user == obj.opened_by:
                    return f"-{amount_str}"

            return amount_str
    

    def validate(self, attrs):
        request = self.context["request"]

        booking = attrs["booking"]

        user = request.user

        if user not in [booking.sender, booking.traveler]:
            raise serializers.ValidationError(
                {
                    "booking": "You are not a participant of this booking."
                }
            )

        if Dispute.objects.filter(booking=booking).exists():
            raise serializers.ValidationError(
                {
                    "booking": "A dispute already exists for this booking."
                }
            )

        if booking.status in [
            "PENDING",
            "CANCELLED",
        ]:
            raise serializers.ValidationError(
                {
                    "booking": "This booking cannot be disputed."
                }
            )

        attrs["opened_by"] = user
        attrs["against_user"] = (
            booking.traveler
            if user == booking.sender
            else booking.sender
        )
        attrs["last_updated_by"] = user

        return attrs

    def create(self, validated_data):
        dispute = Dispute(**validated_data)
        dispute.full_clean()
        dispute.save()
        return dispute




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
# DISPUTE CONVERSATION THREAD MESSAGE SERIALIZER
# ==============================================================================



class DisputeMessageSerializer(serializers.ModelSerializer):
    """
    Serializer for dispute conversation messages.

    Client only provides:
        message_text

    Backend automatically determines:
        dispute
        sender
        created_at
    """

    sender_email = serializers.ReadOnlyField(
        source="sender.email"
    )

    sender_name = serializers.SerializerMethodField()

    sender_profile_picture = serializers.SerializerMethodField()

    is_mine = serializers.SerializerMethodField()

    class Meta:
        model = DisputeMessage

        fields = [
            "id",
            "dispute",
            "sender",
            "sender_email",
            "sender_name",
            "sender_profile_picture",
            "message_text",
            "is_mine",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "dispute",
            "sender",
            "sender_email",
            "sender_name",
            "sender_profile_picture",
            "is_mine",
            "created_at",
        ]

    def get_sender_name(self, obj):
        sender = obj.sender

        if not sender:
            return "Unknown User"

        # Your project appears to use profile.full_name
        profile = getattr(sender, "profile", None)

        if profile and getattr(profile, "full_name", None):
            return profile.full_name

        # Fallback to Django full name
        if hasattr(sender, "get_full_name"):
            full_name = sender.get_full_name().strip()

            if full_name:
                return full_name

        return (
            getattr(sender, "username", None)
            or getattr(sender, "email", None)
            or "Unknown User"
        )

    def get_sender_profile_picture(self, obj):
        sender = obj.sender

        if not sender:
            return None

        profile = getattr(sender, "profile", None)

        if not profile:
            return None

        picture = getattr(profile, "profile_picture", None)

        if not picture:
            return None

        try:
            return picture.url
        except Exception:
            return str(picture)

    def get_is_mine(self, obj):
        request = self.context.get("request")

        if not request or not request.user.is_authenticated:
            return False

        return obj.sender_id == request.user.id

    def validate_message_text(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "Message cannot be empty."
            )

        if len(value) > 5000:
            raise serializers.ValidationError(
                "Message cannot exceed 5000 characters."
            )

        return value
    
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
# PLATFORM ADMINISTRATIVE MODERATION DISPUTE SERIALIZER
# ==============================================================================

class AdminDisputeSerializer(serializers.ModelSerializer):
    """
    Production serializer for Admin Dispute Management.
    """

    # ------------------------------------------------------------------
    # Parties
    # ------------------------------------------------------------------
    opened_by = UserBriefSerializer(read_only=True)
    against_user = UserBriefSerializer(read_only=True)
    assigned_admin = UserBriefSerializer(read_only=True)
    resolved_by = UserBriefSerializer(read_only=True)

    # ------------------------------------------------------------------
    # Booking Summary
    # ------------------------------------------------------------------
    booking = serializers.SerializerMethodField()

    # ------------------------------------------------------------------
    # Human Readable Choices
    # ------------------------------------------------------------------
    reason_display = serializers.CharField(
        source="get_reason_display",
        read_only=True
    )

    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True
    )

    resolution_display = serializers.CharField(
        source="get_resolution_display",
        read_only=True
    )

    # ------------------------------------------------------------------
    # Settlement Summary
    # ------------------------------------------------------------------
    settlement = serializers.SerializerMethodField()

    # ------------------------------------------------------------------
    # Timeline
    # ------------------------------------------------------------------
    timeline = serializers.SerializerMethodField()

    # ------------------------------------------------------------------
    # Related Data
    # ------------------------------------------------------------------
    evidence = DisputeEvidenceSerializer(
        many=True,
        read_only=True
    )

    messages = DisputeMessageSerializer(
        many=True,
        read_only=True
    )

    history = DisputeHistorySerializer(
        many=True,
        read_only=True
    )

    class Meta:
        model = Dispute

        fields = [
            "id",

            "booking",

            "opened_by",
            "against_user",
            "assigned_admin",
            "resolved_by",

            "reason",
            "reason_display",

            "description",

            "disputed_amount",

            "status",
            "status_display",

            "resolution",
            "resolution_display",

            "admin_notes",

            "settlement",

            "timeline",

            "evidence",
            "messages",
            "history",
        ]

        read_only_fields = fields

    # ============================================================
    # BOOKING SUMMARY
    # ============================================================

    def get_booking(self, obj):
        booking = obj.booking

        return {
            "id": str(booking.id),
            "tracking_number": booking.tracking_number,
            "status": booking.status,
            "payment_status": booking.payment_status,
        }

    # ============================================================
    # SETTLEMENT SUMMARY
    # ============================================================

    def get_settlement(self, obj):

        total = obj.disputed_amount or Decimal("0.00")

        refund_ratio = Decimal("0.00")

        if obj.resolution == "FULL_REFUND":
            refund_ratio = Decimal("1.00")

        elif obj.resolution == "PARTIAL_REFUND":
            refund_ratio = getattr(
                obj,
                "refund_ratio",
                Decimal("0.50")
            )

        sender_refund = (
            total * refund_ratio
        ).quantize(Decimal("0.01"))

        traveler_payout = (
            total - sender_refund
        ).quantize(Decimal("0.01"))

        return {
            "currency": "USD",
            "total_amount": str(total),
            "refund_ratio": str(refund_ratio),
            "sender_refund": str(sender_refund),
            "traveler_payout": str(traveler_payout),
        }

    # ============================================================
    # TIMELINE
    # ============================================================

    def get_timeline(self, obj):

        assigned = None

        history = obj.history.filter(
            action="ASSIGNED"
        ).order_by("created_at").first()

        if history:
            assigned = history.created_at

        return {
            "opened_at": obj.created_at,
            "assigned_at": assigned,
            "resolved_at": obj.resolved_at,
        }


class AdminDisputeAssignSerializer(serializers.ModelSerializer):
    assigned_admin = UserBriefSerializer(read_only=True)

    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    class Meta:
        model = Dispute
        fields = [
            "id",
            "status",
            "status_display",
            "assigned_admin",
        ]




class AdminRequestEvidenceSerializer(serializers.Serializer):
    request_message = serializers.CharField(
        max_length=1000,
        required=True,
        allow_blank=False,
        trim_whitespace=True,
        help_text="Explain what additional evidence the user must provide.",
    )





class AdminResolveDisputeSerializer(serializers.Serializer):
    resolution_type = serializers.ChoiceField(
        choices=ResolutionType.choices
    )

    admin_notes = serializers.CharField(
        required=False,
        allow_blank=True,
        default=""
    )

    refund_ratio = serializers.DecimalField(
        max_digits=3,
        decimal_places=2,
        required=False,
        default=Decimal("1.00"),
        min_value=Decimal("0.00"),
        max_value=Decimal("1.00")
    )

    def validate(self, attrs):
        resolution = attrs["resolution_type"]
        refund_ratio = attrs["refund_ratio"]

        if resolution == ResolutionType.RELEASE_ESCROW:
            if refund_ratio != Decimal("0.00"):
                raise serializers.ValidationError({
                    "refund_ratio": "Release Escrow requires refund_ratio = 0.00."
                })

        elif resolution == ResolutionType.FULL_REFUND:
            if refund_ratio != Decimal("1.00"):
                raise serializers.ValidationError({
                    "refund_ratio": "Full Refund requires refund_ratio = 1.00."
                })

        elif resolution == ResolutionType.PARTIAL_REFUND:
            if not Decimal("0.01") <= refund_ratio <= Decimal("0.99"):
                raise serializers.ValidationError({
                    "refund_ratio": "Partial Refund requires a value between 0.01 and 0.99."
                })

        elif resolution == ResolutionType.NO_ACTION:
            attrs["refund_ratio"] = Decimal("0.00")

        return attrs