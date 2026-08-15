import decimal
import logging
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

# 🏛️ Local Dispute App Imports
from apps.disputes.enums import DisputeHistoryAction, DisputeStatus, ResolutionType
from .models import Dispute, DisputeHistory
from .services import DisputeService

# 📅 Bookings App Imports (Aliased to avoid class collision)
from apps.bookings.models import (
    BookingStatus,
    PaymentStatus as BookingPaymentStatusEnum,  # 🟢 Used for booking.payment_status
)

# 💳 Payment App Imports (Aliased to avoid class collision)
from apps.payment.models import (
    BookingPayment,
    BookingPaymentStatus,
    PaymentStatus as PaymentAppStatusEnum,      # 🟢 Used for payment record status if needed
)
from apps.payment.services import BookingPaymentService

# 👛 Wallet & Notifications
from apps.notifications.services import (
    notify_dispute_evidence_requested,
    notify_dispute_resolution,
)
from apps.wallets.services import WalletService

logger = logging.getLogger(__name__)


class AdminDisputeService:

    @staticmethod
    def _verify_admin_clearance(admin_user):
        """Standardized structural permission gatekeeper."""
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

        # ✅ Fix #2: Verify dispute belongs to assigned admin before making updates
        if dispute.assigned_admin and dispute.assigned_admin != admin_user:
            raise ValidationError("This dispute is assigned to another administrator.")

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
    def resolve(dispute_id, admin_user, resolution_type, admin_notes="", refund_ratio="1.00") -> Dispute:
        AdminDisputeService._verify_admin_clearance(admin_user)
        
        # 1. Parse and validate refund ratio input
        try:
            refund_ratio = decimal.Decimal(str(refund_ratio))
        except (decimal.InvalidOperation, ValueError):
            raise ValidationError({
                "success": False,
                "message": "Invalid refund ratio parameter. Must be a valid numerical representation.",
                "code": "INVALID_REFUND_RATIO"
            })
            
        # 2. Fetch dispute record
        try:
            dispute = Dispute.objects.select_for_update().select_related("booking").get(id=dispute_id)
        except Dispute.DoesNotExist:
            raise ValidationError({
                "success": False,
                "message": "Dispute record not found.",
                "code": "DISPUTE_NOT_FOUND"
            })
        
        # 3. User-friendly status state checks
        if dispute.status == DisputeStatus.RESOLVED:
            raise ValidationError({
                "success": False,
                "message": "This dispute has already been resolved and cannot be resolved again.",
                "code": "DISPUTE_ALREADY_RESOLVED"
            })
        elif dispute.status == DisputeStatus.REJECTED:
            raise ValidationError({
                "success": False,
                "message": "This dispute has already been closed with a 'No Action' decision.",
                "code": "DISPUTE_ALREADY_CLOSED"
            })
        elif dispute.status == DisputeStatus.OPEN:
            raise ValidationError({
                "success": False,
                "message": "Assign this dispute to yourself before resolving it.",
                "code": "DISPUTE_NOT_ASSIGNED"
            })
        elif dispute.status == DisputeStatus.CLOSED:
            raise ValidationError({
                "success": False,
                "message": "This dispute has already been closed.",
                "code": "DISPUTE_CLOSED"
            })
        elif dispute.status not in [DisputeStatus.UNDER_REVIEW, DisputeStatus.WAITING_FOR_USER]:
            raise ValidationError({
                "success": False,
                "message": f"This dispute cannot be resolved while its status is '{dispute.get_status_display()}'.",
                "current_status": dispute.status,
                "code": "INVALID_DISPUTE_STATE"
            })

        # 4. Verify assigned admin authorization
        if dispute.assigned_admin and dispute.assigned_admin != admin_user:
            raise ValidationError({
                "success": False,
                "message": "This dispute is currently assigned to another administrator.",
                "assigned_admin": getattr(dispute.assigned_admin, "email", str(dispute.assigned_admin)),
                "code": "DISPUTE_ASSIGNED_TO_ANOTHER_ADMIN"
            })

        old_status = dispute.status
        booking = dispute.booking
        total_held = dispute.disputed_amount

        # 5. Lock and verify payment escrow state
        try:
            payment = BookingPayment.objects.select_for_update().get(
                booking=booking, 
                status=BookingPaymentStatus.AUTHORIZED
            )
        except BookingPayment.DoesNotExist:
            raise ValidationError({
                "success": False,
                "message": "The booking payment is not in an authorized escrow state and cannot be resolved.",
                "code": "ESCROW_NOT_FOUND"
            })

        # ─── RESOLUTION SELECTION ROUTING MATRIX ───
        # ─── RESOLUTION SELECTION ROUTING MATRIX ───
        if resolution_type == ResolutionType.FULL_REFUND:
            dispute.status = DisputeStatus.RESOLVED
            dispute.resolution = ResolutionType.FULL_REFUND
            
            BookingPaymentService.refund(payment=payment)
            
            # Safe Wallet Ledger Execution
            if hasattr(WalletService, "refund_escrow_to_sender"):
                WalletService.refund_escrow_to_sender(booking=booking, amount=total_held)
            elif hasattr(WalletService, "refund_escrow"):
                WalletService.refund_escrow(booking=booking, amount=total_held)
            elif hasattr(WalletService, "process_refund"):
                WalletService.process_refund(booking=booking, amount=total_held)
            else:
                logger.warning("WalletService has no refund method defined. Skipping wallet ledger update.")
            
            booking.payment_status = BookingPaymentStatusEnum.REFUNDED
            booking.status = BookingStatus.CANCELLED
            booking.save(update_fields=["status", "payment_status"])

        elif resolution_type == ResolutionType.RELEASE_ESCROW:
            dispute.status = DisputeStatus.RESOLVED
            dispute.resolution = ResolutionType.RELEASE_ESCROW
            
            BookingPaymentService.release(payment=payment)
            
            if hasattr(WalletService, "release_escrow_to_traveler"):
                WalletService.release_escrow_to_traveler(booking=booking, amount=total_held)
            elif hasattr(WalletService, "release_escrow"):
                WalletService.release_escrow(booking=booking, amount=total_held)
            else:
                logger.warning("WalletService has no release method defined. Skipping wallet ledger update.")
            
            booking.payment_status = getattr(BookingPaymentStatusEnum, "CAPTURED", BookingPaymentStatusEnum.PAID)
            booking.status = BookingStatus.COMPLETED
            booking.save(update_fields=["status", "payment_status"])

        elif resolution_type == ResolutionType.PARTIAL_REFUND:
            if not (decimal.Decimal("0.01") <= refund_ratio <= decimal.Decimal("0.99")):
                raise ValidationError({
                    "success": False,
                    "message": "Partial refund calculation values must reside strictly between 0.01 and 0.99.",
                    "code": "INVALID_REFUND_RATIO_RANGE"
                })

            dispute.status = DisputeStatus.RESOLVED
            dispute.resolution = ResolutionType.PARTIAL_REFUND

            refund_to_sender = (total_held * refund_ratio).quantize(decimal.Decimal("0.01"))
            payout_to_traveler = total_held - refund_to_sender

            BookingPaymentService.partial_refund(
                payment=payment, 
                refund_to_sender=refund_to_sender, 
                payout_to_traveler=payout_to_traveler
            )
            
            if hasattr(WalletService, "split_partial_escrow"):
                WalletService.split_partial_escrow(
                    booking=booking, 
                    sender_amt=refund_to_sender, 
                    traveler_amt=payout_to_traveler
                )
            else:
                logger.warning("WalletService has no partial refund method defined. Skipping wallet ledger update.")
            
            booking.payment_status = BookingPaymentStatusEnum.PARTIAL_REFUND
            booking.status = BookingStatus.COMPLETED
            booking.save(update_fields=["status", "payment_status"])

        elif resolution_type == ResolutionType.NO_ACTION:
            dispute.status = DisputeStatus.REJECTED
            dispute.resolution = ResolutionType.NO_ACTION
            
            booking.status = BookingStatus.COMPLETED
            booking.save(update_fields=["status"])

        else:
            raise ValidationError({
                "success": False,
                "message": "The selected resolution type is invalid.",
                "code": "INVALID_RESOLUTION_TYPE"
            })

        # Commit administrative attributes
        dispute.admin_notes = admin_notes
        dispute.resolved_by = admin_user
        dispute.resolved_at = timezone.now()
        dispute.last_updated_by = admin_user
        dispute.sender_notified = True
        dispute.traveler_notified = True
        
        dispute.save(update_fields=[
            "status",
            "resolution",
            "admin_notes",
            "resolved_by",
            "resolved_at",
            "last_updated_by",
            "sender_notified",
            "traveler_notified",
            "updated_at"
        ])

        history_action_map = {
            ResolutionType.FULL_REFUND: DisputeHistoryAction.RESOLVED_REFUND,
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

        logger.info(
            "Dispute %s resolved seamlessly",
            dispute.id,
            extra={
                "admin": str(admin_user.id),
                "booking": str(booking.id),
                "resolution": resolution_type,
                "refund_ratio": str(refund_ratio)
            }
        )

        transaction.on_commit(lambda: notify_dispute_resolution(dispute))

        return dispute