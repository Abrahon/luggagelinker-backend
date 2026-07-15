from rest_framework import serializers
from decimal import Decimal
from .models import Wallet, WalletTransaction, WithdrawalRequest
import logging
from decimal import Decimal


import logging
from decimal import Decimal
from django.contrib.auth import get_user_model
from rest_framework import serializers
from .models import (
    Wallet, 
    WalletTransaction, 
    WithdrawalRequest, 
    WithdrawalMethod
)

logger = logging.getLogger(__name__)
User = get_user_model()


from rest_framework import serializers
from .models import Wallet


class WalletSerializer(serializers.ModelSerializer):
    """
    Returns only the user's wallet balances.
    """

    class Meta:
        model = Wallet
        fields = [
            "available_balance",
            "pending_balance",
            "total_earned",
            "total_withdrawn",
        ]
        read_only_fields = fields


class WalletTransactionSerializer(serializers.ModelSerializer):
    """
    Serializer capturing audit trails for ledger transactions, detailing 
    balance shifts and reference triggers.
    """
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



class WithdrawalMethodSerializer(serializers.ModelSerializer):
    """
    Manages CRUD configurations for saved payout channels (Bank accounts, Mobile Wallets, etc.).
    Protects sensitive routing logic with structured structural validations.
    """
    type_display = serializers.CharField(source="get_type_display", read_only=True)

    class Meta:
        model = WithdrawalMethod
        fields = [
            "id",
            "type",
            "type_display",
            "account_name",
            "account_number",
            "bank_name",
            "branch_name",
            "routing_number",
            "stripe_account_id",
            "is_default",
            "is_verified",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "is_verified", "created_at", "updated_at"]

    def validate(self, attrs):
        method_type = attrs.get("type")

        # 1. Bank Payout Validations
        if method_type == WithdrawalMethod.MethodType.BANK:
            missing_fields = {}
            for field in ["account_name", "account_number", "bank_name", "branch_name", "routing_number"]:
                if not attrs.get(field):
                    missing_fields[field] = f"This field is required for {method_type} accounts."
            if missing_fields:
                raise serializers.ValidationError(missing_fields)

        # 2. Mobile Financial Services (bKash, Nagad, Rocket)
        elif method_type in [
            WithdrawalMethod.MethodType.BKASH,
            WithdrawalMethod.MethodType.NAGAD,
            WithdrawalMethod.MethodType.ROCKET
        ]:
            if not attrs.get("account_number"):
                raise serializers.ValidationError({
                    "account_number": f"Mobile account number is required for {method_type} disbursements."
                })
            # Clear bank-specific attributes if present to keep data structured
            attrs["bank_name"] = ""
            attrs["branch_name"] = ""
            attrs["routing_number"] = ""
            attrs["stripe_account_id"] = ""

        # 3. Stripe Direct Connect Payouts
        elif method_type == WithdrawalMethod.MethodType.STRIPE:
            if not attrs.get("stripe_account_id"):
                raise serializers.ValidationError({
                    "stripe_account_id": "Stripe Connected Account ID is required for card payouts."
                })
            attrs["bank_name"] = ""
            attrs["branch_name"] = ""
            attrs["routing_number"] = ""

        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user:
            validated_data["user"] = request.user
        
        # Enforce unique default active withdrawal method per user
        is_default = validated_data.get("is_default", False)
        if is_default and request and request.user:
            WithdrawalMethod.objects.filter(user=request.user, is_default=True).update(is_default=False)

        return super().create(validated_data)

    def update(self, instance, validated_data):
        request = self.context.get("request")
        is_default = validated_data.get("is_default", False)
        
        # Re-enforce default constraints on updates
        if is_default and request and request.user:
            WithdrawalMethod.objects.filter(user=request.user, is_default=True).exclude(pk=instance.pk).update(is_default=False)

        return super().update(instance, validated_data)



