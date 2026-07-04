from rest_framework import serializers
from decimal import Decimal
from .models import Wallet, WalletTransaction, WithdrawalRequest
import logging
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from apps.wallets.models import Wallet, WithdrawalRequest, WalletTransaction
logger = logging.getLogger(__name__)

class WalletSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = Wallet
        fields = [
            "id",
            "username",
            "available_balance",
            "pending_balance",
            "total_earned",
            "total_withdrawn",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class WalletTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletTransaction
        fields = [
            "id",
            "booking",
            "type",
            "amount",
            "status",
            "balance_before",
            "balance_after",
            "description",
            "reference",
            "created_at",
        ]
        read_only_fields = fields


class WithdrawalRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = WithdrawalRequest
        fields = [
            "id",
            "amount",
            "status",
            "bank_account_info",
            "rejection_reason",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "status", "rejection_reason", "created_at", "updated_at"]

    def validate_amount(self, value):
        if value <= Decimal("0.00"):
            raise serializers.ValidationError("Withdrawal amount must be greater than zero.")
        if value < Decimal("10.00"):
            raise serializers.ValidationError("The minimum allowable payout request is $10.00.")
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        if not request or not request.user:
            raise serializers.ValidationError("Authentication context missing.")

        user = request.user
        amount = attrs.get("amount")

        # ✅ Clean read-only retrieval during validation step
        try:
            wallet = Wallet.objects.get(user=user)
        except Wallet.DoesNotExist:
            raise serializers.ValidationError("Active financial wallet profile not found.")

        if wallet.available_balance < amount:
            raise serializers.ValidationError({
                "amount": f"Insufficient available funds. Liquid balance: ${wallet.available_balance}."
            })

        return attrs


class EscrowHoldSerializer(serializers.Serializer):
    booking_id = serializers.UUIDField(required=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=True)

    def validate_amount(self, value):
        if value <= Decimal("0.00"):
            raise serializers.ValidationError("Escrow commitment value must be greater than zero.")
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        user = request.user
        amount = attrs.get("amount")

        # ✅ Clean read-only retrieval during validation step
        try:
            wallet = Wallet.objects.get(user=user)
        except Wallet.DoesNotExist:
            raise serializers.ValidationError("Sender wallet instance missing.")

        if wallet.available_balance < amount:
            raise serializers.ValidationError({
                "amount": f"Insufficient balance to place escrow lock. Available: ${wallet.available_balance}."
            })

        return attrs



# admin service class for handling withdrawal approvals, rejections, and marking as paid

class AdminWithdrawalService:

    @classmethod
    @transaction.atomic
    def approve_withdrawal(cls, withdrawal_id: str, admin_user) -> WithdrawalRequest:
        """
        Approves a withdrawal request. Since funds were ALREADY deducted from 
        available_balance during request initialization, we DO NOT deduct them again here.
        """
        try:
            withdrawal = WithdrawalRequest.objects.select_for_update().get(id=withdrawal_id)
        except WithdrawalRequest.DoesNotExist:
            raise ValidationError("Withdrawal request not found.")

        if withdrawal.status != "PENDING":
            raise ValidationError(f"Cannot approve a withdrawal that is already {withdrawal.status}.")

        wallet = Wallet.objects.select_for_update().get(id=withdrawal.wallet_id)
        amount = Decimal(str(withdrawal.amount))

        # 🟢 CHANGED: Do NOT deduct from wallet.available_balance here (it was handled on creation)
        # Instead, just update the total accumulated withdrawn metrics tracking field
        wallet.total_withdrawn += amount
        wallet.save(update_fields=["total_withdrawn"])

        # Advance status milestones
        withdrawal.status = "APPROVED"
        withdrawal.reviewed_by = admin_user
        withdrawal.reviewed_at = timezone.now()
        withdrawal.save(update_fields=["status", "reviewed_by", "reviewed_at"])

        # Cut matching audit trail record for reconciliation stability
        WalletTransaction.objects.create(
            wallet=wallet,
            withdrawal_request=withdrawal,
            type="WITHDRAWAL",  
            amount=-amount,     
            status="COMPLETED",
            balance_before=wallet.available_balance, # Stays same since deduction already happened
            balance_after=wallet.available_balance,
            description=f"Withdrawal request #{withdrawal.id} approved by admin."
        )

        return withdrawal

    @classmethod
    @transaction.atomic
    def reject_withdrawal(cls, withdrawal_id: str, admin_user, rejection_reason: str) -> WithdrawalRequest:
        """Rejects a withdrawal request and REFUNDS the deducted funds back to available_balance."""
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

        # 🟢 REFUND LOGIC: Give the money back to the user since it was deducted on creation
        balance_before = wallet.available_balance
        wallet.available_balance += amount
        wallet.save(update_fields=["available_balance"])

        # Update withdrawal request state
        withdrawal.status = "REJECTED"
        withdrawal.rejection_reason = rejection_reason
        withdrawal.reviewed_by = admin_user
        withdrawal.reviewed_at = timezone.now()
        withdrawal.save(update_fields=["status", "rejection_reason", "reviewed_by", "reviewed_at"])

        # Create a ledger record showing the refund entry
        WalletTransaction.objects.create(
            wallet=wallet,
            withdrawal_request=withdrawal,
            type="WITHDRAWAL_REFUND", # Use your matching transaction type enum
            amount=amount,            # Positive number because we are returning it
            status="COMPLETED",
            balance_before=balance_before,
            balance_after=wallet.available_balance,
            description=f"Refund: Withdrawal request #{withdrawal.id} was rejected."
        )

        return withdrawal


    @classmethod
    @transaction.atomic
    def mark_as_paid(cls, withdrawal_id: str, admin_user) -> WithdrawalRequest:
        """Marks an approved withdrawal as physically processed and paid via fiat gateway banking tools."""
        try:
            withdrawal = WithdrawalRequest.objects.select_for_update().get(id=withdrawal_id)
        except WithdrawalRequest.DoesNotExist:
            raise ValidationError("Withdrawal request not found.")

        if withdrawal.status != "APPROVED":
            raise ValidationError(f"Only 'APPROVED' requests can be marked as paid. Current state: {withdrawal.status}")

        withdrawal.status = "PAID"
        withdrawal.paid_at = timezone.now()
        withdrawal.save(update_fields=["status", "paid_at"])

        logger.info(f"Admin {admin_user.email} marked withdrawal {withdrawal.id} as physically paid.")
        return withdrawal