from datetime import datetime, timedelta
import logging
import stripe
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.conf import settings
import hashlib
import random
import secrets
from decimal import Decimal
import logging
from django.db import transaction
from django.core.exceptions import ValidationError

# Top-level Imports matching instructions 5 & 14
from apps.wallets.models import (
    Wallet, 
    WithdrawalRequest, 
    WalletTransaction, 
    WithdrawalMethod
)
from apps.notifications.services import (
    notify_wallet_credited,
    notify_withdrawal_requested,
    notify_withdrawal_approved,
    notify_withdrawal_rejected,
    notify_refund_completed,
)

# Initialize Stripe API Key
stripe.api_key = settings.STRIPE_SECRET_KEY
logger = logging.getLogger(__name__)


# class WalletService:
    
#     @classmethod
#     @transaction.atomic
#     def hold_escrow(cls, booking) -> WalletTransaction:
#         """
#         Locks funds from the Sender's liquid available balance and places it 
#         into their pending hold block when an order is funded.
#         Supports both direct internal wallet balances and external Stripe top-ups.
#         """
#         sender = booking.sender
#         amount = Decimal(str(booking.agreed_reward))

#         if amount <= Decimal("0.00"):
#             raise ValidationError("Escrow allocation reward must be a positive value.")

#         wallet, created = Wallet.objects.get_or_create(
#             user=sender,
#             defaults={
#                 "available_balance": Decimal("0.00"),
#                 "pending_balance": Decimal("0.00")
#             }
#         )

#         wallet = Wallet.objects.select_for_update().get(id=wallet.id)

#         if wallet.available_balance < amount:
#             logger.info("External payment bypass/top-up detected for user %s via booking #%s", sender.id, booking.id)
#             wallet.available_balance += amount
#             wallet.save(update_fields=["available_balance"])

#         balance_before = wallet.available_balance
#         wallet.available_balance -= amount
#         wallet.pending_balance += amount
#         wallet.save(update_fields=["available_balance", "pending_balance"])

#         tx = WalletTransaction.objects.create(
#             wallet=wallet,
#             booking=booking,
#             type=WalletTransaction.TransactionType.ESCROW_HOLD,
#             amount=-amount,  
#             status=WalletTransaction.TransactionStatus.PENDING,
#             balance_before=balance_before,
#             balance_after=wallet.available_balance,
#             description=f"Escrow lock holding for Booking Tracker: {booking.tracking_number}"
#         )
#         return tx

    
#     @classmethod
#     def get_escrow_status(cls, booking):
#         """
#         Returns the current escrow state for a booking.
#         """

#         if WalletTransaction.objects.filter(
#             booking=booking,
#             type=WalletTransaction.TransactionType.ESCROW_RELEASE,
#             wallet__user=booking.traveler,
#             status=WalletTransaction.TransactionStatus.COMPLETED,
#         ).exists():
#             return "RELEASED"

#         if WalletTransaction.objects.filter(
#             booking=booking,
#             type=WalletTransaction.TransactionType.REFUND,
#             status=WalletTransaction.TransactionStatus.COMPLETED,
#         ).exists():
#             return "REFUNDED"

#         if WalletTransaction.objects.filter(
#             booking=booking,
#             type=WalletTransaction.TransactionType.ESCROW_HOLD,
#             status=WalletTransaction.TransactionStatus.PENDING,
#         ).exists():
#             return "HELD"

#         return "NOT_FUNDED"
    

#     @classmethod
#     @transaction.atomic
#     def release_escrow(cls, booking) -> WalletTransaction:
#         """
#         Clears the pending escrow hold from the sender and releases 
#         liquid payouts to the traveler upon delivery confirmation.
#         """
#         sender = booking.sender
#         traveler = booking.traveler
#         amount = Decimal(str(booking.agreed_reward))

#         if not traveler:
#             raise ValidationError("Cannot execute payment release. No traveler assigned to this booking.")

#         sender_wallet, _ = Wallet.objects.get_or_create(
#             user=sender,
#             defaults={"available_balance": Decimal("0.00"), "pending_balance": Decimal("0.00")}
#         )
#         sender_wallet = Wallet.objects.select_for_update().get(id=sender_wallet.id)

#         traveler_wallet, _ = Wallet.objects.get_or_create(
#             user=traveler,
#             defaults={"available_balance": Decimal("0.00"), "pending_balance": Decimal("0.00")}
#         )
#         traveler_wallet = Wallet.objects.select_for_update().get(id=traveler_wallet.id)

#         if WalletTransaction.objects.filter(
#             booking=booking,
#             type=WalletTransaction.TransactionType.ESCROW_RELEASE,
#             status=WalletTransaction.TransactionStatus.COMPLETED,
#         ).exists():
#             raise ValidationError("Escrow payouts have already been processed for this booking.")

#         escrow_hold = WalletTransaction.objects.select_for_update().filter(
#             wallet=sender_wallet,
#             booking=booking,
#             type=WalletTransaction.TransactionType.ESCROW_HOLD,
#             status=WalletTransaction.TransactionStatus.PENDING,
#         ).first()

#         if not escrow_hold:
#             raise ValidationError("No active pending escrow hold found for this order tracking sequence.")

#         if sender_wallet.pending_balance < amount:
#             raise ValidationError("Corrupt financial ledger state: Sender has insufficient pending holdings.")

#         sender_wallet.pending_balance -= amount
#         sender_wallet.save(update_fields=["pending_balance"])

#         traveler_before = traveler_wallet.available_balance
#         traveler_wallet.available_balance += amount
        
#         if hasattr(traveler_wallet, 'total_earned'):
#             traveler_wallet.total_earned += amount
#             update_fields_list = ["available_balance", "total_earned"]
#         else:
#             update_fields_list = ["available_balance"]
            
#         traveler_wallet.save(update_fields=update_fields_list)

#         escrow_hold.status = "COMPLETED"
#         escrow_hold.save(update_fields=["status"])

