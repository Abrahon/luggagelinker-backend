# from django.core.mail import send_mail
# from django.conf import settings


# def send_pickup_pin_email(user_email, booking, pickup_pin):
#     subject = "Your Booking is Confirmed - Pickup PIN"
    
#     message = f"""
# Your booking is confirmed.

# Booking ID: {booking.tracking_number}
# Pickup PIN: {pickup_pin}

# Give this PIN to the traveler during handover.
# """

#     send_mail(
#         subject,
#         message,
#         settings.DEFAULT_FROM_EMAIL,
#         [user_email],
#         fail_silently=False,
#     )


import logging
from django.core.mail import EmailMultiAlternatives
from django.conf import settings
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)

def send_pickup_pin_email(user_email, booking, pickup_pin):
    """
    Sends a high-converting, professional transactional HTML email containing 
    the security verification PIN to the booking sender.
    """
    subject = f"🔒 Delivery Confirmed - Pickup PIN for #{booking.tracking_number}"
    from_email = settings.DEFAULT_FROM_EMAIL
    to_emails = [user_email]

    # --- HTML Visual Component Template Layout ---
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Booking Confirmed</title>
    </head>
    <body style="margin: 0; padding: 0; background-color: #f4f6f8; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; -webkit-font-smoothing: antialiased;">
        <table border="0" cellpadding="0" cellspacing="0" width="100%" style="table-layout: fixed;">
            <tr>
                <td align="center" style="padding: 40px 0 20px 0; background-color: #f4f6f8;">
                    <table border="0" cellpadding="0" cellspacing="0" width="500" style="background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 10px rgba(0,0,0,0.05);">
                        <tr>
                            <td align="center" style="background-color: #1a73e8; padding: 30px 20px;">
                                <h1 style="color: #ffffff; margin: 0; font-size: 24px; font-weight: 600;">LuggageLinker</h1>
                            </td>
                        </tr>
                        <tr>
                            <td style="padding: 30px 40px;">
                                <p style="font-size: 16px; line-height: 24px; color: #3c4043; margin: 0 0 16px 0;">
                                    Hello,
                                </p>
                                <p style="font-size: 16px; line-height: 24px; color: #3c4043; margin: 0 0 24px 0;">
                                    Great news! Your escrow security payment was successfully cleared. Your delivery routing is officially locked and active.
                                </p>
                                
                                <table border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #f8f9fa; border-radius: 6px; margin-bottom: 24px;">
                                    <tr>
                                        <td style="padding: 16px;">
                                            <div style="font-size: 12px; text-transform: uppercase; color: #70757a; font-weight: 700; letter-spacing: 0.5px; margin-bottom: 4px;">Tracking Reference</div>
                                            <div style="font-size: 16px; color: #202124; font-weight: 600;">#{booking.tracking_number}</div>
                                        </td>
                                    </tr>
                                </table>

                                <div style="border: 2px dashed #1a73e8; background-color: #f1f3f9; border-radius: 8px; padding: 24px; text-align: center; margin-bottom: 24px;">
                                    <div style="font-size: 13px; font-weight: 700; color: #1a73e8; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;">Handover Security PIN</div>
                                    <div style="font-size: 36px; font-weight: 800; color: #202124; letter-spacing: 6px; font-family: monospace; line-height: 1;">{pickup_pin}</div>
                                </div>

                                <table border="0" cellpadding="0" cellspacing="0" width="100%" style="border-top: 1px solid #e8eaed; padding-top: 20px;">
                                    <tr>
                                        <td style="font-size: 13px; line-height: 20px; color: #70757a;">
                                            <strong style="color: #d93025;">⚠️ Important Security Rule:</strong> Do not share this PIN over messaging channels. Hand this PIN to your assigned traveler <strong>in person</strong> only when you are transferring the physical luggage context.
                                        </td>
                                    </tr>
                                </table>
                            </td>
                        </tr>
                        <tr>
                            <td align="center" style="background-color: #f8f9fa; padding: 20px; font-size: 12px; color: #70757a; border-top: 1px solid #e8eaed;">
                                This is an automated secure operational notification. Please do not reply directly to this mail.<br>
                                © 2026 LuggageLinker Logistics Framework.
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

    # --- Fallback Text Assembly Component ---
    # Automatically strip away nested markdown layouts for classic text readers
    text_content = strip_tags(html_content)

    try:
        # Construct the specialized MultiAlternatives distribution system
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=from_email,
            to=to_emails
        )
        # Bind the rich browser HTML rendering layer
        email.attach_alternative(html_content, "text/html")
        email.send(fail_silently=False)
        
        logger.info(f"Successfully sent pickup pin notification to {user_email} for booking {booking.id}")
    except Exception as e:
        # Capture integration faults silently in logs so crashing mail servers do not disrupt payment processing states
        logger.error(f"Failed to transmit Pickup PIN mail to user {user_email}: {str(e)}", exc_info=True)