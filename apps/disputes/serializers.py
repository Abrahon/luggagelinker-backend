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
    """
    Serializer for dispute conversation messages.

    Client sends ONLY:
        {
            "message_text": "Where are you now?"
        }

    Backend determines:
        dispute   -> from URL
        sender    -> request.user
        created_at -> automatically
    """

    sender_email = serializers.EmailField(
        source="sender.email",
        read_only=True,
    )

    sender_name = serializers.SerializerMethodField(
        read_only=True
    )

    sender_profile_picture = serializers.SerializerMethodField(
        read_only=True
    )

    is_mine = serializers.SerializerMethodField(
        read_only=True
    )

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

            "is_admin_note",
            "is_read",

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
            "is_admin_note",
            "is_read",
            "created_at",
        ]

    # ============================================================
    # SENDER NAME
    # ============================================================

    def get_sender_name(self, obj):

        sender = obj.sender

        if not sender:
            return "Unknown User"

        profile = getattr(sender, "profile", None)

        if profile:
            full_name = getattr(
                profile,
                "full_name",
                None
            )

            if full_name:
                return str(full_name).strip()

        if hasattr(sender, "get_full_name"):

            full_name = sender.get_full_name().strip()

            if full_name:
                return full_name

        return (
            getattr(sender, "username", None)
            or getattr(sender, "email", None)
            or "Unknown User"
        )

    # ============================================================
    # PROFILE PICTURE
    # ============================================================

    def get_sender_profile_picture(self, obj):

        sender = obj.sender

        if not sender:
            return None

        profile = getattr(sender, "profile", None)

        if not profile:
            return None

        picture = getattr(
            profile,
            "profile_picture",
            None
        )

        if not picture:
            return None

        try:
            return picture.url
        except Exception:
            return str(picture)

    # ============================================================
    # IS MINE
    # ============================================================

    def get_is_mine(self, obj):

        request = self.context.get("request")

        if not request:
            return False

        if not request.user.is_authenticated:
            return False

        return obj.sender_id == request.user.id

    # ============================================================
    # MESSAGE VALIDATION
    # ============================================================

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



from rest_framework import serializers

from .models import (
    Dispute,
    DisputeEvidence,
    DisputeMessage,
    DisputeHistory,
)


# =============================================================
# USER SERIALIZER
# =============================================================

class DisputeHistoryUserSerializer(serializers.Serializer):
    """
    Lightweight user representation for dispute history.
    """

    id = serializers.UUIDField(read_only=True)
    email = serializers.EmailField(read_only=True)
    name = serializers.SerializerMethodField()

    def get_name(self, user):
        profile = getattr(user, "profile", None)

        if profile:
            full_name = getattr(profile, "full_name", None)

            if full_name:
                return str(full_name).strip()

            first_name = (
                getattr(profile, "first_name", None)
                or ""
            ).strip()

            last_name = (
                getattr(profile, "last_name", None)
                or ""
            ).strip()

            full_name = f"{first_name} {last_name}".strip()

            if full_name:
                return full_name

        return (
            getattr(user, "email", None)
            or "Unknown User"
        )


# =============================================================
# DISPUTE HISTORY SERIALIZER
# =============================================================

class DisputeHistorySerializer(serializers.ModelSerializer):
    """
    Serializer for dispute history timeline.
    """

    actor = DisputeHistoryUserSerializer(read_only=True)

    action_display = serializers.CharField(
        source="get_action_display",
        read_only=True,
    )

    status_from_display = serializers.SerializerMethodField()

    status_to_display = serializers.CharField(
        source="get_status_to_display",
        read_only=True,
    )

    class Meta:
        model = DisputeHistory

        fields = [
            "id",
            "dispute",
            "actor",

            "action",
            "action_display",

            "status_from",
            "status_from_display",

            "status_to",
            "status_to_display",

            "notes",
            "created_at",
        ]

        read_only_fields = fields

    def get_status_from_display(self, obj):
        if not obj.status_from:
            return None

        return obj.get_status_from_display()


# =============================================================
# DISPUTE EVIDENCE SERIALIZER
# =============================================================

class DisputeEvidenceSerializer(serializers.ModelSerializer):

    uploaded_by_email = serializers.EmailField(
        source="uploaded_by.email",
        read_only=True,
    )

    class Meta:
        model = DisputeEvidence

        fields = [
            "id",
            "dispute",
            "uploaded_by",
            "uploaded_by_email",
            "evidence_type",
            "file_attachment",
            "description",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "uploaded_by",
            "created_at",
        ]




# =============================================================
# DISPUTE SERIALIZER
# =============================================================

# class DisputeSerializer(serializers.ModelSerializer):

