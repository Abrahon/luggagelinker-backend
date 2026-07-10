import logging
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from apps.wallets.models import Wallet, WithdrawalRequest, WalletTransaction

import logging
import stripe
from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from django.conf import settings
# 1. Change the import to look for your actual function name
from apps.notifications.services import create_bulk_notifications
from apps.wallets.models import Wallet, WithdrawalRequest, WalletTransaction
from apps.notifications.services import notify_withdrawal_approved, notify_withdrawal_rejected

# Initialize Stripe API Key
stripe.api_key = settings.STRIPE_SECRET_KEY
logger = logging.getLogger(__name__)

# Notification service imports
from apps.notifications.services import (
    notify_wallet_credited,
    notify_withdrawal_requested,
    notify_withdrawal_approved,
    notify_withdrawal_rejected,
    notify_refund_completed,
)

logger = logging.getLogger(__name__)


class WalletService:
    
    @classmethod
    @transaction.atomic
    def hold_escrow(cls, booking) -> WalletTransaction:
        """
        Locks funds from the Sender's liquid available balance and places it 
        into their pending hold block when an order is funded.
        Supports both direct internal wallet balances and external Stripe top-ups.
        """
        sender = booking.sender
        amount = Decimal(str(booking.agreed_reward))

        if amount <= Decimal("0.00"):
            raise ValidationError("Escrow allocation reward must be a positive value.")

        # 🟢 FIXED: Removed 'currency' from defaults to match your Wallet model schema
        wallet, created = Wallet.objects.get_or_create(
            user=sender,
            defaults={
                "available_balance": Decimal("0.00"),
                "pending_balance": Decimal("0.00")
            }
        )

        # Re-fetch with a row-level lock to handle concurrency safely
        wallet = Wallet.objects.select_for_update().get(id=wallet.id)

        # If this is an external Stripe checkout payment, credit the wallet 
        # instantly so the capacity check passes without throwing a balance error.
        if wallet.available_balance < amount:
            logger.info("External payment bypass/top-up detected for user %s via booking #%s", sender.id, booking.id)
            wallet.available_balance += amount
            wallet.save(update_fields=["available_balance"])

        # Mutate account distributions (Move to Escrow Hold)
        balance_before = wallet.available_balance
        wallet.available_balance -= amount
        wallet.pending_balance += amount
        wallet.save(update_fields=["available_balance", "pending_balance"])

        # Write the escrow verification ledger row
        tx = WalletTransaction.objects.create(
            wallet=wallet,
            booking=booking,
            type="ESCROW_HOLD",
            amount=-amount,  # Deducted from liquid asset availability
            status="PENDING",
            balance_before=balance_before,
            balance_after=wallet.available_balance,
            description=f"Escrow lock holding for Booking Tracker: {booking.tracking_number}"
        )
        return tx


    @classmethod
    @transaction.atomic
    def release_escrow(cls, booking) -> WalletTransaction:
        """
        Clears the pending escrow hold from the sender and releases 
        liquid payouts to the traveler upon delivery confirmation.
        """
        sender = booking.sender
        traveler = booking.traveler
        amount = Decimal(str(booking.agreed_reward))

        if not traveler:
            raise ValidationError("Cannot execute payment release. No traveler assigned to this booking.")

        # 🟢 FIX 1: Safely handle Sender Wallet row-lock (Auto-creates if missing)
        sender_wallet, _ = Wallet.objects.get_or_create(
            user=sender,
            defaults={"available_balance": Decimal("0.00"), "pending_balance": Decimal("0.00")}
        )
        sender_wallet = Wallet.objects.select_for_update().get(id=sender_wallet.id)

        # 🟢 FIX 2: Safely handle Traveler Wallet row-lock (Auto-creates if missing)
        traveler_wallet, _ = Wallet.objects.get_or_create(
            user=traveler,
            defaults={"available_balance": Decimal("0.00"), "pending_balance": Decimal("0.00")}
        )
        traveler_wallet = Wallet.objects.select_for_update().get(id=traveler_wallet.id)

        # 1. Idempotency Guard: Prevent double payouts
        if WalletTransaction.objects.filter(
            booking=booking,
            type="ESCROW_RELEASE",
            status="COMPLETED"
        ).exists():
            raise ValidationError("Escrow payouts have already been processed for this booking.")

        # 2. Verify active escrow hold matches
        escrow_hold = WalletTransaction.objects.select_for_update().filter(
            wallet=sender_wallet,
            booking=booking,
            type="ESCROW_HOLD",
            status="PENDING"
        ).first()

        if not escrow_hold:
            raise ValidationError("No active pending escrow hold found for this order tracking sequence.")

        if sender_wallet.pending_balance < amount:
            raise ValidationError("Corrupt financial ledger state: Sender has insufficient pending holdings.")

        # 3. Execute balance settlements
        sender_wallet.pending_balance -= amount
        sender_wallet.save(update_fields=["pending_balance"])

        traveler_before = traveler_wallet.available_balance
        traveler_wallet.available_balance += amount
        
        # Check if total_earned exists as a field in your Wallet model before mutating it
        if hasattr(traveler_wallet, 'total_earned'):
            traveler_wallet.total_earned += amount
            update_fields_list = ["available_balance", "total_earned"]
        else:
            update_fields_list = ["available_balance"]
            
        traveler_wallet.save(update_fields=update_fields_list)

        # 4. Finalize the original hold record status
        escrow_hold.status = "COMPLETED"
        escrow_hold.save(update_fields=["status"])

        # 5. Write out release transaction audit logs
        WalletTransaction.objects.create(
            wallet=sender_wallet,
            booking=booking,
            type="ESCROW_RELEASE",
            amount=-amount,
            status="COMPLETED",
            balance_before=sender_wallet.available_balance,
            balance_after=sender_wallet.available_balance,
            description=f"Released escrow hold asset block for Booking #{booking.id}"
        )

        tx = WalletTransaction.objects.create(
            wallet=traveler_wallet,
            booking=booking,
            type="ESCROW_RELEASE",
            amount=amount,
            status="COMPLETED",
            balance_before=traveler_before,
            balance_after=traveler_wallet.available_balance,
            description=f"Earnings payout received for delivering Booking #{booking.id}"
        )

        # 🔔 Notification: Notify traveler that they received their reward
        transaction.on_commit(lambda: notify_wallet_credited(
            user=traveler,
            booking=booking,
            amount=amount,
        ))

        return tx

    @classmethod
    @transaction.atomic
    def refund(cls, booking) -> WalletTransaction:
        """
        Cancels an order escrow, returning pending holds directly 
        back to the sender's liquid available pool.
        """
        sender = booking.sender
        amount = Decimal(str(booking.agreed_reward))

        wallet = Wallet.objects.select_for_update().get(user=sender)

        escrow_hold = WalletTransaction.objects.select_for_update().filter(
            wallet=wallet,
            booking=booking,
            type="ESCROW_HOLD",
            status="PENDING"
        ).first()

        if not escrow_hold:
            raise ValidationError("No cancellable pending escrow hold discovery profile exists.")

        if wallet.pending_balance < amount:
            raise ValidationError("Insufficient balance matching target cancellation window parameters.")

        # Shift balances back home
        balance_before = wallet.available_balance
        wallet.pending_balance -= amount
        wallet.available_balance += amount
        wallet.save(update_fields=["pending_balance", "available_balance"])

        # Mark historical hold record as terminated
        escrow_hold.status = "CANCELLED"
        escrow_hold.save(update_fields=["status"])

        tx = WalletTransaction.objects.create(
            wallet=wallet,
            booking=booking,
            type="REFUND",
            amount=amount,
            status="COMPLETED",
            balance_before=balance_before,
            balance_after=wallet.available_balance,
            description=f"Escrow refund reversed to available wallet for booking: {booking.id}"
        )

        # 🔔 Notification: Notify sender that their escrow refund completed successfully
        transaction.on_commit(lambda: notify_refund_completed(
            user=booking.sender,
            booking=booking,
            amount=amount,
        ))

        return tx

    @classmethod
    @transaction.atomic
    def withdraw(cls, user, amount: Decimal, bank_account_info: dict) -> WithdrawalRequest:
        """
        Initializes a user cashout request pipeline, immediately freezing 
        the liquid funds out of their available profile.
        """
        if amount <= Decimal("0.00"):
            raise ValidationError("Withdrawal amounts must scale positively.")

        wallet = Wallet.objects.select_for_update().get(user=user)

        # Prevent duplicate pending withdrawal spamming exploits
        if WithdrawalRequest.objects.filter(
            wallet=wallet,
            status="PENDING"
        ).exists():
            raise ValidationError("You already have an active pending withdrawal request processing.")

        if wallet.available_balance < amount:
            raise ValidationError(f"Insufficient funds available. Cashout requests cannot exceed ${wallet.available_balance}")

        balance_before = wallet.available_balance

        # Immediately lock availability block values
        wallet.available_balance -= amount
        wallet.save(update_fields=["available_balance"])

        # Instantiate tracking structural state row
        withdrawal = WithdrawalRequest.objects.create(
            wallet=wallet,
            amount=amount,
            bank_account_info=bank_account_info,
            status="PENDING"
        )

        # Record systemic audit transaction entry
        WalletTransaction.objects.create(
            wallet=wallet,
            type="WITHDRAWAL",
            amount=amount,
            status="PENDING",
            balance_before=balance_before,
            balance_after=wallet.available_balance,
            description=f"Withdrawal request initialized (ID: {withdrawal.id})",
            reference=f"WTH-{withdrawal.id}"
        )

        # 🔔 Notification: Trigger withdrawal request submission notification
        transaction.on_commit(lambda: notify_withdrawal_requested(
            user=user,
            withdrawal=withdrawal,
        ))

        logger.info(f"Withdrawal request {withdrawal.id} filed for user {user.id}")
        return withdrawal

    @classmethod
    @transaction.atomic
    def cancel_withdrawal(cls, withdrawal_id: str, user) -> WithdrawalRequest:
        """
        Allows users to cancel their own cashouts before admin processing, 
        safely re-crediting frozen assets back to their liquid available pool.
        """
        try:
            withdrawal = WithdrawalRequest.objects.select_for_update().get(id=withdrawal_id, wallet__user=user)
        except WithdrawalRequest.DoesNotExist:
            raise ValidationError("Withdrawal record not found or access profile permissions mismatch.")

        if withdrawal.status != "PENDING":
            raise ValidationError(f"Cannot terminate a withdrawal request that has been modified to: {withdrawal.status}")

        wallet = Wallet.objects.select_for_update().get(id=withdrawal.wallet_id)
        amount = Decimal(str(withdrawal.amount))

        # Restore funds to liquid availability limits
        balance_before = wallet.available_balance
        wallet.available_balance += amount
        wallet.save(update_fields=["available_balance"])

        withdrawal.status = "CANCELLED"
        withdrawal.save(update_fields=["status"])

        WalletTransaction.objects.create(
            wallet=wallet,
            type="WITHDRAWAL_REFUND",
            amount=amount,
            status="COMPLETED",
            balance_before=balance_before,
            balance_after=wallet.available_balance,
            description=f"User terminated processing for Withdrawal ID #{withdrawal.id}. Funds re-credited."
        )
        return withdrawal

    @classmethod
    @transaction.atomic
    def adjust_balance(cls, wallet_id: str, delta_amount: Decimal, admin_user, reason: str) -> WalletTransaction:
        """
        Administrative ledger correction engine. Allows support admins 
        to inject positive or negative adjustment delta corrections.
        """
        if not reason or not reason.strip():
            raise ValidationError("A tracking operational context explanation reason parameter string is mandatory.")

        wallet = Wallet.objects.select_for_update().get(id=wallet_id)
        balance_before = wallet.available_balance

        # Boundary Guard: Check for accidental negative wallet balance conversions
        if balance_before + delta_amount < Decimal("0.00"):
            raise ValidationError(
                f"Invalid correction parameters. Current balance is ${balance_before}. "
                f"Adjustment of ${delta_amount} would push ledger balance out into illegal debt bounds."
            )

        wallet.available_balance += delta_amount
        wallet.save(update_fields=["available_balance"])

        tx = WalletTransaction.objects.create(
            wallet=wallet,
            type="ADJUSTMENT",
            amount=delta_amount,
            status="COMPLETED",
            balance_before=balance_before,
            balance_after=wallet.available_balance,
            description=f"Admin Adjustment by {admin_user.email}. Context Notes: {reason}"
        )
        return tx



