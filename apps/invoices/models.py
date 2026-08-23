import uuid

from django.conf import settings
from django.db import models

from apps.payment.models import (
    BookingPayment,
    BookingPaymentGateway,
)


class InvoiceStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    REFUNDED = "REFUNDED", "Refunded"
    CANCELLED = "CANCELLED", "Cancelled"


class Invoice(models.Model):

    # =========================================================
    # ID
    # =========================================================

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    # =========================================================
    # INVOICE NUMBER
    # =========================================================

    invoice_number = models.CharField(
        max_length=50,
        unique=True,
        editable=False,
    )

    # =========================================================
    # RELATIONSHIPS
    # =========================================================

    booking = models.OneToOneField(
        "bookings.Booking",
        on_delete=models.PROTECT,
        related_name="invoice",
    )

    payment = models.OneToOneField(
        BookingPayment,
        on_delete=models.PROTECT,
        related_name="invoice",
    )

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="sent_invoices",
    )

    traveler = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="received_invoices",
    )

    package = models.ForeignKey(
        "packages.Package",
        on_delete=models.PROTECT,
    )

    trip = models.ForeignKey(
        "trips.Trip",
        on_delete=models.PROTECT,
    )

    # =========================================================
    # FINANCIAL SNAPSHOT
    # =========================================================

    reward = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    platform_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    total_paid = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    currency = models.CharField(
        max_length=10,
        default="USD",
    )

    # =========================================================
    # PAYMENT INFORMATION
    # =========================================================

    payment_method = models.CharField(
        max_length=20,
        choices=BookingPaymentGateway.choices,
    )

    transaction_id = models.CharField(
        max_length=255,
        blank=True,
    )

    # =========================================================
    # INVOICE STATUS
    # =========================================================

    status = models.CharField(
        max_length=20,
        choices=InvoiceStatus.choices,
        default=InvoiceStatus.ACTIVE,
    )

    # =========================================================
    # PDF
    # =========================================================

    pdf_generated_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    pdf = models.FileField(
        upload_to="invoices/",
        blank=True,
        null=True,
    )

    # =========================================================
    # DOWNLOAD TRACKING
    # =========================================================

    last_downloaded_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    # =========================================================
    # TIMESTAMPS
    # =========================================================

    invoice_date = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    # =========================================================
    # META
    # =========================================================

    class Meta:
        db_table = "invoices"

        ordering = [
            "-invoice_date",
        ]

        indexes = [
            models.Index(
                fields=["invoice_number"],
            ),
            models.Index(
                fields=["sender"],
            ),
            models.Index(
                fields=["traveler"],
            ),
            models.Index(
                fields=["invoice_date"],
            ),
        ]

    # =========================================================
    # STRING
    # =========================================================

    def __str__(self):
        return f"{self.invoice_number} ({self.status})"

    # =========================================================
    # SAVE
    # =========================================================

    def save(self, *args, **kwargs):

        if not self.invoice_number:

            from django.utils import timezone
            from django.db import transaction

            year = timezone.now().year
            prefix = f"INV-{year}-"

            with transaction.atomic():

                last_invoice = (
                    Invoice.objects
                    .filter(
                        invoice_number__startswith=prefix
                    )
                    .select_for_update()
                    .order_by("invoice_date")
                    .last()
                )

                if last_invoice:

                    last_number = int(
                        last_invoice.invoice_number
                        .split("-")[-1]
                    )

                    new_number = last_number + 1

                else:
                    new_number = 1

                self.invoice_number = (
                    f"{prefix}{new_number:05d}"
                )

        super().save(*args, **kwargs)