#     opened_by_email = serializers.EmailField(
#         source="opened_by.email",
#         read_only=True,
#     )

#     against_user_email = serializers.EmailField(
#         source="against_user.email",
#         read_only=True,
#     )

#     assigned_admin_email = serializers.EmailField(
#         source="assigned_admin.email",
#         read_only=True,
#         allow_null=True,
#     )

#     resolved_by_email = serializers.EmailField(
#         source="resolved_by.email",
#         read_only=True,
#         allow_null=True,
#     )

#     class Meta:
#         model = Dispute

#         fields = [
#             "id",
#             "booking",

#             "opened_by",
#             "opened_by_email",

#             "against_user",
#             "against_user_email",

#             "assigned_admin",
#             "assigned_admin_email",

#             "resolved_by",
#             "resolved_by_email",

#             "last_updated_by",

#             "reason",
#             "status",
#             "resolution",

#             "description",
#             "admin_notes",

#             "disputed_amount",

#             "is_reopened",
#             "sender_notified",
#             "traveler_notified",

#             "created_at",
#             "updated_at",
#             "resolved_at",
#         ]

#         read_only_fields = [
#             "id",
#             "opened_by",
#             "assigned_admin",
#             "resolved_by",
#             "last_updated_by",
#             "status",
#             "resolution",
#             "is_reopened",
#             "sender_notified",
#             "traveler_notified",
#             "created_at",
#             "updated_at",
#             "resolved_at",
#         ]



# =============================================================
# USER DISPUTE DETAIL SERIALIZERS
# Sender / Traveler ONLY
# =============================================================

from decimal import Decimal
from rest_framework import serializers


# =============================================================
# USER DISPUTE BOOKING DETAIL
# =============================================================

class UserDisputeBookingSerializer(serializers.ModelSerializer):
    """
    Booking information visible to Sender / Traveler.
    """

    class Meta:
        model = Booking

        fields = [
            "id",
            "tracking_number",
            "status",
            "payment_status",
        ]

        read_only_fields = fields


# =============================================================
# USER DISPUTE EVIDENCE
# =============================================================

class UserDisputeEvidenceSerializer(serializers.ModelSerializer):
    """
    Evidence visible to Sender / Traveler.

    The user can see evidence that has been submitted.
    Uploading new evidence is handled by the existing
    evidence upload API.
    """

    uploaded_by_email = serializers.EmailField(
        source="uploaded_by.email",
        read_only=True,
    )

    file_url = serializers.SerializerMethodField()

    evidence_type_display = serializers.CharField(
        source="get_evidence_type_display",
        read_only=True,
    )

    class Meta:
        model = DisputeEvidence

        fields = [
            "id",
            "dispute",
            "uploaded_by",
            "uploaded_by_email",
            "evidence_type",
            "evidence_type_display",
            "file_url",
            "description",
            "created_at",
        ]

        read_only_fields = fields

    def get_file_url(self, obj):
        """
        Return Cloudinary URL for existing evidence.
        """

        if not obj.file_attachment:
            return None

        try:
            return obj.file_attachment.url
        except Exception:
            return None


# =============================================================
# USER DISPUTE MESSAGE
# =============================================================

class UserDisputeMessageSerializer(serializers.ModelSerializer):
    """
    Messages visible to Sender / Traveler.

    IMPORTANT:
    Internal admin notes should NOT be exposed here.

    Only real conversation messages should be returned.
    """

    sender_email = serializers.EmailField(
        source="sender.email",
        read_only=True,
    )

    sender_name = serializers.SerializerMethodField()

    sender_profile_picture = serializers.SerializerMethodField()

    is_mine = serializers.SerializerMethodField()

    sender_role = serializers.SerializerMethodField()

    class Meta:
        model = DisputeMessage

        fields = [
            "id",
            "sender",
            "sender_email",
            "sender_name",
            "sender_profile_picture",
            "sender_role",
            "message_text",
            "is_mine",
            "created_at",
        ]

        read_only_fields = fields

    # ---------------------------------------------------------
    # SENDER NAME
    # ---------------------------------------------------------

    def get_sender_name(self, obj):

        sender = obj.sender

        if not sender:
            return "Unknown User"

        profile = getattr(
            sender,
            "profile",
            None
        )

        if profile:

            full_name = getattr(
                profile,
                "full_name",
                None
            )

            if full_name:
                return str(full_name).strip()

        if hasattr(sender, "get_full_name"):

            full_name = (
                sender.get_full_name()
                or ""
            ).strip()

            if full_name:
                return full_name

        return (
            getattr(
                sender,
                "username",
                None
            )
            or getattr(
                sender,
                "email",
                None
            )
            or "Unknown User"
        )

    # ---------------------------------------------------------
    # PROFILE PICTURE
    # ---------------------------------------------------------

    def get_sender_profile_picture(self, obj):

        sender = obj.sender

        if not sender:
            return None

        profile = getattr(
            sender,
            "profile",
            None
        )

        if not profile:
            return None

        picture = getattr(
            profile,
            "profile_picture",
            None
        )

        if not picture:
            return None

        try:
            return picture.url
        except Exception:
            return str(picture)

    # ---------------------------------------------------------
    # IS MINE
    # ---------------------------------------------------------

    def get_is_mine(self, obj):

        request = self.context.get("request")

        if not request:
            return False

        if not request.user.is_authenticated:
            return False

        return (
            obj.sender_id == request.user.id
        )

    # ---------------------------------------------------------
    # SENDER ROLE
    # ---------------------------------------------------------

    def get_sender_role(self, obj):

        dispute = obj.dispute
        sender = obj.sender

        if getattr(sender, "is_staff", False):
            return "ADMIN"

        if sender == dispute.opened_by:
            return "OPENED_BY"

        if sender == dispute.against_user:
            return "AGAINST_USER"

        return "USER"


