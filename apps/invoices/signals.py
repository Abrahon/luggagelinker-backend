from django.db.models.signals import post_save
from django.dispatch import receiver
from apps.payment.models import BookingPayment,BookingPaymentStatus
from apps.invoices.models import Invoice, InvoiceStatus

@receiver(post_save, sender=BookingPayment)
def handle_payment_status_change(sender, instance, created, **kwargs):

    if (
        instance.status == BookingPaymentStatus.AUTHORIZED
        and not hasattr(instance.booking, "invoice")
    ):

        booking = instance.booking

        Invoice.objects.create(
            booking=booking,
            payment=instance,
            sender=booking.sender,
            traveler=booking.traveler,
            package=booking.package,
            trip=booking.trip,
            reward=booking.agreed_reward,
            platform_fee=instance.platform_fee,
            total_paid=instance.amount + instance.platform_fee,
            currency=instance.currency,
            payment_method=instance.gateway,
            transaction_id=instance.transaction_id or "",
            status=InvoiceStatus.ACTIVE,
        )

    elif (
        instance.status == BookingPaymentStatus.REFUNDED
        and hasattr(instance.booking, "invoice")
    ):
        invoice = instance.booking.invoice
        invoice.status = InvoiceStatus.REFUNDED
        invoice.save(update_fields=["status"])

    elif (
        instance.status == BookingPaymentStatus.FAILED
        and hasattr(instance.booking, "invoice")
    ):
        invoice = instance.booking.invoice
        invoice.status = InvoiceStatus.CANCELLED
        invoice.save(update_fields=["status"])