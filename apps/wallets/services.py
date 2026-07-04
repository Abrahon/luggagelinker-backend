import logging
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from .models import Wallet, WalletTransaction, WithdrawalRequest
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from apps.wallets.models import Wallet, WithdrawalRequest, WalletTransaction
logger = logging.getLogger(__name__)





class WalletService:
    
    @classmethod
    def hold_escrow(cls, user, booking, amount: Decimal, reference: str = "") -> WalletTransaction:
        """
        Locks up user funds into pending escrow when a booking is created/confirmed.
        Moves funds: available_balance -> pending_balance
        """
        if amount <= Decimal("0.00"):
            raise ValueError("Escrow amount must be positive.")

        with transaction.atomic():
            try:
                wallet = Wallet.objects.select_for_update().get(user=user)
            except Wallet.DoesNotExist:
                raise ValueError("Wallet not found.")
            
            if wallet.available_balance < amount:
                raise ValueError(f"Insufficient funds to hold escrow. Available: ${wallet.available_balance}")

            balance_before = wallet.available_balance
            
            # Adjust balances
            wallet.available_balance -= amount
            wallet.pending_balance += amount
            wallet.save(update_fields=["available_balance", "pending_balance", "updated_at"])

            # Log audit trail record
            tx = WalletTransaction.objects.create(
                wallet=wallet,
                booking=booking,
                type=WalletTransaction.TransactionType.ESCROW_HOLD,
                amount=amount,
                status=WalletTransaction.TransactionStatus.COMPLETED,
                balance_before=balance_before,
                balance_after=wallet.available_balance,
                description=f"Escrow lock applied for Booking #{booking.tracking_number}",
                reference=reference or f"HOLD-{booking.id}"
            )
            
            logger.info(f"Escrow hold of ${amount} applied successfully on wallet {wallet.id}")
            return tx

    @classmethod
    def release_escrow_to_traveler(cls, booking) -> WalletTransaction:

        sender = booking.sender
        traveler = booking.traveler
        amount = Decimal(str(booking.agreed_reward))

        if not traveler:
            raise ValueError("No traveler assigned.")

        if amount <= Decimal("0.00"):
            raise ValueError("Invalid amount.")

        with transaction.atomic():

            sender_wallet = Wallet.objects.select_for_update().get(user=sender)
            traveler_wallet = Wallet.objects.select_for_update().get(user=traveler)

            # 🔒 Prevent double release
            if WalletTransaction.objects.filter(
                booking=booking,
                type=WalletTransaction.TransactionType.ESCROW_RELEASE,
                status=WalletTransaction.TransactionStatus.COMPLETED
            ).exists():
                raise ValueError("Escrow already released.")

            # 🔍 Validate escrow exists
            escrow = WalletTransaction.objects.filter(
                wallet=sender_wallet,
                booking=booking,
                type=WalletTransaction.TransactionType.ESCROW_HOLD,
                status=WalletTransaction.TransactionStatus.PENDING
            ).first()

            if not escrow:
                raise ValueError("No active escrow found.")

            if sender_wallet.pending_balance < amount:
                raise ValueError("Insufficient escrow balance.")

            # 💰 Sender deduction
            sender_before = sender_wallet.pending_balance
            sender_wallet.pending_balance -= amount
            sender_wallet.save(update_fields=["pending_balance"])

            # 💰 Traveler credit
            traveler_before = traveler_wallet.available_balance
            traveler_wallet.available_balance += amount
            traveler_wallet.total_earned += amount
            traveler_wallet.save(update_fields=["available_balance", "total_earned"])

            # 📊 Ledger sender
            WalletTransaction.objects.create(
                wallet=sender_wallet,
                booking=booking,
                type=WalletTransaction.TransactionType.ESCROW_RELEASE,
                amount=-amount,
                status=WalletTransaction.TransactionStatus.COMPLETED,
                balance_before=sender_before,
                balance_after=sender_wallet.pending_balance,
            )

            # 📊 Ledger traveler
            tx = WalletTransaction.objects.create(
                wallet=traveler_wallet,
                booking=booking,
                type=WalletTransaction.TransactionType.ESCROW_RELEASE,
                amount=amount,
                status=WalletTransaction.TransactionStatus.COMPLETED,
                balance_before=traveler_before,
                balance_after=traveler_wallet.available_balance,
            )

            return tx
        

    @classmethod
    def request_withdrawal(cls, user, amount: Decimal, bank_account_info: dict) -> WithdrawalRequest:
        """
        Initiates a liquid payout pipeline.
        Deducts from available balance immediately to prevent double-spending while review is pending.
        """
        # ✅ Decimal type strict evaluation
        if amount <= Decimal("0.00"):
            raise ValueError("Withdrawal amount must be positive.")

        with transaction.atomic():
            try:
                wallet = Wallet.objects.select_for_update().get(user=user)
            except Wallet.DoesNotExist:
                raise ValueError("Wallet not found.")

            # ✅ Prevent duplicate pending withdrawal spamming exploits
            if WithdrawalRequest.objects.filter(
                wallet=wallet,
                status=WithdrawalRequest.WithdrawalStatus.PENDING
            ).exists():
                raise ValueError("You already have an active pending withdrawal request processing.")

            if wallet.available_balance < amount:
                raise ValueError(f"Insufficient funds for withdrawal request. Available: ${wallet.available_balance}")

            balance_before = wallet.available_balance

            # Freeze the balance immediately
            wallet.available_balance -= amount
            wallet.save(update_fields=["available_balance", "updated_at"])

            # Create internal system payout tracking request
            withdrawal = WithdrawalRequest.objects.create(
                wallet=wallet,
                amount=amount,
                status=WithdrawalRequest.WithdrawalStatus.PENDING,
                bank_account_info=bank_account_info
            )

            # Record systemic audit transaction entry
            WalletTransaction.objects.create(
                wallet=wallet,
                type=WalletTransaction.TransactionType.WITHDRAWAL,
                amount=amount,
                status=WalletTransaction.TransactionStatus.PENDING,
                balance_before=balance_before,
                balance_after=wallet.available_balance,
                description=f"Withdrawal request initialized (ID: {withdrawal.id})",
                reference=f"WTH-{withdrawal.id}"
            )

            logger.info(f"Withdrawal request {withdrawal.id} filed for user {user.id}")
            return withdrawal



    @classmethod
    @transaction.atomic
    def hold_escrow(cls, booking) -> WalletTransaction:
        """
        Locks funds from the Sender's liquid available balance and places it 
        into their pending hold block when an order is funded.
        """
        sender = booking.sender
        amount = Decimal(str(booking.agreed_reward))

        if amount <= Decimal("0.00"):
            raise ValidationError("Escrow allocation reward must be a positive value.")

        # Row-level lock on the sender's vault wallet
        wallet = Wallet.objects.select_for_update().get(user=sender)

        if wallet.available_balance < amount:
            raise ValidationError(
                f"Insufficient available liquidity. Required: ${amount}, Available: ${wallet.available_balance}"
            )

        # Mutate account distributions
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

        sender_wallet = Wallet.objects.select_for_update().get(user=sender)
        traveler_wallet = Wallet.objects.select_for_update().get(user=traveler)

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
        traveler_wallet.total_earned += amount
        traveler_wallet.save(update_fields=["available_balance", "total_earned"])

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

        if wallet.available_balance < amount:
            raise ValidationError(f"Insufficient funds available. Cashout requests cannot exceed ${wallet.available_balance}")

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


