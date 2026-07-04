from rest_framework import serializers
from decimal import Decimal
from .models import Wallet, WalletTransaction, WithdrawalRequest
import logging
from decimal import Decimal


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