#         WalletTransaction.objects.create(
#             wallet=sender_wallet,
#             booking=booking,
#             type=WalletTransaction.TransactionType.ESCROW_RELEASE,
#             amount=-amount,
#             status=WalletTransaction.TransactionStatus.COMPLETED,
#             balance_before=sender_wallet.available_balance,
#             balance_after=sender_wallet.available_balance,
#             description=f"Released escrow hold asset block for Booking #{booking.id}"
#         )

#         tx = WalletTransaction.objects.create(
#             wallet=traveler_wallet,
#             booking=booking,
#             type=WalletTransaction.TransactionType.ESCROW_RELEASE,
#             amount=amount,
#             status=WalletTransaction.TransactionStatus.COMPLETED,
#             balance_before=traveler_before,
#             balance_after=traveler_wallet.available_balance,
#             description=f"Earnings payout received for delivering Booking #{booking.id}"
#         )

#         transaction.on_commit(lambda: notify_wallet_credited(
#             user=traveler,
#             booking=booking,
#             amount=amount,
#         ))

#         return tx

    

#     @classmethod
#     @transaction.atomic
#     def refund(cls, booking) -> WalletTransaction:
#         """
#         Cancels an order escrow, returning pending holds directly 
#         back to the sender's liquid available pool.
#         """
#         sender = booking.sender
#         amount = Decimal(str(booking.agreed_reward))

#         wallet = Wallet.objects.select_for_update().get(user=sender)

#         escrow_hold = WalletTransaction.objects.select_for_update().filter(
#             wallet=wallet,
#             booking=booking,
#             type="ESCROW_HOLD",
#             status="PENDING"
#         ).first()

#         if not escrow_hold:
#             raise ValidationError("No cancellable pending escrow hold discovery profile exists.")

#         if wallet.pending_balance < amount:
#             raise ValidationError("Insufficient balance matching target cancellation window parameters.")

#         balance_before = wallet.available_balance
#         wallet.pending_balance -= amount
#         wallet.available_balance += amount
#         wallet.save(update_fields=["pending_balance", "available_balance"])

#         escrow_hold.status = "CANCELLED"
#         escrow_hold.save(update_fields=["status"])

#         tx = WalletTransaction.objects.create(
#             wallet=wallet,
#             booking=booking,
#             type="REFUND",
#             amount=amount,
#             status="COMPLETED",
#             balance_before=balance_before,
#             balance_after=wallet.available_balance,
#             description=f"Escrow refund reversed to available wallet for booking: {booking.id}"
#         )

#         transaction.on_commit(lambda: notify_refund_completed(
#             user=booking.sender,
#             booking=booking,
#             amount=amount,
#         ))

#         return tx

    

#     @classmethod
#     @transaction.atomic
#     def withdraw(
#         cls,
#         user,
#         amount: Decimal,
#         withdrawal_method,
#     ) -> WithdrawalRequest:
#         """
#         Initializes a user cashout request pipeline, immediately freezing 
#         the liquid funds out of their available profile.
#         """
#         if amount <= Decimal("0.00"):
#             raise ValidationError("Withdrawal amounts must scale positively.")

#         wallet = Wallet.objects.select_for_update().get(user=user)

#         if WithdrawalRequest.objects.filter(
#             wallet=wallet,
#             status=WithdrawalRequest.WithdrawalStatus.PENDING
#         ).exists():
#             raise ValidationError("You already have an active pending withdrawal request processing.")

#         if wallet.available_balance < amount:
#             raise ValidationError(f"Insufficient funds available. Cashout requests cannot exceed ${wallet.available_balance}")

#         balance_before = wallet.available_balance

#         wallet.available_balance -= amount
#         wallet.save(update_fields=["available_balance"])

#         # Create WithdrawalRequest using choices and target withdrawal_method configuration
#         withdrawal = WithdrawalRequest.objects.create(
#             wallet=wallet,
#             amount=amount,
#             status=WithdrawalRequest.WithdrawalStatus.PENDING,
#             withdrawal_method=withdrawal_method,
#         )

#         WalletTransaction.objects.create(
#             wallet=wallet,
#             type="WITHDRAWAL",
#             amount=amount,
#             status="PENDING",
#             balance_before=balance_before,
#             balance_after=wallet.available_balance,
#             description=f"Withdrawal request initialized (ID: {withdrawal.id})",
#             reference=f"WTH-{withdrawal.id}"
#         )

#         transaction.on_commit(lambda: notify_withdrawal_requested(
#             user=user,
#             withdrawal=withdrawal,
#         ))

#         logger.info(f"Withdrawal request {withdrawal.id} filed for user {user.id}")
#         return withdrawal

    

#     @classmethod
#     @transaction.atomic
#     def cancel_withdrawal(cls, withdrawal_id: str, user) -> WithdrawalRequest:
#         """
#         Allows users to cancel their own cashouts before admin processing, 
#         safely re-crediting frozen assets back to their liquid available pool.
#         """
#         try:
#             withdrawal = WithdrawalRequest.objects.select_for_update().get(id=withdrawal_id, wallet__user=user)
#         except WithdrawalRequest.DoesNotExist:
#             raise ValidationError("Withdrawal record not found or access profile permissions mismatch.")

#         if withdrawal.status != WithdrawalRequest.WithdrawalStatus.PENDING:
#             raise ValidationError(f"Cannot terminate a withdrawal request that has been modified to: {withdrawal.status}")

#         wallet = Wallet.objects.select_for_update().get(id=withdrawal.wallet_id)
#         amount = Decimal(str(withdrawal.amount))

#         balance_before = wallet.available_balance
#         wallet.available_balance += amount
#         wallet.save(update_fields=["available_balance"])

#         withdrawal.status = WithdrawalRequest.WithdrawalStatus.CANCELLED
#         withdrawal.save(update_fields=["status"])

