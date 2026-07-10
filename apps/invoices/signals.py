from django.db.models.signals import post_save
from django.dispatch import receiver
from apps.payment.models import BookingPayment
from apps.invoices.models import Invoice, InvoiceStatus

@receiver(post_save, sender=BookingPayment)
def handle_payment_status_change(sender, instance, created, **kwargs):
    """
    Listens to BookingPayment records to automate our historical invoicing layout steps.
    """
    # 1. Trigger Invoice structure on payment authorization
    if instance.status == "AUTHORIZED":
        if not hasattr(instance.booking, 'invoice'):
            booking = instance.booking
            
            Invoice.objects.create(
                booking=booking,
                payment=instance,
                sender=booking.sender,
                traveler=booking.traveler,
                package=booking.package,
                trip=booking.trip,
                reward=booking.reward_amount,
                platform_fee=booking.platform_fee,
                total_paid=instance.amount,
                currency=instance.currency,
                payment_method=instance.gateway,  # Uses Choice Enum directly
                transaction_id=getattr(instance, 'stripe_charge_id', ''),
                status=InvoiceStatus.ACTIVE
            )

    # 2. Trigger Status updates if a customer gets a partial/full platform refund
    elif instance.status == "REFUNDED" and hasattr(instance.booking, 'invoice'):
        invoice = instance.booking.invoice
        invoice.status = InvoiceStatus.REFUNDED
        invoice.save()

    elif instance.status == "FAILED" and hasattr(instance.booking, 'invoice'):
        invoice = instance.booking.invoice
        invoice.status = InvoiceStatus.CANCELLED
        invoice.save()