# =============================================================
# USER DISPUTE HISTORY
# =============================================================

class UserDisputeHistorySerializer(
    serializers.ModelSerializer
):
    """
    Safe dispute timeline for Sender / Traveler.

    Internal actor information is intentionally hidden.
    """

    action_display = serializers.CharField(
        source="get_action_display",
        read_only=True,
    )

    status_from_display = serializers.SerializerMethodField()

    status_to_display = serializers.CharField(
        source="get_status_to_display",
        read_only=True,
    )

    class Meta:
        model = DisputeHistory

        fields = [
            "id",

            "action",
            "action_display",

            "status_from",
            "status_from_display",

            "status_to",
            "status_to_display",

            "notes",
            "created_at",
        ]

        read_only_fields = fields

    def get_status_from_display(self, obj):

        if not obj.status_from:
            return None

        return obj.get_status_from_display()


# =============================================================
# SENDER / TRAVELER DISPUTE DETAIL
# =============================================================

from decimal import Decimal

from rest_framework import serializers

from .models import Dispute
from .enums import (
    DisputeStatus,
    ResolutionType,
)

from apps.accounts.serializers import UserBriefSerializer


class SenderDisputeDetailSerializer(
    serializers.ModelSerializer
):

    # =========================================================
    # BOOKING
    # =========================================================

    booking = UserDisputeBookingSerializer(
        read_only=True
    )

    # =========================================================
    # USERS
    # =========================================================

    opened_by = UserBriefSerializer(
        read_only=True
    )

    against_user = UserBriefSerializer(
        read_only=True
    )

    # =========================================================
    # DISPLAY FIELDS
    # =========================================================

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

    # =========================================================
    # AMOUNT
    # =========================================================

    disputed_amount = serializers.SerializerMethodField()

    # =========================================================
    # SETTLEMENT
    # =========================================================

    settlement = serializers.SerializerMethodField()

    # =========================================================
    # TIMELINE
    # =========================================================

    timeline = serializers.SerializerMethodField()

    # =========================================================
    # RESOLUTION INFO
    # =========================================================

    resolution_info = serializers.SerializerMethodField()

    # =========================================================
    # EVIDENCE
    # =========================================================

    evidence = UserDisputeEvidenceSerializer(
        many=True,
        read_only=True
    )

    # =========================================================
    # MESSAGES
    # =========================================================

    messages = serializers.SerializerMethodField()

    # =========================================================
    # HISTORY
    # =========================================================

    history = UserDisputeHistorySerializer(
        many=True,
        read_only=True
    )

    # =========================================================
    # FRONTEND PERMISSIONS
    # =========================================================

    permissions = serializers.SerializerMethodField()

    # =========================================================
    # META
    # =========================================================

    class Meta:

        model = Dispute

        fields = [
            "id",

            # Booking
            "booking",

            # Parties
            "opened_by",
            "against_user",

            # Dispute
            "reason",
            "reason_display",
            "description",

            # Money
            "disputed_amount",
            "settlement",

            # Status
            "status",
            "status_display",

            # Resolution
            "resolution",
            "resolution_display",
            "resolution_info",

            # Timeline
            "timeline",

            # Evidence
            "evidence",

            # Conversation
            "messages",

            # History
            "history",

            # Dates
            "created_at",
            "updated_at",
            "resolved_at",

            # Frontend permissions
            "permissions",
        ]

        read_only_fields = fields

    # =========================================================
    # DISPUTED AMOUNT
    # =========================================================

    def get_disputed_amount(self, obj):

        amount = str(
            obj.disputed_amount or Decimal("0.00")
        )

        request = self.context.get("request")

        if not request:
            return amount

        user = request.user

        # -----------------------------------------------------
        # Before resolution
        # -----------------------------------------------------

        if obj.status != DisputeStatus.RESOLVED:
            return amount

        # -----------------------------------------------------
        # Full / Partial Refund
        #
        # Sender gets money
        # Traveler loses money
        # -----------------------------------------------------

        if obj.resolution in [
            ResolutionType.FULL_REFUND,
            ResolutionType.PARTIAL_REFUND,
        ]:

            if user == obj.opened_by:
                return f"+{amount}"

            if user == obj.against_user:
                return f"-{amount}"

        # -----------------------------------------------------
        # Release Escrow
        #
        # Traveler gets money
        # Sender loses money
        # -----------------------------------------------------

        if obj.resolution == ResolutionType.RELEASE_ESCROW:

            if user == obj.against_user:
                return f"+{amount}"

            if user == obj.opened_by:
                return f"-{amount}"

        # -----------------------------------------------------
        # NO ACTION
        #
        # No financial movement.
        # -----------------------------------------------------

        if obj.resolution == ResolutionType.NO_ACTION:
            return amount

        return amount

    # =========================================================
    # SETTLEMENT
    # =========================================================

    def get_settlement(self, obj):

        total = (
            obj.disputed_amount
            or Decimal("0.00")
        )

        refund_ratio = Decimal("0.00")

        # -----------------------------------------------------
        # FULL REFUND
        # -----------------------------------------------------

        if obj.resolution == ResolutionType.FULL_REFUND:

            refund_ratio = Decimal("1.00")

        # -----------------------------------------------------
        # PARTIAL REFUND
        # -----------------------------------------------------

        elif obj.resolution == ResolutionType.PARTIAL_REFUND:

            refund_ratio = getattr(
                obj,
                "refund_ratio",
                Decimal("0.50")
            )

        # -----------------------------------------------------
        # RELEASE ESCROW
        # -----------------------------------------------------

        elif obj.resolution == ResolutionType.RELEASE_ESCROW:

            refund_ratio = Decimal("0.00")

        # -----------------------------------------------------
        # NO ACTION
        # -----------------------------------------------------

        elif obj.resolution == ResolutionType.NO_ACTION:

            refund_ratio = Decimal("0.00")

        # -----------------------------------------------------
        # Calculate sender refund
        # -----------------------------------------------------

        sender_refund = (
            total * refund_ratio
        ).quantize(
            Decimal("0.01")
        )

        # -----------------------------------------------------
        # Traveler payout
        # -----------------------------------------------------

        traveler_payout = (
            total - sender_refund
        ).quantize(
            Decimal("0.01")
        )

        # -----------------------------------------------------
        # IMPORTANT:
        # For NO_ACTION, don't report a financial settlement.
        # -----------------------------------------------------

        if obj.resolution == ResolutionType.NO_ACTION:

            sender_refund = Decimal("0.00")
            traveler_payout = Decimal("0.00")

        return {
            "currency": "USD",

            "total_amount": str(
                total
            ),

            "refund_ratio": str(
                refund_ratio
            ),

            "sender_refund": str(
                sender_refund
            ),

            "traveler_payout": str(
                traveler_payout
            ),
        }

    # =========================================================
    # TIMELINE
    # =========================================================

    def get_timeline(self, obj):

        assigned_at = None

        assigned_history = (
            obj.history
            .filter(
                action="ASSIGNED"
            )
            .order_by(
                "created_at"
            )
            .first()
        )

        if assigned_history:
            assigned_at = (
                assigned_history.created_at
            )

        return {
            "opened_at": obj.created_at,
            "assigned_at": assigned_at,
            "resolved_at": obj.resolved_at,
        }

    # =========================================================
    # RESOLUTION INFO
    # =========================================================

    def get_resolution_info(self, obj):

        if obj.status != DisputeStatus.RESOLVED:
            return None

        if not obj.resolution:
            return None

        messages = {

            # -------------------------------------------------
            # FULL REFUND
            # -------------------------------------------------

            ResolutionType.FULL_REFUND:
                "Your dispute was resolved with a full refund.",

            # -------------------------------------------------
            # PARTIAL REFUND
            # -------------------------------------------------

            ResolutionType.PARTIAL_REFUND:
                "Your dispute was resolved with a partial refund.",

            # -------------------------------------------------
            # RELEASE ESCROW
            # -------------------------------------------------

            ResolutionType.RELEASE_ESCROW:
                "Your dispute was resolved and the escrow was released to the traveler.",

            # -------------------------------------------------
            # NO ACTION
            # -------------------------------------------------

            ResolutionType.NO_ACTION:
                "Your dispute was resolved without any financial adjustment.",
        }

        return {
            "type": obj.resolution,

            "type_display": (
                obj.get_resolution_display()
            ),

            "message": messages.get(
                obj.resolution,
                "Your dispute has been resolved."
            ),
        }

    # =========================================================
    # MESSAGES
    # =========================================================

    def get_messages(self, obj):

        """
        Sender sees:

        - Sender messages
        - Traveler messages
        - Admin messages

        Sender does NOT see:

        - Internal admin notes
        """

        queryset = (
            obj.messages
            .filter(
                is_admin_note=False
            )
            .select_related(
                "sender"
            )
            .order_by(
                "created_at"
            )
        )

        serializer = UserDisputeMessageSerializer(
            queryset,
            many=True,
            context=self.context
        )

        return serializer.data

    # =========================================================
    # FRONTEND PERMISSIONS
    # =========================================================

    def get_permissions(self, obj):

        request = self.context.get("request")

        if not request:
            return {
                "can_send_message": False,
                "can_upload_evidence": False,
                "can_reopen": False,
            }

        user = request.user

        # -----------------------------------------------------
        # Only dispute participants
        # -----------------------------------------------------

        if user not in [
            obj.opened_by,
            obj.against_user,
        ]:

            return {
                "can_send_message": False,
                "can_upload_evidence": False,
                "can_reopen": False,
            }

        # -----------------------------------------------------
        # OPEN
        # -----------------------------------------------------

        if obj.status == DisputeStatus.OPEN:

            return {
                "can_send_message": True,
                "can_upload_evidence": True,
                "can_reopen": False,
            }

        # -----------------------------------------------------
        # UNDER REVIEW
        # -----------------------------------------------------

        if obj.status == DisputeStatus.UNDER_REVIEW:

            return {
                "can_send_message": True,
                "can_upload_evidence": True,
                "can_reopen": False,
            }

        # -----------------------------------------------------
        # WAITING FOR USER
        #
        # This is particularly important for your system.
        #
        # Admin can request evidence through the message/request
        # flow and the user can respond.
        # -----------------------------------------------------

        if obj.status == DisputeStatus.WAITING_FOR_USER:

            return {
                "can_send_message": True,
                "can_upload_evidence": True,
                "can_reopen": False,
            }

        # -----------------------------------------------------
        # RESOLVED
        # -----------------------------------------------------

        if obj.status == DisputeStatus.RESOLVED:

            return {
                "can_send_message": False,
                "can_upload_evidence": False,
                "can_reopen": False,
            }

        # -----------------------------------------------------
        # REJECTED
        # -----------------------------------------------------

        if obj.status == DisputeStatus.REJECTED:

            return {
                "can_send_message": False,
                "can_upload_evidence": False,
                "can_reopen": False,
            }

        # -----------------------------------------------------
        # CLOSED
        # -----------------------------------------------------

        if obj.status == DisputeStatus.CLOSED:

            return {
                "can_send_message": False,
                "can_upload_evidence": False,
                "can_reopen": False,
            }

        # -----------------------------------------------------
        # Default
        # -----------------------------------------------------

        return {
            "can_send_message": False,
            "can_upload_evidence": False,
            "can_reopen": False,
        }
    

class TravelerEvidenceSerializer(serializers.ModelSerializer):
    """
    Serializer specifically for Traveler evidence uploads.

    Traveler provides only:
        file_attachment
        description

    Backend determines:
        dispute
        uploaded_by
    """

    file_attachment = serializers.FileField(
        write_only=True,
        required=True,
    )

    class Meta:
        model = DisputeEvidence

        fields = [
            "id",
            "file_attachment",
            "description",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "created_at",
        ]

    def validate_file_attachment(self, value):

        max_size_mb = 10

        if (
            hasattr(value, "size")
            and value.size > max_size_mb * 1024 * 1024
        ):
            raise serializers.ValidationError(
                f"Maximum allowed file size is {max_size_mb} MB."
            )

        return value

    def validate(self, attrs):

        dispute = self.context.get("dispute")

        if not dispute:
            raise serializers.ValidationError(
                "Dispute context is required."
            )

        if dispute.status in [
            DisputeStatus.RESOLVED,
            DisputeStatus.REJECTED,
        ]:
            raise serializers.ValidationError(
                "Evidence cannot be uploaded because this dispute is closed."
            )

        return attrs