#         # Map explicitly to dynamic WITHDRAWAL_CANCEL transaction tracking
#         WalletTransaction.objects.create(
#             wallet=wallet,
#             type="WITHDRAWAL_CANCEL",
#             amount=amount,
#             status="COMPLETED",
#             balance_before=balance_before,
#             balance_after=wallet.available_balance,
#             description=f"User terminated processing for Withdrawal ID #{withdrawal.id}. Funds re-credited."
#         )
#         return withdrawal
#     @staticmethod
#     def _calculate_luhn_check_digit(number_15_digits: str) -> str:
#         """Calculates the 16th check digit using the Luhn Algorithm."""
#         digits = [int(d) for d in number_15_digits]
#         for i in range(len(digits) - 1, -1, -2):
#             digits[i] *= 2
#             if digits[i] > 9:
#                 digits[i] -= 9
#         total_sum = sum(digits)
#         check_digit = (10 - (total_sum % 10)) % 10
#         return str(check_digit)

#     @classmethod
#     def generate_virtual_card_number(cls) -> str:
#         """
#         Generates a 16-digit Visa card number (BIN: 4829) passing the Luhn algorithm.
#         Uses cryptographically secure random digits instead of predictable user IDs.
#         """
#         # 4-digit BIN + 11 secure random digits = 15 digits
#         random_payload = "".join(str(secrets.randbelow(10)) for _ in range(11))
#         fifteen_digits = f"4829{random_payload}"
        
#         # Calculate 16th digit
#         check_digit = cls._calculate_luhn_check_digit(fifteen_digits)
#         return f"{fifteen_digits}{check_digit}"

#     @staticmethod
#     def generate_masked_card(card_number: str) -> str:
#         """Masks a given card number safely."""
#         if not card_number or len(card_number) < 16:
#             return "•••• •••• •••• ••••"
#         return f"{card_number[:4]} •••• •••• {card_number[-4:]}"

#     @staticmethod
#     def generate_virtual_cvv() -> str:
#         """Generates a secure 3-digit CVV (100–999)."""
#         return str(secrets.randbelow(900) + 100)

#     @staticmethod
#     def generate_expiry(years_valid: int = 3) -> str:
#         """Dynamically calculates expiry date relative to today."""
#         expiry_date = datetime.now() + timedelta(days=365 * years_valid)
#         return expiry_date.strftime("%m/%y")


#     @classmethod
#     @transaction.atomic
#     def adjust_balance(cls, wallet_id: str, delta_amount: Decimal, admin_user, reason: str) -> WalletTransaction:
#         """
#         Administrative ledger correction engine. Allows support admins 
#         to inject positive or negative adjustment delta corrections.
#         """
#         if not reason or not reason.strip():
#             raise ValidationError("A tracking operational context explanation reason parameter string is mandatory.")

#         wallet = Wallet.objects.select_for_update().get(id=wallet_id)
#         balance_before = wallet.available_balance

#         if balance_before + delta_amount < Decimal("0.00"):
#             raise ValidationError(
#                 f"Invalid correction parameters. Current balance is ${balance_before}. "
#                 f"Adjustment of ${delta_amount} would push ledger balance out into illegal debt bounds."
#             )

#         wallet.available_balance += delta_amount
#         wallet.save(update_fields=["available_balance"])

#         tx = WalletTransaction.objects.create(
#             wallet=wallet,
#             type="ADJUSTMENT",
#             amount=delta_amount,
#             status="COMPLETED",
#             balance_before=balance_before,
#             balance_after=wallet.available_balance,
#             description=f"Admin Adjustment by {admin_user.email}. Context Notes: {reason}"
#         )
#         return tx




#     @classmethod
#     @transaction.atomic
#     def split_partial_escrow(cls, booking, sender_amt, traveler_amt):
#         """
#         Splits held escrow funds between Sender (partial refund) and Traveler/Carrier (partial payout)
#         during dispute resolution.
#         """
#         sender_amt = Decimal(str(sender_amt or "0.00"))
#         traveler_amt = Decimal(str(traveler_amt or "0.00"))

#         if sender_amt < Decimal("0.00") or traveler_amt < Decimal("0.00"):
#             raise ValidationError("Split amounts must be non-negative.")

#         total_split = sender_amt + traveler_amt
#         if total_split <= Decimal("0.00"):
#             raise ValidationError("Total dispute settlement amount must be greater than zero.")

#         # 1. Fetch & lock Sender Wallet
#         sender = booking.sender
#         sender_wallet, _ = Wallet.objects.get_or_create(
#             user=sender,
#             defaults={"available_balance": Decimal("0.00"), "pending_balance": Decimal("0.00")}
#         )
#         sender_wallet = Wallet.objects.select_for_update().get(id=sender_wallet.id)

#         # ---------------------------------------------------------
#         # 2. PROCESS SENDER REFUND (DISPUTE_REFUND)
#         # ---------------------------------------------------------
#         if sender_amt > Decimal("0.00"):
#             sender_wallet.pending_balance -= sender_amt
#             sender_wallet.available_balance += sender_amt

#             WalletTransaction.objects.create(
#                 wallet=sender_wallet,
#                 booking=booking,
#                 type=WalletTransaction.TransactionType.DISPUTE_REFUND,  # 🟢 Clearly marked
#                 amount=sender_amt,
#                 status=WalletTransaction.TransactionStatus.COMPLETED,
#                 balance_before=sender_wallet.available_balance - sender_amt,
#                 balance_after=sender_wallet.available_balance,
#                 description=f"Dispute Partial Refund for Booking: {booking.tracking_number}"
#             )

#         # ---------------------------------------------------------
#         # 3. DEDUCT REMAINING ESCROW FROM SENDER
#         # ---------------------------------------------------------
#         if traveler_amt > Decimal("0.00"):
#             sender_wallet.pending_balance -= traveler_amt

#         sender_wallet.save(update_fields=["available_balance", "pending_balance"])