class WithdrawalRequestSerializer(serializers.ModelSerializer):
    """
    Serializer for creating and retrieving withdrawal requests.
    Uses a saved WithdrawalMethod instead of duplicating payout details.
    """

    withdrawal_method = serializers.PrimaryKeyRelatedField(
        queryset=WithdrawalMethod.objects.all()
    )

    withdrawal_method_details = WithdrawalMethodSerializer(
        source="withdrawal_method",
        read_only=True,
    )

    class Meta:
        model = WithdrawalRequest
        fields = [
            "id",
            "withdrawal_method",
            "withdrawal_method_details",
            "amount",
            "status",
            "stripe_transfer_id",
            "stripe_payout_id",
            "rejection_reason",
            "processed_by",
            "processed_at",
            "admin_note",
            "completed_at",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "status",
            "stripe_transfer_id",
            "stripe_payout_id",
            "rejection_reason",
            "processed_by",
            "processed_at",
            "admin_note",
            "completed_at",
            "created_at",
            "updated_at",
        ]

    def validate_amount(self, value):
        if value <= Decimal("0.00"):
            raise serializers.ValidationError(
                "Withdrawal amount must be greater than zero."
            )

        if value < Decimal("10.00"):
            raise serializers.ValidationError(
                "Minimum withdrawal amount is $10."
            )

        return value

    def validate(self, attrs):

        request = self.context["request"]
        user = request.user

        withdrawal_method = attrs["withdrawal_method"]
        amount = attrs["amount"]

        # ---------------------------------------------
        # Ensure withdrawal method belongs to the user
        # ---------------------------------------------
        if withdrawal_method.user != user:
            raise serializers.ValidationError({
                "withdrawal_method":
                    "This withdrawal method does not belong to you."
            })

        # ---------------------------------------------
        # Active check
        # ---------------------------------------------
        if not withdrawal_method.is_active:
            raise serializers.ValidationError({
                "withdrawal_method":
                    "This withdrawal method has been disabled."
            })

        # ---------------------------------------------
        # Verification check
        # ---------------------------------------------
        if not withdrawal_method.is_verified:
            raise serializers.ValidationError({
                "withdrawal_method":
                    "This withdrawal method is not verified."
            })

        # ---------------------------------------------
        # Wallet existence
        # ---------------------------------------------
        try:
            wallet = Wallet.objects.get(user=user)

        except Wallet.DoesNotExist:
            raise serializers.ValidationError(
                "Wallet not found."
            )

        # ---------------------------------------------
        # Balance check
        # ---------------------------------------------
        if wallet.available_balance < amount:
            raise serializers.ValidationError({
                "amount":
                    f"Available balance is only ${wallet.available_balance}."
            })

        # ---------------------------------------------
        # Stripe payout validation
        # ---------------------------------------------
        if withdrawal_method.type == WithdrawalMethod.MethodType.STRIPE:

            try:
                stripe = user.stripe_account

                if not stripe.payouts_enabled:
                    raise serializers.ValidationError({
                        "withdrawal_method":
                            "Stripe payouts are not enabled."
                    })

            except Exception:
                raise serializers.ValidationError({
                    "withdrawal_method":
                        "No Stripe Connect account found."
                })

        return attrs

    def create(self, validated_data):

        request = self.context["request"]

        wallet = Wallet.objects.get(user=request.user)

        return WithdrawalRequest.objects.create(
            wallet=wallet,
            withdrawal_method=validated_data["withdrawal_method"],
            amount=validated_data["amount"],
        )

class EscrowHoldSerializer(serializers.Serializer):
    """
    Validates booking identity and balance sufficiency for locks placed 
    under safe escrow holds.
    """
    booking_id = serializers.UUIDField(required=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=True)

    def validate_amount(self, value):
        if value <= Decimal("0.00"):
            raise serializers.ValidationError("Escrow commitment value must be greater than zero.")
        return value

    def validate(self, attrs):
        request = self.context.get("request")
        if not request or not request.user:
            raise serializers.ValidationError("Authentication context missing.")

        user = request.user
        amount = attrs.get("amount")

        try:
            wallet = Wallet.objects.get(user=user)
        except Wallet.DoesNotExist:
            raise serializers.ValidationError("Sender wallet instance missing.")

        if wallet.available_balance < amount:
            raise serializers.ValidationError({
                "amount": f"Insufficient balance to place escrow lock. Available: ${wallet.available_balance}."
            })

        return attrs


class StripeConnectSerializer(serializers.Serializer):
    """
    Handles authentication verification context for setting up Stripe onboarding links.
    """
    def validate(self, attrs):
        request = self.context.get("request")
        if not request or not request.user:
            raise serializers.ValidationError("Authentication context missing.")
        return attrs



