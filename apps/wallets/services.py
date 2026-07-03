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
        """
        Releases locked escrow funds directly to the traveler upon successful delivery verification.
        Moves funds: Sender's pending_balance -> Traveler's available_balance & total_earned
        """
        sender = booking.sender
        traveler = booking.traveler
        amount = Decimal(str(booking.agreed_reward))  # Cast safely to clean Decimal

        if not traveler:
            raise ValueError("Cannot release escrow. No traveler assigned to this booking.")
            
        if amount <= Decimal("0.00"):
            raise ValueError("Release amount must be positive.")

        with transaction.atomic():
            # Extract IDs to determine safe lock sequencing order
            sender_wallet_id = Wallet.objects.filter(user=sender).values_list('id', flat=True).first()
            traveler_wallet_id = Wallet.objects.filter(user=traveler).values_list('id', flat=True).first()
            
            # ✅ Guard against unprovisioned profiles to block TypeErrors
            if sender_wallet_id is None or traveler_wallet_id is None:
                raise ValueError("Sender or traveler wallet profile not found.")

            # Row-lock BOTH wallets in a deterministic sequence to avoid database deadlocks
            if sender_wallet_id < traveler_wallet_id:
                sender_wallet = Wallet.objects.select_for_update().get(user=sender)
                traveler_wallet = Wallet.objects.select_for_update().get(user=traveler)
            else:
                traveler_wallet = Wallet.objects.select_for_update().get(user=traveler)
                sender_wallet = Wallet.objects.select_for_update().get(user=sender)

            if sender_wallet.pending_balance < amount:
                raise ValueError(f"Sender wallet lacks corresponding pending escrow balance. Pending: ${sender_wallet.pending_balance}")

            # 1. Deduct from sender's pending vault
            sender_wallet.pending_balance -= amount
            sender_wallet.save(update_fields=["pending_balance", "updated_at"])

            # 2. Credit the traveler's liquid vault
            traveler_balance_before = traveler_wallet.available_balance
            traveler_wallet.available_balance += amount
            traveler_wallet.total_earned += amount
            traveler_wallet.save(update_fields=["available_balance", "total_earned", "updated_at"])

            # 3. Write immutable audit ledger record for the traveler
            tx = WalletTransaction.objects.create(
                wallet=traveler_wallet,
                booking=booking,
                type=WalletTransaction.TransactionType.ESCROW_RELEASE,
                amount=amount,
                status=WalletTransaction.TransactionStatus.COMPLETED,
                balance_before=traveler_balance_before,
                balance_after=traveler_wallet.available_balance,
                description=f"Escrow payout received for completing Delivery #{booking.tracking_number}",
                reference=f"REL-{booking.id}"
            )

            logger.info(f"Escrow payout of ${amount} securely settled to traveler {traveler.id}")
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