from rest_framework import serializers
from decimal import Decimal
from .models import Wallet, WalletTransaction, WithdrawalRequest
import logging
from decimal import Decimal
from apps.bookings.models import Booking

import logging
from decimal import Decimal
from django.contrib.auth import get_user_model, models
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



from decimal import Decimal

from rest_framework import serializers

from apps.wallets.models import (
    Wallet,
    WithdrawalMethod,
    WithdrawalRequest,
)
from apps.wallets.serializers import WithdrawalMethodSerializer


class WithdrawalRequestSerializer(serializers.ModelSerializer):
    """
    Create and retrieve withdrawal requests.

    The traveler selects one of their saved withdrawal methods.
    The admin reviews and approves/rejects the request later.
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
                "Minimum withdrawal amount is $10.00."
            )

        return value

    def validate(self, attrs):
        request = self.context["request"]
        user = request.user

        withdrawal_method = attrs["withdrawal_method"]
        amount = attrs["amount"]

        # -----------------------------------------
        # Method must belong to current user
        # -----------------------------------------
        if withdrawal_method.user != user:
            raise serializers.ValidationError({
                "withdrawal_method":
                    "This withdrawal method does not belong to you."
            })

        # -----------------------------------------
        # Method must be active
        # -----------------------------------------
        if not withdrawal_method.is_active:
            raise serializers.ValidationError({
                "withdrawal_method":
                    "This withdrawal method has been disabled."
            })

        # -----------------------------------------
        # Wallet must exist
        # -----------------------------------------
        try:
            wallet = Wallet.objects.get(user=user)

        except Wallet.DoesNotExist:
            raise serializers.ValidationError(
                "Wallet not found."
            )

        # -----------------------------------------
        # Enough available balance
        # -----------------------------------------
        if wallet.available_balance < amount:
            raise serializers.ValidationError({
                "amount":
                    f"Available balance is only ${wallet.available_balance}."
            })

        # -----------------------------------------
        # Prevent multiple pending withdrawals
        # -----------------------------------------
        if WithdrawalRequest.objects.filter(
            wallet=wallet,
            status__in=[
                WithdrawalRequest.WithdrawalStatus.PENDING,
                WithdrawalRequest.WithdrawalStatus.APPROVED,
                WithdrawalRequest.WithdrawalStatus.PROCESSING,
            ],
        ).exists():
            raise serializers.ValidationError(
                "You already have an active withdrawal request processing."
            )

        # -----------------------------------------
        # Stripe validation (only for Stripe)
        # -----------------------------------------
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
        wallet = Wallet.objects.get(
            user=self.context["request"].user
        )

        return WithdrawalRequest.objects.create(
            wallet=wallet,
            withdrawal_method=validated_data["withdrawal_method"],
            amount=validated_data["amount"],
        )

class WithdrawalHistorySerializer(serializers.ModelSerializer):
    withdrawal_method = serializers.SerializerMethodField()

    class Meta:
        model = WithdrawalRequest
        fields = [
            "id",
            "amount",
            "status",
            "created_at",
            "processed_at",
            "completed_at",
            "withdrawal_method",
        ]

    def get_withdrawal_method(self, obj):
        if not obj.withdrawal_method:
            return None

        method = obj.withdrawal_method

        return {
            "type": method.type,
            "type_display": method.get_type_display(),
            "account_name": method.account_name,
            "account_number": f"****{method.account_number[-4:]}",
            "bank_name": method.bank_name,
            "branch_name": method.branch_name,
        }
    
from rest_framework import serializers
from apps.wallets.models import WithdrawalRequest


# class AdminWithdrawalListSerializer(serializers.ModelSerializer):
#     traveler_name = serializers.SerializerMethodField()
#     traveler_email = serializers.EmailField(
#         source="wallet.user.email",
#         read_only=True,
#     )

#     withdrawal_method_details = serializers.SerializerMethodField()

#     class Meta:
#         model = WithdrawalRequest
#         fields = (
#             "id",
#             "traveler_name",
#             "traveler_email",
#             "withdrawal_method",
#             "withdrawal_method_details",
#             "amount",
#             "status",
#             "processed_by",
#             "processed_at",
#             "completed_at",
#             "created_at",
#         )

#     def get_traveler_name(self, obj):
#         user = obj.wallet.user

#         if hasattr(user, "profile"):
#             first = getattr(user.profile, "first_name", "")
#             last = getattr(user.profile, "last_name", "")
#             full_name = f"{first} {last}".strip()
#             if full_name:
#                 return full_name

#         return user.email

#     def get_withdrawal_method_details(self, obj):
#         method = obj.withdrawal_method

#         if not method:
#             return None

#         return {
#             "type": method.get_type_display(),
#             "account_name": method.account_name,
#             "account_number": method.account_number,
#             "bank_name": method.bank_name,
#             "branch_name": method.branch_name,
#             "is_verified": method.is_verified,
#         }


class AdminWithdrawalListSerializer(serializers.ModelSerializer):
    traveler_name = serializers.SerializerMethodField()
    traveler_email = serializers.EmailField(
        source="wallet.user.email",
        read_only=True,
    )

    # Returns: BANK / BKASH / NAGAD / ROCKET / STRIPE
    withdrawal_method = serializers.SerializerMethodField()

    withdrawal_method_details = serializers.SerializerMethodField()

    class Meta:
        model = WithdrawalRequest
        fields = [
            "id",
            "traveler_name",
            "traveler_email",
            "withdrawal_method",
            "withdrawal_method_details",
            "amount",
            "status",
            "processed_by",
            "processed_at",
            "completed_at",
            "created_at",
        ]

    def get_traveler_name(self, obj):
        user = obj.wallet.user

        if hasattr(user, "profile"):
            first = getattr(user.profile, "first_name", "")
            last = getattr(user.profile, "last_name", "")
            full_name = f"{first} {last}".strip()
            if full_name:
                return full_name

        return user.email

    def get_withdrawal_method(self, obj):
        if not obj.withdrawal_method:
            return None

        # Returns: BANK / BKASH / NAGAD / ROCKET / STRIPE
        return obj.withdrawal_method.type

    def get_withdrawal_method_details(self, obj):
        if not obj.withdrawal_method:
            return None

        method = obj.withdrawal_method

        return {
            "type": method.get_type_display(),   
            "account_name": method.account_name,
            "account_number": method.account_number,
            "bank_name": method.bank_name,
            "branch_name": method.branch_name,
            "routing_number": method.routing_number,
            "is_verified": method.is_verified,
        }

    
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


# apps/wallets/serializers.py

from rest_framework import serializers


class AdminWithdrawalStatsSerializer(serializers.Serializer):
    total_travelers_requested = serializers.IntegerField()

    total_pending_balance = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    pending_requests = serializers.IntegerField()

    completed_requests = serializers.IntegerField()




class MonthlyEarningsSerializer(serializers.Serializer):
    month = serializers.CharField()
    earnings = serializers.DecimalField(max_digits=12, decimal_places=2)
    deliveries = serializers.IntegerField()



# traveler earns escrew held
class PendingReleaseSerializer(serializers.Serializer):
    booking_id = serializers.UUIDField(source="id")
    tracking_number = serializers.CharField()
    package_title = serializers.CharField(source="package.title")
    reward = serializers.DecimalField(
        source="agreed_reward",
        max_digits=10,
        decimal_places=2,
    )
    currency = serializers.CharField()
    expected_release = serializers.DateField(
        source="trip.arrival_date",
        allow_null=True,
    )
    escrow_status = serializers.CharField()
    booking_status = serializers.CharField(source="status")




class WalletLedgerSerializer(serializers.ModelSerializer):
    reference = serializers.SerializerMethodField()
    booking_tracking = serializers.SerializerMethodField()
    booking_id = serializers.SerializerMethodField()
    transaction_date = serializers.DateTimeField(source="created_at")
    transaction_type = serializers.CharField(source="get_type_display")

    class Meta:
        model = WalletTransaction
        fields = [
            "reference",
            "transaction_date",
            "transaction_type",
            "amount",
            "booking_id",
            "booking_tracking",
            "status",
            "description",
        ]

    def get_transaction_type(self, obj):
        if (
            obj.type == WalletTransaction.TransactionType.ESCROW_RELEASE
            and obj.amount > 0
        ):
            return "Earnings"

        return obj.get_type_display()
    
    def get_reference(self, obj):
        return f"TXN-{obj.id.hex[:8].upper()}"

    def get_booking_tracking(self, obj):
        if obj.booking:
            return obj.booking.tracking_number
        return None

    def get_booking_id(self, obj):
        if obj.booking:
            return obj.booking.id
        return None


# widrawl by month

class MonthlyWithdrawalSerializer(serializers.Serializer):
    month = serializers.CharField()
    withdrawn = serializers.DecimalField(max_digits=12, decimal_places=2)
    withdrawals = serializers.IntegerField()





# traveler earning dashbaord
class TravelerEarningDashboardSerializer(serializers.Serializer):
    total_earned = serializers.DecimalField(max_digits=12, decimal_places=2)
    available_balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    pending_releases = serializers.DecimalField(max_digits=12, decimal_places=2)
    completed_deliveries = serializers.IntegerField()







class RecentCompletedBookingSerializer(serializers.ModelSerializer):
    reward = serializers.DecimalField(
        source="agreed_reward",
        max_digits=10,
        decimal_places=2,
        read_only=True,
    )

    delivered_at = serializers.DateTimeField(format="%d %b %Y")

    class Meta:
        model = Booking
        fields = [
            "id",
            "tracking_number",
            "reward",
            "currency",
            "delivered_at",
        ]


from rest_framework import serializers
from decimal import Decimal
from apps.wallets.models import Wallet


class TravelerWalletCardSerializer(serializers.ModelSerializer):
    held_in_escrow = serializers.SerializerMethodField()
    pending_payout = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()
    card_details = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()  # <--- Requires get_full_name()

    class Meta:
        model = Wallet
        fields = [
            "available_balance",
            "held_in_escrow",
            "pending_payout",
            "currency",
            "card_details",
            "full_name",
        ]

    def get_full_name(self, obj):
        """Returns the user's full name from profile, or falls back to email."""
        profile = getattr(obj.user, "profile", None)
        if profile:
            name = " ".join(
                filter(
                    None,
                    [
                        getattr(profile, "first_name", ""),
                        getattr(profile, "last_name", ""),
                    ],
                )
            )
            if name:
                return name
        return getattr(obj.user, "email", "")

    def get_held_in_escrow(self, obj):
        return Decimal("0.00")

    def get_pending_payout(self, obj):
        return obj.pending_balance

    def get_currency(self, obj):
        return "USD"

    def get_card_details(self, obj):
        holder_name = self.get_full_name(obj)

        return {
            "card_number_masked": "4829 •••• •••• 9104",
            "card_number_full": "4829741288309104",
            "card_holder_name": holder_name.upper(),
            "expiry_date": "08/28",
            "cvv": "349",
        }