# admin service class for handling withdrawal approvals, rejections, and marking as paid

class AdminWithdrawalService:

    @classmethod
    @transaction.atomic

    def approve_withdrawal(cls, withdrawal_id: str, admin_user) -> WithdrawalRequest:
        try:
            withdrawal = WithdrawalRequest.objects.select_for_update().get(id=withdrawal_id)
        except WithdrawalRequest.DoesNotExist:
            raise ValidationError("Withdrawal request not found.")

        if withdrawal.status != "PENDING":
            raise ValidationError(f"Cannot approve a withdrawal that is already {withdrawal.status}.")

        wallet = Wallet.objects.select_for_update().get(id=withdrawal.wallet_id)
        amount = Decimal(str(withdrawal.amount))

        wallet.total_withdrawn += amount
        wallet.save(update_fields=["total_withdrawn"])

        withdrawal.status = "APPROVED"
        withdrawal.save(update_fields=["status"])

        # 🟢 FIXED: Removed the invalid withdrawal_request column assignment
        WalletTransaction.objects.create(
            wallet=wallet,
            type="WITHDRAWAL",  
            amount=-amount,     
            status="COMPLETED",
            balance_before=wallet.available_balance,
            balance_after=wallet.available_balance,
            description=f"Withdrawal Request ID: {withdrawal.id} successfully approved by admin."
        )

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

        # 🟢 FIXED: Removed the invalid withdrawal_request column assignment
        WalletTransaction.objects.create(
            wallet=wallet,
            type="WITHDRAWAL_REFUND", 
            amount=amount,            
            status="COMPLETED",
            balance_before=balance_before,
            balance_after=wallet.available_balance,
            description=f"Refund: Withdrawal Request ID {withdrawal.id} was rejected. Reason: {rejection_reason}"
        )

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

        # 🟢 FIXED: Removed paid_at reference to align completely with your model schema fields
        withdrawal.status = "PAID"
        withdrawal.save(update_fields=["status"])

        logger.info(f"Admin {admin_user.email} marked withdrawal {withdrawal.id} as physically paid.")
        return withdrawal



