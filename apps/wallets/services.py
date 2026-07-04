import logging
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from .models import Wallet, WalletTransaction, WithdrawalRequest

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