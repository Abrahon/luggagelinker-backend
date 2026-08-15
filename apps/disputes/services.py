import logging
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.bookings.models import Booking, BookingStatus
from apps.payment.models import BookingPayment, BookingPaymentStatus
from apps.notifications.services import notify_dispute_opened,notify_admin_dispute_opened
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

    # @staticmethod
    # @transaction.atomic
    # def create_dispute(
    #     booking_id,
    #     user,
    #     reason,
    #     description,
    #     disputed_amount,
    #     evidence_files=None,
    # ):
    #     try:
    #         booking = (
    #             Booking.objects
    #             .select_for_update()
    #             .select_related("sender", "traveler")
    #             .get(id=booking_id)
    #         )
    #     except Booking.DoesNotExist:
    #         raise ValidationError("Booking not found.")

    #     # --------------------------------------------------
    #     # 1. PARTICIPANT CHECK
    #     # --------------------------------------------------
    #     if user not in [booking.sender, booking.traveler]:
    #         raise ValidationError(
    #             "You are not allowed to create a dispute for this booking."
    #         )

    #     # --------------------------------------------------
    #     # 2. ONLY COMPLETED BOOKINGS CAN BE DISPUTED
    #     # --------------------------------------------------
    #     if booking.status != BookingStatus.COMPLETED:
    #         raise ValidationError(
    #             "Disputes can only be opened for completed bookings."
    #         )

    #     # --------------------------------------------------
    #     # 3. 24-HOUR DISPUTE WINDOW
    #     # --------------------------------------------------
    #     if not booking.completed_at:
    #         raise ValidationError(
    #             "This booking does not have a completion timestamp."
    #         )

    #     dispute_deadline = booking.completed_at + timedelta(hours=24)

    #     if timezone.now() > dispute_deadline:
    #         raise ValidationError(
    #             "The 24-hour dispute window has expired."
    #         )

    #     # --------------------------------------------------
    #     # 4. PREVENT DUPLICATE DISPUTE
    #     # --------------------------------------------------
    #     if Dispute.objects.filter(booking=booking).exists():
    #         raise ValidationError(
    #             "A dispute already exists for this booking."
    #         )

    #     # --------------------------------------------------
    #     # 5. PAYMENT / ESCROW VALIDATION
    #     # --------------------------------------------------
    #     try:
    #         payment = BookingPayment.objects.get(booking=booking)
    #     except BookingPayment.DoesNotExist:
    #         raise ValidationError(
    #             "Payment record not found for this completed booking."
    #         )

    #     if payment.status != BookingPaymentStatus.AUTHORIZED:
    #         raise ValidationError(
    #             "This booking does not have an active escrow payment."
    #         )

    #     # --------------------------------------------------
    #     # 6. DETERMINE OTHER PARTICIPANT
    #     # --------------------------------------------------
    #     against_user = (
    #         booking.traveler
    #         if user == booking.sender
    #         else booking.sender
    #     )

    #     # --------------------------------------------------
    #     # 7. CREATE DISPUTE
    #     # --------------------------------------------------
    #     dispute = Dispute.objects.create(
    #         booking=booking,
    #         opened_by=user,
    #         against_user=against_user,
    #         reason=reason,
    #         description=description,
    #         disputed_amount=disputed_amount,
    #         status=DisputeStatus.OPEN,
    #         last_updated_by=user,
    #     )

    #     # --------------------------------------------------
    #     # 8. INITIAL EVIDENCE
    #     # --------------------------------------------------
    #     if evidence_files:
    #         for evidence in evidence_files:
    #             DisputeEvidence.objects.create(
    #                 dispute=dispute,
    #                 uploaded_by=user,
    #                 file_attachment=evidence,
    #             )

    #     # --------------------------------------------------
    #     # 9. HISTORY
    #     # --------------------------------------------------
    #     DisputeHistory.objects.create(
    #         dispute=dispute,
    #         actor=user,
    #         action=DisputeHistoryAction.OPENED,
    #         status_from=DisputeStatus.OPEN,
    #         status_to=DisputeStatus.OPEN,
    #         notes=f"Dispute opened by {user.email}.",
    #     )

    #     # --------------------------------------------------
    #     # 10. NOTIFICATION
    #     # --------------------------------------------------
    #     transaction.on_commit(
    #         lambda: notify_dispute_opened(
    #             user=against_user,
    #             dispute=dispute,
    #         )
    #     )

    #     return dispute





    @staticmethod
    @transaction.atomic
    def create_dispute(
        booking_id,
        user,
        reason,
        description,
        disputed_amount,
        evidence_files=None,
    ):
        # ==================================================
        # 1. GET + LOCK BOOKING
        # ==================================================

        try:
            booking = (
                Booking.objects
                .select_for_update()
                .select_related(
                    "sender",
                    "traveler",
                )
                .get(id=booking_id)
            )

        except Booking.DoesNotExist:
            raise ValidationError(
                "Booking not found."
            )

        # ==================================================
        # 2. PARTICIPANT CHECK
        # ==================================================

        if user.id not in [
            booking.sender_id,
            booking.traveler_id,
        ]:
            raise ValidationError(
                "You are not allowed to create a dispute for this booking."
            )

        # ==================================================
        # 3. COMPLETED BOOKING CHECK
        # ==================================================

        if booking.status != BookingStatus.COMPLETED:
            raise ValidationError(
                "Disputes can only be opened for completed bookings."
            )

        # ==================================================
        # 4. COMPLETION TIMESTAMP
        # ==================================================

        if not booking.completed_at:
            raise ValidationError(
                "This booking does not have a completion timestamp."
            )

        # ==================================================
        # 5. 24-HOUR DISPUTE WINDOW
        # ==================================================

        now = timezone.now()

        dispute_deadline = (
            booking.completed_at
            + timedelta(hours=24)
        )

        if now > dispute_deadline:
            raise ValidationError(
                "The 24-hour dispute window has expired."
            )

        # ==================================================
        # 6. CHECK EXISTING DISPUTE
        # ==================================================

        existing_dispute = (
            Dispute.objects
            .select_for_update()
            .filter(
                booking=booking,
            )
            .order_by("-created_at")
            .first()
        )

        if existing_dispute:

            # --------------------------------------------------
            # ACTIVE DISPUTE
            # --------------------------------------------------

            active_statuses = [
                DisputeStatus.OPEN,
                DisputeStatus.PENDING,
                DisputeStatus.UNDER_REVIEW,
            ]

            if existing_dispute.status in active_statuses:
                raise ValidationError(
                    "A dispute is already open for this booking."
                )

            # --------------------------------------------------
            # COMPLETED / RESOLVED DISPUTE
            # --------------------------------------------------

            terminal_statuses = [
                DisputeStatus.RESOLVED,
                DisputeStatus.CLOSED,
            ]

            if existing_dispute.status in terminal_statuses:
                raise ValidationError(
                    "This booking already has a resolved dispute."
                )

            # --------------------------------------------------
            # REJECTED / CANCELLED / FAILED
            # --------------------------------------------------

            retryable_statuses = [
                DisputeStatus.REJECTED,
                DisputeStatus.CANCELLED,
                DisputeStatus.FAILED,
            ]

            if existing_dispute.status in retryable_statuses:

                # IMPORTANT:
                # Do NOT delete the old dispute.
                #
                # Keep history/audit trail.
                #
                # A new dispute can be created below.

                pass

        # ==================================================
        # 7. PAYMENT / ESCROW VALIDATION
        # ==================================================

        try:
            payment = (
                BookingPayment.objects
                .select_for_update()
                .get(
                    booking=booking
                )
            )

        except BookingPayment.DoesNotExist:
            raise ValidationError(
                "Payment record not found for this completed booking."
            )

        if payment.status != BookingPaymentStatus.AUTHORIZED:
            raise ValidationError(
                "This booking does not have an active escrow payment."
            )

        # ==================================================
        # 8. VALIDATE DISPUTED AMOUNT
        # ==================================================

        try:
            disputed_amount = Decimal(
                str(disputed_amount)
            )
        except Exception:
            raise ValidationError(
                "Invalid disputed amount."
            )

        if disputed_amount <= Decimal("0.00"):
            raise ValidationError(
                "Disputed amount must be greater than zero."
            )

        # Optional but recommended:
        # Never allow dispute amount greater than booking reward.

        if disputed_amount > booking.agreed_reward:
            raise ValidationError(
                "Disputed amount cannot exceed the booking agreed reward."
            )

        # ==================================================
        # 9. DETERMINE OTHER PARTICIPANT
        # ==================================================

        if user.id == booking.sender_id:
            against_user = booking.traveler
        else:
            against_user = booking.sender

        # ==================================================
        # 10. CREATE DISPUTE
        # ==================================================

        try:

            dispute = Dispute.objects.create(
                booking=booking,
                opened_by=user,
                against_user=against_user,
                reason=reason,
                description=description,
                disputed_amount=disputed_amount,
                status=DisputeStatus.OPEN,
                last_updated_by=user,
            )

            # ==================================================
            # 11. INITIAL EVIDENCE
            # ==================================================

            if evidence_files:

                for evidence in evidence_files:

                    if not evidence:
                        continue

                    DisputeEvidence.objects.create(
                        dispute=dispute,
                        uploaded_by=user,
                        file_attachment=evidence,
                    )

            # ==================================================
            # 12. HISTORY
            # ==================================================

            DisputeHistory.objects.create(
                dispute=dispute,
                actor=user,
                action=DisputeHistoryAction.OPENED,
                status_from=DisputeStatus.OPEN,
                status_to=DisputeStatus.OPEN,
                notes=(
                    f"Dispute opened by {user.email}."
                ),
            )

        except IntegrityError as exc:

            # The atomic transaction will rollback.
            #
            # Do not leave a partially-created dispute/ledger
            # behind.

            logger.exception(
                "Dispute creation integrity error | "
                "Booking=%s User=%s",
                booking.id,
                user.id,
            )

            raise ValidationError(
                "Unable to open the dispute because "
                "another dispute operation is already in progress. "
                "Please try again."
            )

        except Exception:

            logger.exception(
                "Dispute creation failed | "
                "Booking=%s User=%s",
                booking.id,
                user.id,
            )

            # Raising the exception is important.
            # @transaction.atomic will rollback everything.

            raise

        # ==================================================
        # 13. NOTIFICATION
        # ==================================================

        # ==================================================
        # NOTIFICATIONS
        # ==================================================

        transaction.on_commit(
            lambda: notify_dispute_opened(
                user=against_user,
                dispute=dispute,
            )
        )

        transaction.on_commit(
            lambda: notify_admin_dispute_opened(
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