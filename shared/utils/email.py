import logging
import random

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, BadHeaderError
from django.utils.html import strip_tags
from rest_framework_simplejwt.tokens import RefreshToken

logger = logging.getLogger(__name__)

def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)

    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }


def generate_otp():
    return str(random.randint(100000, 999999))


def send_otp_email(to_email, otp_code, name="User", sender_name=None):

    subject = "🔐 Your OTP Code for Verification"

    # Modern, Eye-Catching, Compact & Responsive HTML Template
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta name="x-apple-disable-message-reformatting">
        <title>{subject}</title>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
            
            body {{
                font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                -webkit-font-smoothing: antialiased;
                margin: 0;
                padding: 0;
                background-color: #f1f5f9;
            }}
            
            table {{
                border-collapse: collapse;
                mso-table-lspace: 0pt;
                mso-table-rspace: 0pt;
            }}

            @media screen and (max-width: 520px) {{
                .container {{
                    width: 100% !important;
                    padding: 8px !important;
                }}
                .card {{
                    padding: 24px 18px !important;
                    border-radius: 16px !important;
                }}
                .otp-box {{
                    font-size: 26px !important;
                    letter-spacing: 6px !important;
                    padding: 12px 18px !important;
                }}
            }}
        </style>
    </head>

    <body style="background-color: #f1f5f9; padding: 12px 0;">

        <!-- Hidden Preheader Text -->
        <div style="display:none;font-size:1px;color:#fff;max-height:0;max-width:0;opacity:0;overflow:hidden;">
            Your LuggageLinker verification code is {otp_code}. Valid for 5 minutes.
        </div>

        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color: #f1f5f9;">
            <tr>
                <td align="center">
                    <div class="container" style="max-width: 520px; width: 100%; margin: 0 auto; padding: 12px;">
                        
                        <!-- Main Card -->
                        <div class="card" style="background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 20px; padding: 32px 28px; text-align: center; box-shadow: 0 10px 15px -3px rgba(15, 23, 42, 0.05), 0 4px 6px -2px rgba(15, 23, 42, 0.025); overflow: hidden;">
                            
                            <!-- Header Logo Banner -->
                            <div style="background: linear-gradient(135deg, #4f46e5 0%, #3b82f6 100%); border-radius: 14px; padding: 16px; margin-bottom: 24px;">
                                <h1 style="margin: 0; font-size: 22px; font-weight: 800; color: #ffffff; letter-spacing: -0.5px;">
                                    🎒 Luggage<span style="color: #93c5fd;">Linker</span>
                                </h1>
                            </div>

                            <!-- Body Heading -->
                            <h2 style="margin: 0 0 8px 0; font-size: 18px; font-weight: 700; color: #0f172a;">
                                Verify Your Account 👋
                            </h2>
                            
                            <p style="margin: 0 0 20px 0; font-size: 14px; line-height: 1.5; color: #475569;">
                                Hello <strong>{name}</strong>, use the code below to finalize your action on <strong>LuggageLinker</strong>.
                            </p>

                            <!-- Modern OTP Box -->
                            <div style="margin-bottom: 20px;">
                                <div class="otp-box" style="
                                    display: inline-block;
                                    background: linear-gradient(180deg, #f5f3ff 0%, #ede9fe 100%);
                                    border: 1.5px dashed #6366f1;
                                    border-radius: 14px;
                                    padding: 14px 28px;
                                    font-size: 32px;
                                    font-weight: 800;
                                    letter-spacing: 8px;
                                    color: #4338ca;
                                    text-indent: 8px;
                                    box-shadow: inset 0 2px 4px 0 rgba(99, 102, 241, 0.06);
                                ">
                                    {otp_code}
                                </div>
                            </div>

                            <!-- Countdown Expiration Badge -->
                            <div style="margin-bottom: 20px;">
                                <span style="
                                    display: inline-block;
                                    background-color: #fff1f2;
                                    border: 1px solid #fecdd3;
                                    border-radius: 20px;
                                    padding: 4px 14px;
                                    font-size: 12px;
                                    font-weight: 600;
                                    color: #e11d48;
                                ">
                                    ⏳ Valid for <strong style="color: #be123c;">5 minutes</strong> only
                                </span>
                            </div>

                            <p style="margin: 0; font-size: 12px; color: #94a3b8; line-height: 1.4;">
                                Didn't request this code? You can safely ignore this email.
                            </p>

                        </div>

                        <!-- Footer -->
                        <div style="padding: 20px 12px 0 12px; text-align: center;">
                            <p style="margin: 0 0 4px 0; font-size: 12px; font-weight: 600; color: #64748b;">
                                © 2026 LuggageLinker
                            </p>
                            <p style="margin: 0 0 8px 0; font-size: 11px; color: #94a3b8;">
                                Secure Travel &bull; Trusted Delivery &bull; Global Community
                            </p>
                            <p style="margin: 0; font-size: 10px; color: #cbd5e1;">
                                Automated message. Please do not reply directly.
                            </p>
                        </div>

                    </div>
                </td>
            </tr>
        </table>

    </body>
    </html>
    """

    plain_text = strip_tags(html_content)

    from email.utils import formataddr
    from_email = formataddr(("Luggage Linker", settings.EMAIL_HOST_USER))

    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=plain_text,
            # from_email=f"Luggage Linker <{settings.EMAIL_HOST_USER}>".replace('"', ''),
            from_email=str(from_email),
            to=[to_email],
            reply_to=[settings.DEFAULT_FROM_EMAIL]
        )

        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)

        logger.info("OTP email sent to %s", to_email)
        return True

    except BadHeaderError as exc:
        logger.exception("Bad header error sending OTP to %s: %s", to_email, exc)
        return False

    except Exception as exc:
        logger.exception("Unexpected error sending OTP to %s: %s", to_email, exc)
        return False