import logging
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.bookings.models import Booking, BookingStatus
from apps.payment.models import BookingPayment, BookingPaymentStatus
from apps.notifications.services import notify_dispute_opened,notify_admins_dispute_opened
from datetime import timedelta
from django.utils import timezone
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
from django.db import transaction, IntegrityError
from apps.disputes.models import (
    Dispute,
    DisputeStatus,
    DisputeHistoryAction,
    DisputeReason,
    ResolutionType,
    EvidenceType,
    DisputeEvidence,
    DisputeHistory,
)

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
    def create_dispute(
        *,
        booking_id,
        user,
        reason: str,
        description: str,
        disputed_amount,
        evidence_files=None,
    ) -> Dispute:
        """
        Atomically creates a new Dispute ticket for a completed booking.
        If an error occurs at any point, the entire operation rolls back.
        """

        # ==============================================================================
        # 1. FETCH AND LOCK BOOKING
        # ==============================================================================
        try:
            booking = (
                Booking.objects
                .select_for_update()
                .select_related("sender", "traveler")
                .get(id=booking_id)
            )
        except Booking.DoesNotExist:
            raise ValidationError({"booking_id": "Booking not found."})

        # ==============================================================================
        # 2. PARTICIPANT VALIDATION
        # ==============================================================================
        if user.id not in [booking.sender_id, booking.traveler_id]:
            raise ValidationError(
                "Authorization Error: You must be an active party to this booking to open a dispute."
            )

        # Determine counterparty
        against_user = booking.traveler if user.id == booking.sender_id else booking.sender

        # ==============================================================================
        # 3. BOOKING STATUS & WINDOW CHECKS
        # ==============================================================================
        if booking.status != BookingStatus.COMPLETED:
            raise ValidationError(
                "Workflow Error: Disputes can only be opened for completed bookings."
            )

        if not getattr(booking, "completed_at", None):
            raise ValidationError(
                "Workflow Error: This booking lacks a valid completion timestamp."
            )

        now = timezone.now()
        dispute_deadline = booking.completed_at + timedelta(hours=24)
        if now > dispute_deadline:
            raise ValidationError(
                "Time Frame Exceeded: The 24-hour dispute window for this booking has expired."
            )

        # ==============================================================================
        # 4. ONE-TO-ONE / EXISTING DISPUTE CHECK
        # ==============================================================================
        # Since Dispute.booking is a OneToOneField, check for existing linked dispute
        existing_dispute = Dispute.objects.select_for_update().filter(booking=booking).first()

        if existing_dispute:
            if existing_dispute.status in [
                DisputeStatus.OPEN,
                DisputeStatus.UNDER_REVIEW,
                DisputeStatus.WAITING_FOR_USER,
            ]:
                raise ValidationError("A dispute ticket is already active for this booking.")

            if existing_dispute.status in [
                DisputeStatus.RESOLVED,
                DisputeStatus.CLOSED,
            ]:
                raise ValidationError("This booking already has a resolved or closed dispute.")

        # ==============================================================================
        # 5. ESCROW / PAYMENT VALIDATION & FREEZE
        # ==============================================================================
        try:
            payment = BookingPayment.objects.select_for_update().get(booking=booking)
        except BookingPayment.DoesNotExist:
            raise ValidationError("Payment record not found for this booking.")

        # Ensure payment is authorized in escrow before freezing
        if payment.status != BookingPaymentStatus.AUTHORIZED:
            raise ValidationError("This booking does not have an active escrow payment hold.")

        # ==============================================================================
        # 6. DISPUTED AMOUNT VALIDATION
        # ==============================================================================
        try:
            disputed_amount = Decimal(str(disputed_amount))
        except (ValueError, TypeError):
            raise ValidationError({"disputed_amount": "Invalid disputed amount provided."})

        if disputed_amount <= Decimal("0.00"):
            raise ValidationError({"disputed_amount": "Disputed amount must be greater than zero."})

        agreed_reward = getattr(booking, "agreed_reward", None)
        if agreed_reward and disputed_amount > agreed_reward:
            raise ValidationError(
                {"disputed_amount": f"Disputed amount cannot exceed agreed reward (${agreed_reward})."}
            )

        # Map string reason to DisputeReason text choices safely
        if reason not in DisputeReason.values:
            reason = DisputeReason.OTHER

        # ==============================================================================
        # 7. EXECUTE DISPUTE CREATION
        # ==============================================================================
        try:
            # Construct Dispute instance
            dispute = Dispute(
                booking=booking,
                opened_by=user,
                against_user=against_user,
                reason=reason,
                status=DisputeStatus.OPEN,
                description=description,
                disputed_amount=disputed_amount,
                last_updated_by=user,
            )

            # Validate against model clean() restrictions
            dispute.full_clean()
            dispute.save()

            # Update Payment Escrow Status to DISPUTED (if enum exists on payment model)
            if hasattr(BookingPaymentStatus, "DISPUTED"):
                payment.status = BookingPaymentStatus.DISPUTED
                payment.save(update_fields=["status"])

            # Save Evidence files if provided
            if evidence_files:
                for file_obj in evidence_files:
                    if not file_obj:
                        continue
                    
                    DisputeEvidence.objects.create(
                        dispute=dispute,
                        uploaded_by=user,
                        file_attachment=file_obj,
                        evidence_type=EvidenceType.IMAGE,  # Uses explicit default choice
                    )

            # Record Audit Trail Log
            DisputeHistory.objects.create(
                dispute=dispute,
                actor=user,
                action=DisputeHistoryAction.OPENED,
                status_from=DisputeStatus.OPEN,
                status_to=DisputeStatus.OPEN,
                notes=f"Dispute ticket initialized by {user.email}.",
            )

        except IntegrityError as exc:
            logger.exception(
                "Dispute creation DB integrity failure | Booking=%s User=%s",
                booking.id,
                user.id,
            )
            raise ValidationError(
                "Unable to process dispute due to a duplicate or concurrent request. Please try again."
            )
        except ValidationError as exc:
            # Re-raise model clean validation errors directly
            raise exc
        except Exception as exc:
            logger.exception(
                "Dispute creation unexpected failure | Booking=%s User=%s | Error: %s",
                booking.id,
                user.id,
                str(exc),
            )
            raise ValidationError("An unexpected error occurred while processing your dispute request.")

        # ==============================================================================
        # 8. POST-COMMIT NOTIFICATIONS (Triggers ONLY when DB transaction succeeds)
        # ==============================================================================
        transaction.on_commit(
            lambda: notify_dispute_opened(
                user=against_user,
                dispute=dispute,
            )
        )

        transaction.on_commit(
            lambda: notify_admins_dispute_opened(
                dispute=dispute,
            )
        )

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
                action=DisputeHistoryAction.EVIDENCE_ADDED,
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
    def add_evidence(
        dispute_id,
        uploaded_by,
        file_object,
        evidence_type,
        description=""
    ) -> DisputeEvidence:
        """
        Save uploaded evidence for a dispute.
        """
        dispute = DisputeService.get_dispute(
            dispute_id=dispute_id,
            user=uploaded_by
        )

        if dispute.status in [
            DisputeStatus.RESOLVED,
            DisputeStatus.REJECTED,
        ]:
            raise ValidationError(
                "Evidence cannot be uploaded because this dispute has been closed."
            )

        evidence = DisputeEvidence.objects.create(
            dispute=dispute,
            uploaded_by=uploaded_by,
            file_attachment=file_object,
            evidence_type=evidence_type,
            description=description,
        )

        old_status = dispute.status
        dispute.last_updated_by = uploaded_by

        if dispute.status == DisputeStatus.WAITING_FOR_USER:
            dispute.status = DisputeStatus.UNDER_REVIEW
            dispute.save(
                update_fields=[
                    "status",
                    "updated_at",
                    "last_updated_by",
                ]
            )

            DisputeHistory.objects.create(
                dispute=dispute,
                actor=uploaded_by,
                action=DisputeHistoryAction.EVIDENCE_ADDED,
                status_from=old_status,
                status_to=DisputeStatus.UNDER_REVIEW,
                notes=f"Evidence uploaded by {uploaded_by.email}.",
            )
        else:
            dispute.save(
                update_fields=[
                    "updated_at",
                    "last_updated_by",
                ]
            )

        logger.info(
            "Evidence %s uploaded successfully.",
            evidence.id,
            extra={
                "dispute": str(dispute.id),
                "user": str(uploaded_by.id),
                "type": evidence_type,
            },
        )

        return evidence