# apps/wallets/serializers.py


from decimal import Decimal
from django.db import models
from django.db.models import Sum
from django.db.models.functions import Coalesce
from rest_framework import serializers

from .models import Wallet


class SenderWalletDashboardSerializer(serializers.ModelSerializer):
    total_spent = serializers.SerializerMethodField()
    total_refunded = serializers.SerializerMethodField()
    active_escrow = serializers.SerializerMethodField()
    completed_transactions = serializers.SerializerMethodField()

    class Meta:
        model = Wallet
        fields = [
            "available_balance",
            "pending_balance",
            "total_spent",
            "total_refunded",
            "active_escrow",
            "completed_transactions",
        ]

    def get_total_spent(self, obj) -> Decimal:
        spent = (
            obj.transactions.filter(
                type="ESCROW_HOLD",
                status="COMPLETED",
            )
            .aggregate(
                total=Coalesce(
                    Sum("amount"),
                    Decimal("0.00"),
                    output_field=models.DecimalField(),
                )
            )
            .get("total")
        )
        return abs(spent)

    def get_total_refunded(self, obj) -> Decimal:
        return (
            obj.transactions.filter(
                type__in=[
                    "REFUND",
                    "DISPUTE_REFUND",
                ],
                status="COMPLETED",
            )
            .aggregate(
                total=Coalesce(
                    Sum("amount"),
                    Decimal("0.00"),
                    output_field=models.DecimalField(),
                )
            )
            .get("total")
        )

    def get_active_escrow(self, obj) -> Decimal:
        return obj.pending_balance or Decimal("0.00")

    def get_completed_transactions(self, obj) -> int:
        return obj.transactions.filter(status="COMPLETED").count()