#         # ---------------------------------------------------------
#         # 4. PROCESS TRAVELER PAYOUT (DISPUTE_PAYOUT)
#         # ---------------------------------------------------------
#         if traveler_amt > Decimal("0.00"):
#             traveler = getattr(booking, "traveler", None) or getattr(booking, "carrier", None)
#             if not traveler:
#                 raise ValidationError("Cannot issue traveler payout: No traveler/carrier assigned to this booking.")

#             traveler_wallet, _ = Wallet.objects.get_or_create(
#                 user=traveler,
#                 defaults={"available_balance": Decimal("0.00"), "pending_balance": Decimal("0.00")}
#             )
#             traveler_wallet = Wallet.objects.select_for_update().get(id=traveler_wallet.id)

#             balance_before = traveler_wallet.available_balance
#             traveler_wallet.available_balance += traveler_amt
            
#             update_fields = ["available_balance"]
#             if hasattr(traveler_wallet, "total_earned"):
#                 traveler_wallet.total_earned += traveler_amt
#                 update_fields.append("total_earned")

#             traveler_wallet.save(update_fields=update_fields)

#             WalletTransaction.objects.create(
#                 wallet=traveler_wallet,
#                 booking=booking,
#                 type=WalletTransaction.TransactionType.DISPUTE_PAYOUT,  # 🟢 Clearly marked
#                 amount=traveler_amt,
#                 status=WalletTransaction.TransactionStatus.COMPLETED,
#                 balance_before=balance_before,
#                 balance_after=traveler_wallet.available_balance,
#                 description=f"Dispute Settlement Payout for Booking: {booking.tracking_number}"
#             )


from datetime import datetime, timedelta
import logging
import stripe
from decimal import Decimal
import secrets

from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.conf import settings

from apps.wallets.models import (
    Wallet, 
    WithdrawalRequest, 
    WalletTransaction, 
    WithdrawalMethod
)
from apps.notifications.services import (
    notify_wallet_credited,
    notify_withdrawal_requested,
    notify_withdrawal_approved,
    notify_withdrawal_rejected,
    notify_refund_completed,
)

stripe.api_key = settings.STRIPE_SECRET_KEY
logger = logging.getLogger(__name__)


