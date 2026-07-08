import decimal
import logging
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from .models import Dispute, DisputeHistory
from .services import DisputeService
from .choices import DisputeStatus, ResolutionType, DisputeHistoryAction

# 💳 Concrete internal service layouts
from apps.payment.services import BookingPaymentService
from apps.payment.models import BookingPayment, BookingPaymentStatus
from apps.wallets.services import WalletService
from apps.notifications.services import (
    notify_dispute_resolved,
    notify_dispute_evidence_requested,
    notify_refund_completed,
    notify_wallet_credited
)

logger = logging.getLogger(__name__)


class AdminDisputeService:

    @staticmethod
    def _verify_admin_clearance(admin_user):
        if not admin_user.is_staff and not admin_user.is_superuser:
            raise ValidationError("Permission Denied: Only platform administrators can perform this action.")

    @staticmethod
    @transaction.atomic
    def assign_admin(dispute_id, admin_user) -> Dispute:
        AdminDisputeService._verify_admin_clearance(admin_user)
        
        try:
            dispute = Dispute.objects.select_for_update().get(id=dispute_id)
        except Dispute.DoesNotExist:
            raise ValidationError("Dispute not found.")
            
        if dispute.assigned_admin and dispute.assigned_admin != admin_user:
            raise ValidationError("Dispute already assigned to another administrator.")

        old_status = dispute.status
        dispute.assigned_admin = admin_user
        dispute.status = DisputeStatus.UNDER_REVIEW
        dispute.last_updated_by = admin_user
        dispute.save(update_fields=["assigned_admin", "status", "updated_at", "last_updated_by"])
        
        DisputeHistory.objects.create(
            dispute=dispute,
            actor=admin_user,
            action=DisputeHistoryAction.ASSIGNED,
            status_from=old_status,
            status_to=DisputeStatus.UNDER_REVIEW,
            notes=f"Case file assigned to admin: {admin_user.email}"
        )
        
        logger.info("Dispute %s assigned to admin %s", dispute.id, admin_user.id)
        return dispute

    @staticmethod
    @transaction.atomic
    def request_more_evidence(dispute_id, admin_user, message_text) -> Dispute:
        AdminDisputeService._verify_admin_clearance(admin_user)
        
        try:
            dispute = Dispute.objects.select_for_update().get(id=dispute_id)
        except Dispute.DoesNotExist:
            raise ValidationError("Dispute not found.")
            
        if dispute.status != DisputeStatus.UNDER_REVIEW:
            raise ValidationError(f"Invalid status state: Cannot request evidence unless ticket is UNDER_REVIEW. Current: {dispute.status}")

        old_status = dispute.status
        dispute.status = DisputeStatus.WAITING_FOR_USER
        dispute.last_updated_by = admin_user
        dispute.save(update_fields=["status", "updated_at", "last_updated_by"])
        
        DisputeService.add_message(dispute_id=dispute.id, sender=admin_user, message_text=message_text)
        
        DisputeHistory.objects.create(
            dispute=dispute,
            actor=admin_user,
            action=DisputeHistoryAction.EVIDENCE_REQUESTED,
            status_from=old_status,
            status_to=DisputeStatus.WAITING_FOR_USER,
            notes="Administrative information request dispatched to users."
        )

        transaction.on_commit(lambda: notify_dispute_evidence_requested(user=dispute.opened_by, dispute=dispute))
        transaction.on_commit(lambda: notify_dispute_evidence_requested(user=dispute.against_user, dispute=dispute))
        
        logger.info("Dispute %s state changed to WAITING_FOR_USER by admin %s", dispute.id, admin_user.id)
        return dispute

    @staticmethod
    @transaction.atomic
    def resolve(dispute_id, admin_user, resolution_type, admin_notes="", refund_ratio=decimal.Decimal("1.00")) -> Dispute:
        AdminDisputeService._verify_admin_clearance(admin_user)
        
        if not isinstance(refund_ratio, decimal.Decimal):
            raise ValidationError("Precision Error: refund_ratio parameters must be an explicit decimal instance.")
            
        try:
            dispute = Dispute.objects.select_for_update().select_related('booking').get(id=dispute_id)
        except Dispute.DoesNotExist:
            raise ValidationError("Dispute not found.")
        
        if dispute.status in [DisputeStatus.RESOLVED, DisputeStatus.REJECTED]:
            raise ValidationError("This dispute ledger instance has already been finalized.")

        old_status = dispute.status
        booking = dispute.booking
        total_held = dispute.disputed_amount

        try:
            payment = BookingPayment.objects.select_for_update().get(booking=booking, status=BookingPaymentStatus.AUTHORIZED)
        except BookingPayment.DoesNotExist:
            raise ValidationError("No active authorized escrow ledger record found for this disputed booking transaction.")

        # ─── RESOLUTION SELECTION ROUTING MATRIX ───
        if resolution_type == ResolutionType.REFUND:
            dispute.status = DisputeStatus.RESOLVED
            dispute.resolution = ResolutionType.REFUND
            
            # Use your built-in payment service infrastructure directly
            BookingPaymentService.refund(payment=payment)
            WalletService.refund_escrow_to_sender(booking=booking, amount=total_held)
            
            booking.payment_status = "REFUNDED"
            booking.status = "CANCELLED"
            booking.save(update_fields=["status", "payment_status"])

            transaction.on_commit(lambda: notify_refund_completed(user=booking.sender, booking=booking, amount=total_held))

        elif resolution_type == ResolutionType.RELEASE_ESCROW:
            dispute.status = DisputeStatus.RESOLVED
            dispute.resolution = ResolutionType.RELEASE_ESCROW
            
            BookingPaymentService.release(payment=payment)
            WalletService.release_escrow_to_traveler(booking=booking, amount=total_held)
            
            booking.payment_status = "PAID"
            booking.status = "COMPLETED"
            booking.save(update_fields=["status", "payment_status"])

            transaction.on_commit(lambda: notify_wallet_credited(user=booking.traveler, booking=booking, amount=total_held))

        elif resolution_type == ResolutionType.PARTIAL_REFUND:
            if not (decimal.Decimal("0.01") <= refund_ratio <= decimal.Decimal("0.99")):
                raise ValidationError("Partial refund calculation values must reside strictly between 0.01 and 0.99.")

            dispute.status = DisputeStatus.RESOLVED
            dispute.resolution = ResolutionType.PARTIAL_REFUND

            refund_to_sender = (total_held * refund_ratio).quantize(decimal.Decimal("0.01"))
            payout_to_traveler = total_held - refund_to_sender

            BookingPaymentService.partial_refund(payment=payment, refund_to_sender=refund_to_sender, payout_to_traveler=payout_to_traveler)
            WalletService.split_partial_escrow(booking=booking, sender_amt=refund_to_sender, traveler_amt=payout_to_traveler)
            
            booking.payment_status = "PARTIALLY_REFUNDED"
            booking.status = "COMPLETED"
            booking.save(update_fields=["status", "payment_status"])

            transaction.on_commit(lambda: notify_refund_completed(user=booking.sender, booking=booking, amount=refund_to_sender))
            transaction.on_commit(lambda: notify_wallet_credited(user=booking.traveler, booking=booking, amount=payout_to_traveler))

        elif resolution_type == ResolutionType.NO_ACTION:
            dispute.status = DisputeStatus.REJECTED
            dispute.resolution = ResolutionType.NO_ACTION
            
            booking.status = "COMPLETED"
            booking.save(update_fields=["status"])

        else:
            raise ValidationError(f"Invalid execution resolution choice type strategy: {resolution_type}")

        dispute.admin_notes = admin_notes
        dispute.resolved_by = admin_user
        dispute.resolved_at = timezone.now()
        dispute.last_updated_by = admin_user
        dispute.sender_notified = True
        dispute.traveler_notified = True
        dispute.save()

        # Route matching execution string label for standard logging mappings
        history_action_map = {
            ResolutionType.REFUND: DisputeHistoryAction.RESOLVED_REFUND,
            ResolutionType.RELEASE_ESCROW: DisputeHistoryAction.RESOLVED_RELEASE,
            ResolutionType.PARTIAL_REFUND: DisputeHistoryAction.RESOLVED_PARTIAL,
            ResolutionType.NO_ACTION: DisputeHistoryAction.REJECTED
        }

        DisputeHistory.objects.create(
            dispute=dispute,
            actor=admin_user,
            action=history_action_map.get(resolution_type, DisputeHistoryAction.CLOSED),
            status_from=old_status,
            status_to=dispute.status,
            notes=f"Verdict applied: {resolution_type}. Admin notes: {admin_notes}"
        )

        logger.info("Dispute %s resolved by %s using %s", dispute.id, admin_user.id, resolution_type)

        # Notify endpoints post transactional database commitment phase bounds
        transaction.on_commit(lambda: notify_dispute_resolved(user=booking.sender, dispute=dispute, resolution_type=resolution_type))
        transaction.on_commit(lambda: notify_dispute_resolved(user=booking.traveler, dispute=dispute, resolution_type=resolution_type))

        return dispute