# apps/wallets/serializers.py



class SenderWalletTransactionSerializer(serializers.ModelSerializer):
    transaction_type = serializers.CharField(
        source="get_type_display",
        read_only=True
    )

    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True
    )

    booking_id = serializers.UUIDField(
        source="booking.id",
        read_only=True
    )

    booking_tracking_number = serializers.CharField(
        source="booking.tracking_number",
        read_only=True
    )

    class Meta:
        model = WalletTransaction
        fields = [
            "id",
            "booking_id",
            "booking_tracking_number",
            "type",
            "transaction_type",
            "amount",
            "status",
            "status_display",
            "description",
            "balance_before",
            "balance_after",
            "created_at",
        ]




# add money on the wallet
from decimal import Decimal
from rest_framework import serializers


class WalletTopupSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("5.00"),
        max_value=Decimal("10000.00"),
    )

    def validate_amount(self, value: Decimal) -> Decimal:
        if value <= Decimal("0.00"):
            raise serializers.ValidationError(
                "Top-up amount must be greater than $0.00."
            )

        if value < Decimal("5.00"):
            raise serializers.ValidationError(
                "Minimum wallet top-up amount is $5.00."
            )

        if value > Decimal("10000.00"):
            raise serializers.ValidationError(
                "Maximum wallet top-up amount is $10,000.00."
            )

        if value.quantize(Decimal("0.01")) != value:
            raise serializers.ValidationError(
                "Amount must contain no more than two decimal places."
            )

        return value