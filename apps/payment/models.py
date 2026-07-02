from django.db import models

# Create your models here.
import uuid

from django.conf import settings
from django.db import models


class PaymentMethod(models.TextChoices):
    STRIPE = "STRIPE", "Stripe"


class PaymentStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    SUCCEEDED = "SUCCEEDED", "Succeeded"
    FAILED = "FAILED", "Failed"
    CANCELLED = "CANCELLED", "Cancelled"
    REFUNDED = "REFUNDED", "Refunded"


class Payment(models.Model):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payments",
    )

    plan = models.ForeignKey(
        "subscriptions.Plan",
        on_delete=models.PROTECT,
        related_name="payments",
    )

    subscription = models.ForeignKey(
        "subscriptions.Subscription",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
    )

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    currency = models.CharField(
        max_length=10,
        default="USD",
    )

    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.STRIPE,
    )

    status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
    )

    stripe_checkout_session_id = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
    )

    stripe_payment_intent_id = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
    )

    stripe_customer_id = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )

    stripe_invoice_id = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
    )

    transaction_id = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
    )
    paid_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    failure_reason = models.TextField(
        blank=True,
    )

    refund_reason = models.TextField(
        blank=True,
    )

    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = "payments"
        ordering = ["-created_at"]

        indexes = [
            models.Index(fields=["user"]),
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["stripe_checkout_session_id"]),
            models.Index(fields=["stripe_payment_intent_id"]),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.plan.name} - {self.status}"



# booking payment model
import uuid
from django.db import models
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from apps.bookings.models import Booking  # Adjust path based on your project configuration

User = get_user_model()


class BookingPaymentGateway(models.TextChoices):
    STRIPE = "STRIPE", _("Stripe")
    BKASH = "BKASH", _("bKash")
    NAGAD = "NAGAD", _("Nagad")


class BookingPaymentStatus(models.TextChoices):
    PENDING = "PENDING", _("Pending Initiation")
    INITIALIZED = "INITIALIZED", _("Gateway Session Created")
    AUTHORIZED = "AUTHORIZED", _("Authorized / Held in Escrow")
    CAPTURED = "CAPTURED", _("Captured / Released to Traveler")
    REFUNDED = "REFUNDED", _("Refunded to Sender")
    FAILED = "FAILED", _("Failed")


class BookingPayment(models.Model):
    """
    Production-grade financial escrow ledger specifically for tracking P2P package delivery bookings.
    """
    id = models.UUIDField(
        primary_key=True, 
        default=uuid.uuid4, 
        editable=False
    )
    
    # Linked to your existing delivery booking flow
    booking = models.OneToOneField(
            Booking,
            on_delete=models.PROTECT,
            related_name="booking_payment",
            help_text=_("The single delivery booking instance tied to this escrow transaction.")
        )
        
    # Counter-parties (Denormalized for instant lookup performance)
    payer = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="booking_payments_made",
        help_text=_("The sender paying for the shipping.")
    )
    
    payee = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="booking_payments_received",
        help_text=_("The traveler earning the reward payment upon delivery.")
    )

    # Financial Matrix
    amount = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        help_text=_("Gross transaction amount processed via gateway.")
    )
    
    platform_fee = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0.00,
        help_text=_("Platform commission fee deducted from traveler payout.")
    )
    
    currency = models.CharField(
        max_length=3, 
        default="USD", 
        help_text=_("ISO alphabet currency code (e.g., USD, BDT).")
    )

    # Gateway Routing
    gateway = models.CharField(
        max_length=20,
        choices=BookingPaymentGateway.choices,
        default=BookingPaymentGateway.STRIPE
    )
    
    status = models.CharField(
        max_length=20,
        choices=BookingPaymentStatus.choices,
        default=BookingPaymentStatus.PENDING,
        db_index=True
    )

    # ------------------------------------------------------
    # PRODUCTION ID ALIGNMENT FOR GATEWAYS
    # ------------------------------------------------------
    # Stripe: Holds 'cs_test_...' or PaymentIntent ID 'pi_...'
    # bKash: Holds bKash 'paymentID' from Create Payment API response
    provider_payment_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        unique=True,
        db_index=True,
        help_text=_("The checkout/intent session ID generated by the external API provider.")
    )

    checkout_url = models.URLField(
        max_length=500,  # 500 length is safer as some tokenized URLs can be quite long
        blank=True,
        null=True,
        help_text=_("The active redirection link generated by the gateway for user authentication.")
    )
    
    # Stripe: Holds 'ch_...' or Charge ID
    # bKash / Nagad: Holds the actual MFS Transaction ID (TrxID) after pin confirmation
    transaction_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        unique=True,
        db_index=True,
        help_text=_("The definitive transaction reference indicating finalized settlement.")
    )

    # Compliance & Auditing
    failure_reason = models.TextField(
        blank=True,
        null=True,
        help_text=_("Raw diagnostic logging if status drops to FAILED.")
    )
    
    ip_address = models.GenericIPAddressField(
        blank=True,
        null=True,
        help_text=_("IP address tracked during checkout initialization for anti-fraud analysis.")
    )

    # Timeline Matrix
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    authorized_at = models.DateTimeField(blank=True, null=True)
    captured_at = models.DateTimeField(blank=True, null=True)
    refunded_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "gateway"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"BookingPayment {self.id} | {self.amount} {self.currency} | {self.status}"


class BookingPaymentLog(models.Model):
    """
    Append-only raw audit trail to capture incoming webhook webhook structures from Stripe, bKash, or Nagad.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking_payment = models.ForeignKey(
        BookingPayment, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name="logs"
    )
    event_type = models.CharField(max_length=100, help_text=_("e.g., payment_intent.succeeded or bKash webhook event"))
    raw_payload = models.JSONField(help_text=_("Raw immutable payload data received directly from the gateway."))
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"BookingLog {self.id} - Event: {self.event_type}"