class WalletService:

    @classmethod
    @transaction.atomic
    def hold_escrow(cls, booking) -> WalletTransaction:
        """
        Locks funds from the Sender's liquid available balance into pending escrow block.
        """
        sender = booking.sender
        amount = Decimal(str(booking.agreed_reward))

        if amount <= Decimal("0.00"):
            raise ValidationError("Escrow allocation reward must be a positive value.")

        wallet, _ = Wallet.objects.get_or_create(
            user=sender,
            defaults={"available_balance": Decimal("0.00"), "pending_balance": Decimal("0.00")}
        )
        wallet = Wallet.objects.select_for_update().get(id=wallet.id)

        if wallet.available_balance < amount:
            logger.info("External payment top-up detected for user %s via booking #%s", sender.id, booking.id)
            wallet.available_balance += amount
            wallet.save(update_fields=["available_balance"])

        balance_before = wallet.available_balance
        wallet.available_balance -= amount
        wallet.pending_balance += amount
        wallet.save(update_fields=["available_balance", "pending_balance"])

        tx = WalletTransaction.objects.create(
            wallet=wallet,
            booking=booking,
            type=WalletTransaction.TransactionType.ESCROW_HOLD,
            amount=-amount,  
            status=WalletTransaction.TransactionStatus.PENDING,
            balance_before=balance_before,
            balance_after=wallet.available_balance,
            description=f"Escrow lock holding for Booking: {booking.tracking_number}"
        )
        return tx

    @classmethod
    def get_escrow_status(cls, booking) -> str:
        """
        Returns the current internal escrow state for a booking.
        """
        if WalletTransaction.objects.filter(
            booking=booking,
            type=WalletTransaction.TransactionType.ESCROW_RELEASE,
            wallet__user=booking.traveler,
            status=WalletTransaction.TransactionStatus.COMPLETED,
        ).exists():
            return "RELEASED"

        if WalletTransaction.objects.filter(
            booking=booking,
            type=WalletTransaction.TransactionType.REFUND,
            status=WalletTransaction.TransactionStatus.COMPLETED,
        ).exists():
            return "REFUNDED"

        if WalletTransaction.objects.filter(
            booking=booking,
            type=WalletTransaction.TransactionType.ESCROW_HOLD,
            status=WalletTransaction.TransactionStatus.PENDING,
        ).exists():
            return "HELD"

        return "NOT_FUNDED"

    @classmethod
    @transaction.atomic
    def release_escrow(cls, booking) -> WalletTransaction:
        """
        Alias for releasing funds to traveler.
        """
        return cls.release_escrow_to_traveler(booking=booking)

    @classmethod
    @transaction.atomic
    def release_escrow_to_traveler(cls, booking, amount=None) -> WalletTransaction:
        """
        Clears pending escrow hold and credits liquid payout to the traveler.
        """
        sender = booking.sender
        traveler = getattr(booking, "traveler", None) or getattr(booking, "carrier", None)
        payout_amount = Decimal(str(amount if amount is not None else booking.agreed_reward))

        if not traveler:
            raise ValidationError("Cannot execute payment release. No traveler assigned to this booking.")

        sender_wallet, _ = Wallet.objects.get_or_create(
            user=sender,
            defaults={"available_balance": Decimal("0.00"), "pending_balance": Decimal("0.00")}
        )
        sender_wallet = Wallet.objects.select_for_update().get(id=sender_wallet.id)

        traveler_wallet, _ = Wallet.objects.get_or_create(
            user=traveler,
            defaults={"available_balance": Decimal("0.00"), "pending_balance": Decimal("0.00")}
        )
        traveler_wallet = Wallet.objects.select_for_update().get(id=traveler_wallet.id)

        escrow_hold = WalletTransaction.objects.select_for_update().filter(
            wallet=sender_wallet,
            booking=booking,
            type=WalletTransaction.TransactionType.ESCROW_HOLD,
            status=WalletTransaction.TransactionStatus.PENDING,
        ).first()

        if sender_wallet.pending_balance >= payout_amount:
            sender_wallet.pending_balance -= payout_amount
            sender_wallet.save(update_fields=["pending_balance"])

        traveler_before = traveler_wallet.available_balance
        traveler_wallet.available_balance += payout_amount
        
        update_fields_list = ["available_balance"]
        if hasattr(traveler_wallet, "total_earned"):
            traveler_wallet.total_earned += payout_amount
            update_fields_list.append("total_earned")
            
        traveler_wallet.save(update_fields=update_fields_list)

        if escrow_hold:
            escrow_hold.status = WalletTransaction.TransactionStatus.COMPLETED
            escrow_hold.save(update_fields=["status"])

        tx = WalletTransaction.objects.create(
            wallet=traveler_wallet,
            booking=booking,
            type=WalletTransaction.TransactionType.ESCROW_RELEASE,
            amount=payout_amount,
            status=WalletTransaction.TransactionStatus.COMPLETED,
            balance_before=traveler_before,
            balance_after=traveler_wallet.available_balance,
            description=f"Earnings payout received for delivering Booking #{booking.id}"
        )

        transaction.on_commit(lambda: notify_wallet_credited(
            user=traveler,
            booking=booking,
            amount=payout_amount,
        ))

        return tx

    @classmethod
    @transaction.atomic
    def refund(cls, booking) -> WalletTransaction:
        """
        Standard refund entry point for booking cancellation.
        """
        return cls.refund_escrow_to_sender(booking=booking)

    @classmethod
    @transaction.atomic
    def refund_escrow_to_sender(cls, booking, amount=None) -> WalletTransaction:
        """
        Unlocks escrow pending hold and returns funds back to sender's available pool.
        Called by both standard cancellations and AdminDisputeService.
        """
        sender = booking.sender
        refund_amount = Decimal(str(amount if amount is not None else booking.agreed_reward))

        wallet, _ = Wallet.objects.get_or_create(
            user=sender,
            defaults={"available_balance": Decimal("0.00"), "pending_balance": Decimal("0.00")}
        )
        wallet = Wallet.objects.select_for_update().get(id=wallet.id)

        escrow_hold = WalletTransaction.objects.select_for_update().filter(
            wallet=wallet,
            booking=booking,
            type=WalletTransaction.TransactionType.ESCROW_HOLD,
            status=WalletTransaction.TransactionStatus.PENDING
        ).first()

        if wallet.pending_balance >= refund_amount:
            wallet.pending_balance -= refund_amount
            wallet.available_balance += refund_amount
            wallet.save(update_fields=["pending_balance", "available_balance"])

        if escrow_hold:
            escrow_hold.status = WalletTransaction.TransactionStatus.CANCELLED
            escrow_hold.save(update_fields=["status"])

        tx = WalletTransaction.objects.create(
            wallet=wallet,
            booking=booking,
            type=WalletTransaction.TransactionType.REFUND,
            amount=refund_amount,
            status=WalletTransaction.TransactionStatus.COMPLETED,
            balance_before=wallet.available_balance - refund_amount,
            balance_after=wallet.available_balance,
            description=f"Escrow refund reversed to available wallet for booking: {booking.id}"
        )

        transaction.on_commit(lambda: notify_refund_completed(
            user=booking.sender,
            booking=booking,
            amount=refund_amount,
        ))

        return tx

    @classmethod
    @transaction.atomic
    def split_partial_escrow(cls, booking, sender_amt, traveler_amt):
        """
        Splits held escrow funds between Sender (partial refund) and Traveler (partial payout).
        """
        sender_amt = Decimal(str(sender_amt or "0.00"))
        traveler_amt = Decimal(str(traveler_amt or "0.00"))

        if sender_amt < Decimal("0.00") or traveler_amt < Decimal("0.00"):
            raise ValidationError("Split amounts must be non-negative.")

        total_split = sender_amt + traveler_amt
        if total_split <= Decimal("0.00"):
            raise ValidationError("Total dispute settlement amount must be greater than zero.")

        sender = booking.sender
        sender_wallet, _ = Wallet.objects.get_or_create(
            user=sender,
            defaults={"available_balance": Decimal("0.00"), "pending_balance": Decimal("0.00")}
        )
        sender_wallet = Wallet.objects.select_for_update().get(id=sender_wallet.id)

        if sender_amt > Decimal("0.00"):
            sender_wallet.pending_balance -= sender_amt
            sender_wallet.available_balance += sender_amt

            WalletTransaction.objects.create(
                wallet=sender_wallet,
                booking=booking,
                type=WalletTransaction.TransactionType.DISPUTE_REFUND,
                amount=sender_amt,
                status=WalletTransaction.TransactionStatus.COMPLETED,
                balance_before=sender_wallet.available_balance - sender_amt,
                balance_after=sender_wallet.available_balance,
                description=f"Dispute Partial Refund for Booking: {booking.tracking_number}"
            )

        if traveler_amt > Decimal("0.00"):
            sender_wallet.pending_balance -= traveler_amt

        sender_wallet.save(update_fields=["available_balance", "pending_balance"])

        if traveler_amt > Decimal("0.00"):
            traveler = getattr(booking, "traveler", None) or getattr(booking, "carrier", None)
            if not traveler:
                raise ValidationError("Cannot issue traveler payout: No traveler/carrier assigned to this booking.")

            traveler_wallet, _ = Wallet.objects.get_or_create(
                user=traveler,
                defaults={"available_balance": Decimal("0.00"), "pending_balance": Decimal("0.00")}
            )
            traveler_wallet = Wallet.objects.select_for_update().get(id=traveler_wallet.id)

            balance_before = traveler_wallet.available_balance
            traveler_wallet.available_balance += traveler_amt
            
            update_fields = ["available_balance"]
            if hasattr(traveler_wallet, "total_earned"):
                traveler_wallet.total_earned += traveler_amt
                update_fields.append("total_earned")

            traveler_wallet.save(update_fields=update_fields)

            WalletTransaction.objects.create(
                wallet=traveler_wallet,
                booking=booking,
                type=WalletTransaction.TransactionType.DISPUTE_PAYOUT,
                amount=traveler_amt,
                status=WalletTransaction.TransactionStatus.COMPLETED,
                balance_before=balance_before,
                balance_after=traveler_wallet.available_balance,
                description=f"Dispute Settlement Payout for Booking: {booking.tracking_number}"
            )

    @classmethod
    @transaction.atomic
    def withdraw(cls, user, amount: Decimal, withdrawal_method) -> WithdrawalRequest:
        if amount <= Decimal("0.00"):
            raise ValidationError("Withdrawal amounts must scale positively.")

        wallet = Wallet.objects.select_for_update().get(user=user)

        if WithdrawalRequest.objects.filter(
            wallet=wallet,
            status=WithdrawalRequest.WithdrawalStatus.PENDING
        ).exists():
            raise ValidationError("You already have an active pending withdrawal request processing.")

        if wallet.available_balance < amount:
            raise ValidationError(f"Insufficient funds available. Cashout requests cannot exceed ${wallet.available_balance}")

        balance_before = wallet.available_balance

        wallet.available_balance -= amount
        wallet.save(update_fields=["available_balance"])

        withdrawal = WithdrawalRequest.objects.create(
            wallet=wallet,
            amount=amount,
            status=WithdrawalRequest.WithdrawalStatus.PENDING,
            withdrawal_method=withdrawal_method,
        )

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

        transaction.on_commit(lambda: notify_withdrawal_requested(
            user=user,
            withdrawal=withdrawal,
        ))

        logger.info(f"Withdrawal request {withdrawal.id} filed for user {user.id}")
        return withdrawal

    @classmethod
    @transaction.atomic
    def cancel_withdrawal(cls, withdrawal_id: str, user) -> WithdrawalRequest:
        try:
            withdrawal = WithdrawalRequest.objects.select_for_update().get(id=withdrawal_id, wallet__user=user)
        except WithdrawalRequest.DoesNotExist:
            raise ValidationError("Withdrawal record not found or access profile permissions mismatch.")

        if withdrawal.status != WithdrawalRequest.WithdrawalStatus.PENDING:
            raise ValidationError(f"Cannot terminate a withdrawal request that has been modified to: {withdrawal.status}")

        wallet = Wallet.objects.select_for_update().get(id=withdrawal.wallet_id)
        amount = Decimal(str(withdrawal.amount))

        balance_before = wallet.available_balance
        wallet.available_balance += amount
        wallet.save(update_fields=["available_balance"])

        withdrawal.status = WithdrawalRequest.WithdrawalStatus.CANCELLED
        withdrawal.save(update_fields=["status"])

        WalletTransaction.objects.create(
            wallet=wallet,
            type=WalletTransaction.TransactionType.WITHDRAWAL_CANCEL,
            amount=amount,
            status=WalletTransaction.TransactionStatus.COMPLETED,
            balance_before=balance_before,
            balance_after=wallet.available_balance,
            description=f"User terminated processing for Withdrawal ID #{withdrawal.id}. Funds re-credited."
        )
        return withdrawal

    @staticmethod
    def _calculate_luhn_check_digit(number_15_digits: str) -> str:
        digits = [int(d) for d in number_15_digits]
        for i in range(len(digits) - 1, -1, -2):
            digits[i] *= 2
            if digits[i] > 9:
                digits[i] -= 9
        total_sum = sum(digits)
        check_digit = (10 - (total_sum % 10)) % 10
        return str(check_digit)

    @classmethod
    def generate_virtual_card_number(cls) -> str:
        random_payload = "".join(str(secrets.randbelow(10)) for _ in range(11))
        fifteen_digits = f"4829{random_payload}"
        check_digit = cls._calculate_luhn_check_digit(fifteen_digits)
        return f"{fifteen_digits}{check_digit}"

    @staticmethod
    def generate_masked_card(card_number: str) -> str:
        if not card_number or len(card_number) < 16:
            return "•••• •••• •••• ••••"
        return f"{card_number[:4]} •••• •••• {card_number[-4:]}"

    @staticmethod
    def generate_virtual_cvv() -> str:
        return str(secrets.randbelow(900) + 100)

    @staticmethod
    def generate_expiry(years_valid: int = 3) -> str:
        expiry_date = datetime.now() + timedelta(days=365 * years_valid)
        return expiry_date.strftime("%m/%y")

    @classmethod
    @transaction.atomic
    def adjust_balance(cls, wallet_id: str, delta_amount: Decimal, admin_user, reason: str) -> WalletTransaction:
        if not reason or not reason.strip():
            raise ValidationError("A tracking operational context explanation reason parameter string is mandatory.")

        wallet = Wallet.objects.select_for_update().get(id=wallet_id)
        balance_before = wallet.available_balance

        if balance_before + delta_amount < Decimal("0.00"):
            raise ValidationError(
                f"Invalid correction parameters. Current balance is ${balance_before}. "
                f"Adjustment of ${delta_amount} would push ledger balance out into illegal debt bounds."
            )

        wallet.available_balance += delta_amount
        wallet.save(update_fields=["available_balance"])

        tx = WalletTransaction.objects.create(
            wallet=wallet,
            type=WalletTransaction.TransactionType.ADJUSTMENT,
            amount=delta_amount,
            status=WalletTransaction.TransactionStatus.COMPLETED,
            balance_before=balance_before,
            balance_after=wallet.available_balance,
            description=f"Admin Adjustment by {admin_user.email}. Context Notes: {reason}"
        )
        return tx
    
