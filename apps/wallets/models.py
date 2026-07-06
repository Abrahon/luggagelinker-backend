import uuid
from django.db import models
from django.conf import settings
from decimal import Decimal

class Wallet(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name="wallet"
    )
    available_balance = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=Decimal("0.00")
    )
    pending_balance = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=Decimal("0.00")
    )
    total_earned = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=Decimal("0.00")
    )
    total_withdrawn = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=Decimal("0.00")
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username}'s Wallet - Avail: ${self.available_balance}"


class WalletTransaction(models.Model):
    class TransactionType(models.TextChoices):
        ESCROW_HOLD = "ESCROW_HOLD", "Escrow Hold"
        ESCROW_RELEASE = "ESCROW_RELEASE", "Escrow Release"
        WITHDRAWAL = "WITHDRAWAL", "Withdrawal"
        WITHDRAWAL_CANCEL = "WITHDRAWAL_CANCEL", "Withdrawal Cancel"
        REFUND = "REFUND", "Refund"
        ADJUSTMENT = "ADJUSTMENT", "Adjustment"

    class TransactionStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wallet = models.ForeignKey(
        Wallet, 
        on_delete=models.CASCADE, 
        related_name="transactions"
    )
    booking = models.ForeignKey(
        "bookings.Booking", 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="wallet_transactions"
    )
    type = models.CharField(max_length=20, choices=TransactionType.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(
        max_length=15, 
        choices=TransactionStatus.choices, 
        default=TransactionStatus.PENDING
    )
    
    # --- 10/10 IMMUTABLE AUDIT TRAIL SENSORS ---
    balance_before = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    
    description = models.TextField(blank=True)
    
    # Idempotency Key / Reference Tracking to completely block dual-processing
    reference = models.CharField(max_length=100, unique=True, null=True, blank=True) 
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # High performance composite reads and audit speed optimization
        indexes = [
            models.Index(fields=["wallet", "-created_at"]),
            models.Index(fields=["booking"]),
            models.Index(fields=["reference"]),
        ]

    def __str__(self):
        return f"{self.type} ({self.status}) - ${self.amount}"




import uuid
import logging
from django.db import models
from apps.wallets.models import Wallet  # Adjust import path if needed

class WithdrawalRequest(models.Model):

    class WithdrawalStatus(models.TextChoices):
        PENDING = "PENDING", "Pending Approval"
        APPROVED = "APPROVED", "Approved & Processing"
        COMPLETED = "COMPLETED", "Completed"
        REJECTED = "REJECTED", "Rejected"
        FAILED = "FAILED", "Failed"  #

    class WithdrawalMethod(models.TextChoices):
        STRIPE = "STRIPE", "Stripe Bank Payout"
        BANK = "BANK", "Bank Account"
        BKASH = "BKASH", "bKash"
        NAGAD = "NAGAD", "Nagad"
        ROCKET = "ROCKET", "Rocket"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.CASCADE,
        related_name="withdrawals"
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    status = models.CharField(
        max_length=15,
        choices=WithdrawalStatus.choices,
        default=WithdrawalStatus.PENDING
    )

    # -----------------------------
    # Withdrawal Method (Kept the required, non-nullable one)
    # -----------------------------
    method = models.CharField(
        max_length=20,
        choices=WithdrawalMethod.choices
    )

    # -----------------------------
    # Common Information
    # -----------------------------
    account_name = models.CharField(
        max_length=150,
        blank=True,
        null=True
    )

    account_number = models.CharField(
        max_length=50, 
        blank=True, 
        null=True
    )

    # -----------------------------
    # Only for BANK
    # -----------------------------
    bank_name = models.CharField(
        max_length=100,
        blank=True
    )

    branch_name = models.CharField(
        max_length=100,
        blank=True
    )

    routing_number = models.CharField(
        max_length=50,
        blank=True
    )

    # -----------------------------
    # Admin
    # -----------------------------
    rejection_reason = models.TextField(
        blank=True,
        null=True
    )
    
    stripe_transfer_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Stripe platform transfer tracking reference (tr_...)"
    )
    stripe_payout_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Stripe express destination payout tracking reference (po_...)"
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp confirming absolute banking clearance settlement."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["wallet", "-created_at"]),
            models.Index(fields=["status"]),
            models.Index(fields=["method"]),
        ]





import uuid
from django.db import models
from django.conf import settings


class StripeConnectedAccount(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="stripe_account",
    )

    # e.g. acct_1ABCDEFxxxxxxxx
    stripe_account_id = models.CharField(
        max_length=100,
        unique=True,
    )

    payouts_enabled = models.BooleanField(default=False)

    charges_enabled = models.BooleanField(default=False)

    details_submitted = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email} ({self.stripe_account_id})"