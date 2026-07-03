from django.db import models

# Create your models here.
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
    # Linking directly to your Booking model
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
    description = models.TextField(blank=True)
    reference = models.CharField(max_length=100, blank=True) 
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.type} ({self.status}) - ${self.amount} for {self.wallet.user.username}"