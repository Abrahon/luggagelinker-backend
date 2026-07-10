import uuid
from django.db import models
from django.conf import settings
from apps.payment.models import BookingPayment, BookingPaymentGateway

class InvoiceStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    REFUNDED = "REFUNDED", "Refunded"
    CANCELLED = "CANCELLED", "Cancelled"

class Invoice(models.Model):
    id = models.UUIDField(
        primary_key=True, 
        default=uuid.uuid4, 
        editable=False
    )
    
    invoice_number = models.CharField(
        max_length=50, 
        unique=True, 
        editable=False
    )
    
    # Structural Relationships & Core Corrections
    booking = models.OneToOneField(
        'bookings.Booking', 
        on_delete=models.PROTECT, 
        related_name="invoice"
    )
    payment = models.OneToOneField(
        BookingPayment, 
        on_delete=models.PROTECT, 
        related_name="invoice"
    )
    
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.PROTECT, 
        related_name="sent_invoices"
    )
    traveler = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.PROTECT, 
        related_name="received_invoices"
    )
    
    package = models.ForeignKey('packages.Package', on_delete=models.PROTECT)
    trip = models.ForeignKey('trips.Trip', on_delete=models.PROTECT)
    
    # Financial Breakdown Snapshots (Saved on authorization)
    reward = models.DecimalField(max_digits=10, decimal_places=2)
    platform_fee = models.DecimalField(max_digits=10, decimal_places=2)
    total_paid = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default="USD")
    
    # Gateway Metadata
    payment_method = models.CharField(
        max_length=20,
        choices=BookingPaymentGateway.choices,
    )
    transaction_id = models.CharField(
        max_length=255,
        blank=True
    )
    
    # Invoice Lifecycle Status (Kept separate from payment state)
    status = models.CharField(
        max_length=20,
        choices=InvoiceStatus.choices,
        default=InvoiceStatus.ACTIVE
    )
    
    # Optimized Storage & Tracking Meta Fields
    pdf = models.FileField(
        upload_to="invoices/",
        blank=True,
        null=True
    )
    last_downloaded_at = models.DateTimeField(
        null=True,
        blank=True
    )
    invoice_date = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "invoices"
        ordering = ["-invoice_date"]
        indexes = [
            models.Index(fields=["invoice_number"]),
            models.Index(fields=["sender"]),
            models.Index(fields=["traveler"]),
            models.Index(fields=["invoice_date"]),
        ]

    def __str__(self):
        return f"{self.invoice_number} ({self.status})"

    def save(self, *args, **kwargs):
        # Concurrency-Safe Invoice Number Sequential Generation
        if not self.invoice_number:
            from django.utils import timezone
            from django.db import transaction
            
            year = timezone.now().year
            prefix = f"INV-{year}-"
            
            # Using an atomic database transaction block with select_for_update 
            # to line up simultaneous requests sequentially and prevent duplicate serial keys
            with transaction.atomic():
                last_invoice = Invoice.objects.filter(
                    invoice_number__startswith=prefix
                ).select_for_update().order_by('invoice_date').last()
                
                if last_invoice:
                    last_number = int(last_invoice.invoice_number.split("-")[-1])
                    new_number = last_number + 1
                else:
                    new_number = 1
                    
                self.invoice_number = f"{prefix}{new_number:05d}"
            
        super().save(*args, **kwargs)