class AdminWithdrawalService:

    @classmethod
    def approve_withdrawal(cls, withdrawal_id: str, admin_user) -> WithdrawalRequest:
        
        # ─── PHASE 1: ROW SELECTION AND METHOD-SPECIFIC VALIDATION CHECKS ───
        with transaction.atomic():
            try:
                withdrawal = WithdrawalRequest.objects.select_for_update().get(id=withdrawal_id)
            except WithdrawalRequest.DoesNotExist:
                raise ValidationError("Withdrawal record not found.")

            if withdrawal.status != WithdrawalRequest.WithdrawalStatus.PENDING:
                raise ValidationError(f"Cannot process an already processed request ({withdrawal.status}).")

            user = withdrawal.wallet.user
            stripe_account_id = None

            # Look up method configurations through relational nesting properties
            if withdrawal.withdrawal_method.type == WithdrawalMethod.MethodType.STRIPE:
                try:
                    stripe_account = user.stripe_account
                except Exception:
                    raise ValidationError("No Stripe Connected Account profile is linked to this user.")

                if not stripe_account.details_submitted:
                    raise ValidationError("Finish Stripe onboarding profile registration details first.")

                if not stripe_account.charges_enabled:
                    raise ValidationError("Charges capabilities are not enabled on this Connect sub-account profile.")

                if not stripe_account.payouts_enabled:
                    raise ValidationError("Payout configurations are not enabled. Check bank clearance documentation requirements on Stripe.")

                stripe_account_id = stripe_account.stripe_account_id

            withdrawal.status = WithdrawalRequest.WithdrawalStatus.APPROVED
            withdrawal.save(update_fields=["status"])

        # ─── PHASE 2: EXTERNAL STRIPE API EXECUTION (OUTSIDE DATABASE LOCK) ───
        stripe_response = None

        if withdrawal.withdrawal_method.type == WithdrawalMethod.MethodType.STRIPE:
            amount_in_cents = int(float(withdrawal.amount) * 100)
            
            try:
                transfer = stripe.Transfer.create(
                    amount=amount_in_cents,
                    currency="usd",
                    destination=stripe_account_id,
                    transfer_group=f"withdrawal_{withdrawal.id}",
                    description=f"Withdrawal {withdrawal.id}"
                )

                payout = stripe.Payout.create(
                    amount=amount_in_cents,
                    currency="usd",
                    stripe_account=stripe_account_id
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

            if (
                withdrawal.withdrawal_method.type
                == WithdrawalMethod.MethodType.STRIPE
                and stripe_response
            ):
                if stripe_response.get("success") is True:
                    withdrawal.stripe_transfer_id = stripe_response["transfer_id"]
                    withdrawal.stripe_payout_id = stripe_response["payout_id"]
                    withdrawal.save(update_fields=["stripe_transfer_id", "stripe_payout_id"])

                    WalletTransaction.objects.create(
                        wallet=wallet,
                        type="WITHDRAWAL",  
                        amount=-withdrawal.amount,     
                        status="PENDING",
                        balance_before=wallet.available_balance,
                        balance_after=wallet.available_balance,
                        reference=stripe_response["payout_id"],
                        description=f"Stripe processing withdrawal. Reference: {stripe_response['payout_id']}"
                    )

                    transaction.on_commit(lambda: notify_withdrawal_approved(
                        user=wallet.user,
                        withdrawal=withdrawal,
                    ))
                else:
                    withdrawal.status = WithdrawalRequest.WithdrawalStatus.FAILED
                    withdrawal.rejection_reason = stripe_response.get("error_message")
                    withdrawal.save(update_fields=["status", "rejection_reason"])

                    balance_before = wallet.available_balance
                    wallet.available_balance += withdrawal.amount
                    wallet.save(update_fields=["available_balance"])

                    WalletTransaction.objects.create(
                        wallet=wallet,
                        type="WITHDRAWAL_CANCEL", 
                        amount=withdrawal.amount,            
                        status="COMPLETED",
                        balance_before=balance_before,
                        balance_after=wallet.available_balance,
                        description=f"Stripe transaction failed: {stripe_response.get('error_message')}. Funds returned to account balance."
                    )

                    transaction.on_commit(lambda: notify_withdrawal_rejected(
                        user=wallet.user,
                        withdrawal=withdrawal,
                    ))

            else:
                withdrawal.status = WithdrawalRequest.WithdrawalStatus.COMPLETED
                withdrawal.save(update_fields=["status"])

                wallet.total_withdrawn += withdrawal.amount
                wallet.save(update_fields=["total_withdrawn"])

                WalletTransaction.objects.create(
                    wallet=wallet,
                    type="WITHDRAWAL",  
                    amount=-withdrawal.amount,     
                    status="COMPLETED",
                    balance_before=wallet.available_balance,
                    balance_after=wallet.available_balance,
                    reference=f"MAN-BANK-{withdrawal.id}",
                    description=f"Manual bank routing payout successfully processed and approved."
                )

                transaction.on_commit(lambda: notify_withdrawal_approved(
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

        if withdrawal.status != WithdrawalRequest.WithdrawalStatus.PENDING:
            raise ValidationError(f"Cannot reject a withdrawal that is already {withdrawal.status}.")

        wallet = Wallet.objects.select_for_update().get(id=withdrawal.wallet_id)
        amount = Decimal(str(withdrawal.amount))

        balance_before = wallet.available_balance
        wallet.available_balance += amount
        wallet.save(update_fields=["available_balance"])

        withdrawal.status = WithdrawalRequest.WithdrawalStatus.FAILED
        withdrawal.rejection_reason = rejection_reason
        withdrawal.save(update_fields=["status", "rejection_reason"])

        WalletTransaction.objects.create(
            wallet=wallet,
            type="WITHDRAWAL_CANCEL", 
            amount=amount,            
            status="COMPLETED",
            balance_before=balance_before,
            balance_after=wallet.available_balance,
            description=f"Refund: Withdrawal Request ID {withdrawal.id} was rejected. Reason: {rejection_reason}"
        )

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

        if withdrawal.status != WithdrawalRequest.WithdrawalStatus.APPROVED:
            raise ValidationError(f"Only 'APPROVED' requests can be marked as paid. Current state: {withdrawal.status}")

        withdrawal.status = WithdrawalRequest.WithdrawalStatus.COMPLETED
        withdrawal.completed_at = timezone.now()
        withdrawal.save(
            update_fields=[
                "status",
                "completed_at",
            ]
        )

        logger.info(f"Admin {admin_user.email} marked withdrawal {withdrawal.id} as physically paid.")
        return withdrawal


 

# apps/wallets/services.py

import logging
from decimal import Decimal
import stripe

from django.conf import settings
from django.db import transaction
from django.core.exceptions import ValidationError

from apps.wallets.models import Wallet, WalletTransaction
from apps.notifications.services import notify_wallet_topup_success
from apps.notifications.utils.email import send_wallet_topup_email

logger = logging.getLogger(__name__)


class WalletPaymentService:

    @classmethod
    def create_topup_checkout(cls, user, amount):
        """
        Creates a Stripe Checkout Session for wallet top-up.
        """
        success_url = getattr(
            settings,
            "STRIPE_TOPUP_SUCCESS_URL",
            "http://localhost:3600/sender-wallet/topup/success?session_id={CHECKOUT_SESSION_ID}",
        )
        cancel_url = getattr(
            settings,
            "STRIPE_TOPUP_CANCEL_URL",
            "http://localhost:3600/sender-wallet/topup/cancel",
        )

        try:
            session = stripe.checkout.Session.create(
                mode="payment",
                payment_method_types=["card"],
                customer_email=user.email,
                success_url=success_url,
                cancel_url=cancel_url,
                metadata={
                    "payment_type": "wallet_topup",
                    "user_id": str(user.id),
                    "amount": str(amount),
                },
                line_items=[
                    {
                        "price_data": {
                            "currency": "usd",
                            "unit_amount": int(amount * 100),
                            "product_data": {
                                "name": "Wallet Top-up",
                                "description": f"Wallet funding for {user.email}",
                            },
                        },
                        "quantity": 1,
                    }
                ],
            )
            return session

        except stripe.error.StripeError as e:
            logger.error("Stripe Checkout creation failed for user %s: %s", user.id, str(e))
            raise ValidationError(f"Stripe could not create a top-up session: {str(e)}")

    # -------------------------------------------------------------------------
    # 🆕 ADD THIS METHOD BELOW
    # -------------------------------------------------------------------------


# apps/wallets/services.py

    @classmethod
    def process_topup(cls, event):
        """
        Processes completed wallet top-up checkout session from Stripe Webhook.
        Ensures idempotent wallet balance updates and records running balances.
        """
        # 1. Safely extract session data dictionary
        if isinstance(event, dict):
            session_data = event.get("data", {}).get("object", {})
        else:
            session_obj = getattr(event.data, "object", {})
            session_data = session_obj.to_dict() if hasattr(session_obj, "to_dict") else session_obj

        session_id = session_data.get("id")
        
        # 2. Extract metadata safely
        metadata = session_data.get("metadata") or {}
        if hasattr(metadata, "to_dict"):
            metadata = metadata.to_dict()

        user_id = metadata.get("user_id")
        amount_str = metadata.get("amount")

        if not user_id or not amount_str:
            logger.error("Missing metadata (user_id/amount) in top-up session: %s", session_id)
            return

        amount = Decimal(str(amount_str))

        with transaction.atomic():
            # 3. Idempotency Check: Prevent double crediting
            if WalletTransaction.objects.filter(reference=session_id).exists():
                logger.info("Top-up session %s was already processed.", session_id)
                return

            try:
                wallet = Wallet.objects.select_for_update().get(user_id=user_id)
            except Wallet.DoesNotExist:
                logger.error("Wallet not found for user ID %s during top-up processing.", user_id)
                return

            # -----------------------------------------------------------------
            # 🆕 RECORD RUNNING BALANCES
            # -----------------------------------------------------------------
            balance_before = wallet.available_balance
            wallet.available_balance += amount
            wallet.save(update_fields=["available_balance"])
            balance_after = wallet.available_balance
            # -----------------------------------------------------------------

             # 4. Determine Transaction Type Enum
            transaction_type = getattr(
                WalletTransaction.TransactionType,
                "TOPUP",
                getattr(WalletTransaction.TransactionType, "DEPOSIT", "TOPUP"),
            )

            # 5. Create historical ledger entry with running balances
            WalletTransaction.objects.create(
                wallet=wallet,
                type=transaction_type,
                amount=amount,
                status=WalletTransaction.TransactionStatus.COMPLETED,
                reference=session_id,
                description=f"Wallet top-up via Stripe (${amount:.2f}).",
                balance_before=balance_before,
                balance_after=balance_after,
            )

            # 6. Trigger Notifications & Emails after DB commit
            user = wallet.user

            def send_topup_alerts():
                # Trigger in-app / WebSocket notification
                notify_wallet_topup_success(
                    user=user,
                    amount=amount,
                    reference=session_id,
                )
                
                # 🆕 ADDED HERE: Trigger Email delivery pipeline
                try:
                    from apps.notifications.utils.email import send_wallet_topup_email
                    send_wallet_topup_email(
                        user=user,
                        amount=amount,
                        balance_after=balance_after,
                        reference=session_id,
                    )
                except ImportError:
                    logger.warning("send_wallet_topup_email function not found.")
                except Exception as e:
                    logger.error("Failed to trigger top-up email: %s", str(e))

            transaction.on_commit(send_topup_alerts)

            logger.info("Successfully processed wallet top-up of $%s for user %s.", amount, user_id)