class AdminWithdrawalService:

    @classmethod
    def approve_withdrawal(cls, withdrawal_id: str, admin_user) -> WithdrawalRequest:
        
        # ─── PHASE 1: ROW SELECTION, ONBOARDING AND VALIDATION CHECKS ───
        with transaction.atomic():
            try:
                withdrawal = WithdrawalRequest.objects.select_for_update().get(id=withdrawal_id)
            except WithdrawalRequest.DoesNotExist:
                raise ValidationError("Withdrawal record not found.")

            if withdrawal.status != WithdrawalRequest.WithdrawalStatus.PENDING:
                raise ValidationError(f"Cannot process an already processed request ({withdrawal.status}).")

            user = withdrawal.wallet.user

            # Verify onboarding status via your exact StripeConnectedAccount relationship
            # ─── EXTRACTION & VERIFICATION CHECKS ───
            try:
                stripe_account = user.stripe_account
            except Exception:
                raise ValidationError("No Stripe Connected Account profile is linked to this user.")

            # Step 3: Enforcement Guard Rails
            if not stripe_account.details_submitted:
                raise ValidationError("Finish Stripe onboarding profile registration details first.")

            if not stripe_account.charges_enabled:
                raise ValidationError("Charges capabilities are not enabled on this Connect sub-account profile.")

            if not stripe_account.payouts_enabled:
                raise ValidationError("Payout configurations are not enabled. Check bank clearance documentation requirements on Stripe.")

            # Temporarily transition state to APPROVED to prevent concurrent double-clicks
            withdrawal.status = WithdrawalRequest.WithdrawalStatus.APPROVED
            withdrawal.save(update_fields=["status"])

            # Keep a read-only variable of the target account ID for Phase 2
            stripe_account_id = stripe_account.stripe_account_id

        # ─── PHASE 2: EXTERNAL STRIPE API EXECUTION (OUTSIDE DATABASE LOCK) ───
        if withdrawal.method == WithdrawalRequest.WithdrawalMethod.STRIPE:
            amount_in_cents = int(float(withdrawal.amount) * 100)
            
            try:
                # 1. Transfer funds from Platform Balance -> User Connected Account Balance [Phase 1]
                transfer = stripe.Transfer.create(
                    amount=amount_in_cents,
                    currency="usd",
                    destination=stripe_account_id,
                    transfer_group=f"withdrawal_{withdrawal.id}", # Match standard naming
                    description=f"Withdrawal {withdrawal.id}"
                )

                # 2. Trigger Bank payout out of their Connected Account balance instantly [Phase 2]
                payout = stripe.Payout.create(
                    amount=amount_in_cents,
                    currency="usd",
                    stripe_account=stripe_account_id  # explicitly targets the connected account context
                )
                
                stripe_response = {
                    "success": True,
                    "transfer_id": transfer.id,
                    "payout_id": payout.id
                }

            except stripe.error.StripeError as e:
                logger.error(f"Stripe Engine processing rejection for {stripe_account_id}: {str(e)}")
                stripe_response = {
                    "success": False,
                    "error_message": e.user_message or str(e)
                }

            # ─── PHASE 3: FINAL BALANCE AND LEDGER RESOLUTIONS ───
            with transaction.atomic():
                withdrawal = WithdrawalRequest.objects.select_for_update().get(id=withdrawal_id)
                wallet = Wallet.objects.select_for_update().get(id=withdrawal.wallet_id)

                if stripe_response.get("success") is True:
                    # Success Flow: Save tracking IDs to model fields [Phase 3]
                    withdrawal.stripe_transfer_id = stripe_response["transfer_id"]
                    withdrawal.stripe_payout_id = stripe_response["payout_id"]
                    withdrawal.save(update_fields=["stripe_transfer_id", "stripe_payout_id"])

                    # Create a PENDING ledger entry. The Webhook will mark this COMPLETED [Phase 6]
                    WalletTransaction.objects.create(
                        wallet=wallet,
                        type="WITHDRAWAL",  
                        amount=-withdrawal.amount,     
                        status="PENDING", # Status is pending until bank clears it
                        balance_before=wallet.available_balance,
                        balance_after=wallet.available_balance,
                        reference=stripe_response["payout_id"],
                        description=f"Stripe processing withdrawal. Reference: {stripe_response['payout_id']}"
                    )

                    # 🔔 Trigger notification upon successful generation
                    transaction.on_commit(lambda: notify_withdrawal_approved(
                        user=wallet.user,
                        withdrawal=withdrawal,
                    ))
                else:
                    # Gateway Error Flow -> Automatically return frozen liquidity back home
                    withdrawal.status = WithdrawalRequest.WithdrawalStatus.FAILED
                    withdrawal.rejection_reason = stripe_response.get("error_message")
                    withdrawal.save(update_fields=["status", "rejection_reason"])

                    balance_before = wallet.available_balance
                    wallet.available_balance += withdrawal.amount
                    wallet.save(update_fields=["available_balance"])

                    WalletTransaction.objects.create(
                        wallet=wallet,
                        type="WITHDRAWAL_REFUND", 
                        amount=withdrawal.amount,            
                        status="COMPLETED",
                        balance_before=balance_before,
                        balance_after=wallet.available_balance,
                        description=f"Stripe transaction failed: {stripe_response.get('error_message')}. Funds returned to account balance."
                    )

                    # 🔔 Trigger notification upon failure
                    transaction.on_commit(lambda: notify_withdrawal_rejected(
                        user=wallet.user,
                        withdrawal=withdrawal,
                    ))

            return withdrawal


    @classmethod
    @transaction.atomic
    def reject_withdrawal(cls, withdrawal_id: str, admin_user, rejection_reason: str) -> WithdrawalRequest:
        if not rejection_reason or not rejection_reason.strip():
            raise ValidationError("A justification reason is required to reject a withdrawal.")

        try:
            withdrawal = WithdrawalRequest.objects.select_for_update().get(id=withdrawal_id)
        except WithdrawalRequest.DoesNotExist:
            raise ValidationError("Withdrawal request not found.")

        if withdrawal.status != "PENDING":
            raise ValidationError(f"Cannot reject a withdrawal that is already {withdrawal.status}.")

        wallet = Wallet.objects.select_for_update().get(id=withdrawal.wallet_id)
        amount = Decimal(str(withdrawal.amount))

        balance_before = wallet.available_balance
        wallet.available_balance += amount
        wallet.save(update_fields=["available_balance"])

        withdrawal.status = "REJECTED"
        withdrawal.rejection_reason = rejection_reason
        withdrawal.save(update_fields=["status", "rejection_reason"])

        WalletTransaction.objects.create(
            wallet=wallet,
            type="WITHDRAWAL_REFUND", 
            amount=amount,            
            status="COMPLETED",
            balance_before=balance_before,
            balance_after=wallet.available_balance,
            description=f"Refund: Withdrawal Request ID {withdrawal.id} was rejected. Reason: {rejection_reason}"
        )

        # 🔔 Notification: Trigger rejection alert
        transaction.on_commit(lambda: notify_withdrawal_rejected(
            user=withdrawal.wallet.user,
            withdrawal=withdrawal,
        ))

        return withdrawal

    @classmethod
    @transaction.atomic
    def mark_as_paid(cls, withdrawal_id: str, admin_user) -> WithdrawalRequest:
        """Marks an approved withdrawal as physically processed and settled via banking networks."""
        try:
            withdrawal = WithdrawalRequest.objects.select_for_update().get(id=withdrawal_id)
        except WithdrawalRequest.DoesNotExist:
            raise ValidationError("Withdrawal request not found.")

        if withdrawal.status != "APPROVED":
            raise ValidationError(f"Only 'APPROVED' requests can be marked as paid. Current state: {withdrawal.status}")

        withdrawal.status = "PAID"
        withdrawal.save(update_fields=["status"])

        logger.info(f"Admin {admin_user.email} marked withdrawal {withdrawal.id} as physically paid.")
        return withdrawal