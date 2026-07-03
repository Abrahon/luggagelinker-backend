from django.core.mail import send_mail
from django.conf import settings


def send_pickup_pin_email(user_email, booking, pickup_pin):
    subject = "Your Booking is Confirmed - Pickup PIN"
    
    message = f"""
Your booking is confirmed.

Booking ID: {booking.tracking_number}
Pickup PIN: {pickup_pin}

Give this PIN to the traveler during handover.
"""

    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [user_email],
        fail_silently=False,
    )