from rest_framework import serializers
from .models import WalletTransaction


class WalletRecentActivitySerializer(serializers.ModelSerializer):
    title = serializers.SerializerMethodField()
    subtitle = serializers.SerializerMethodField()
    category = serializers.SerializerMethodField()
    icon = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    booking_id = serializers.SerializerMethodField()
    tracking_number = serializers.SerializerMethodField()
    amount = serializers.SerializerMethodField()

    class Meta:
        model = WalletTransaction
        fields = [
            "id",
            "title",
            "subtitle",
            "category",
            "icon",
            "status",
            "amount",
            "booking_id",
            "tracking_number",
            "created_at",
        ]

    def get_amount(self, obj):
        return str(obj.amount)

    def get_booking_id(self, obj):
        return str(obj.booking.id) if obj.booking else None

    def get_tracking_number(self, obj):
        return obj.booking.tracking_number if obj.booking else None

    def get_status(self, obj):
        return obj.status.lower()

    def get_category(self, obj):

        if obj.type in [
            WalletTransaction.TransactionType.ESCROW_HOLD,
            WalletTransaction.TransactionType.ESCROW_RELEASE,
        ]:
            return "earning"

        if obj.type in [
            WalletTransaction.TransactionType.WITHDRAWAL,
            WalletTransaction.TransactionType.WITHDRAWAL_CANCEL,
        ]:
            return "withdrawal"

        if obj.type == WalletTransaction.TransactionType.REFUND:
            return "refund"

        if obj.type == WalletTransaction.TransactionType.ADJUSTMENT:
            return "adjustment"

        return "other"

    def get_icon(self, obj):

        if obj.type == WalletTransaction.TransactionType.ESCROW_HOLD:
            return "clock"

        if obj.type == WalletTransaction.TransactionType.ESCROW_RELEASE:
            return "wallet"

        if obj.type == WalletTransaction.TransactionType.WITHDRAWAL:
            return "arrow_up"

        if obj.type == WalletTransaction.TransactionType.WITHDRAWAL_CANCEL:
            return "rotate_ccw"

        if obj.type == WalletTransaction.TransactionType.REFUND:
            return "rotate_ccw"

        if obj.type == WalletTransaction.TransactionType.ADJUSTMENT:
            return "settings"

        return "wallet"

    def get_title(self, obj):

        booking = obj.booking

        if obj.type == WalletTransaction.TransactionType.ESCROW_HOLD:

            if booking:
                if booking.status == "PAYMENT_PENDING":
                    return "Payment Authorized"

                if booking.status == "CONFIRMED":
                    return "Payment Held in Escrow"

                if booking.status in [
                    "PICKED_UP",
                    "IN_TRANSIT",
                ]:
                    return "Earnings Pending"

            return "Escrow Hold"

        if obj.type == WalletTransaction.TransactionType.ESCROW_RELEASE:

            if booking:
                if booking.status == "COMPLETED":
                    return "Earnings Received"

                if booking.status == "DELIVERED":
                    return "Payment Released"

            return "Escrow Released"

        if obj.type == WalletTransaction.TransactionType.WITHDRAWAL:
            return "Withdrawal Request"

        if obj.type == WalletTransaction.TransactionType.WITHDRAWAL_CANCEL:
            return "Withdrawal Cancelled"

        if obj.type == WalletTransaction.TransactionType.REFUND:
            return "Booking Refunded"

        if obj.type == WalletTransaction.TransactionType.ADJUSTMENT:
            return "Balance Adjustment"

        return obj.get_type_display()

    def get_subtitle(self, obj):

        booking = obj.booking

        if booking:

            if obj.type == WalletTransaction.TransactionType.ESCROW_HOLD:
                return (
                    f"Booking {booking.tracking_number} • "
                    f"{booking.get_status_display()}"
                )

            if obj.type == WalletTransaction.TransactionType.ESCROW_RELEASE:
                return (
                    f"Booking {booking.tracking_number} • "
                    f"{booking.get_status_display()}"
                )

            if obj.type == WalletTransaction.TransactionType.REFUND:
                return f"Refund for Booking {booking.tracking_number}"

        if obj.description:
            return obj.description

        return ""