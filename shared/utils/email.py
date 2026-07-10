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

    # Modern, Sleek, Mobile-Responsive HTML Template
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta name="x-apple-disable-message-reformatting">
        <title>{subject}</title>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');
            
            body {{
                font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                -webkit-font-smoothing: antialiased;
                -webkit-text-size-adjust: 100%;
                -ms-text-size-adjust: 100%;
                margin: 0;
                padding: 0;
                background-color: #f8fafc;
            }}
            
            table {{
                border-collapse: collapse;
                mso-table-lspace: 0pt;
                mso-table-rspace: 0pt;
            }}

            @media screen and (max-width: 620px) {{
                .container {{
                    width: 100% !important;
                    padding: 10px !important;
                }}
                .card {{
                    padding: 32px 20px !important;
                    border-radius: 16px !important;
                }}
                .otp-box {{
                    font-size: 28px !important;
                    letter-spacing: 6px !important;
                    padding: 14px 24px !important;
                }}
            }}
        </style>
    </head>

    <body style="background-color: #f8fafc; padding: 20px 0;">

        <div style="display:none;font-size:1px;color:#fff;max-height:0;max-width:0;opacity:0;overflow:hidden;">
            Your LuggageLinker verification code is {otp_code}. Valid for 5 minutes.
        </div>

        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color: #f8fafc;">
            <tr>
                <td align="center">
                    <div class="container" style="max-width: 600px; width: 100%; margin: 0 auto; padding: 20px;">
                        
                        <div class="card" style="background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 24px; padding: 48px; text-align: center; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);">
                            
                            <div style="margin-bottom: 32px;">
                                <span style="font-size: 40px; display: inline-block; margin-bottom: 12px;">🎒</span>
                                <h1 style="margin: 0; font-size: 24px; font-weight: 700; color: #0f172a; letter-spacing: -0.5px;">
                                    Luggage<span style="color: #4f46e5;">Linker</span>
                                </h1>
                            </div>

                            <div style="height: 1px; background-color: #f1f5f9; margin-bottom: 32px;"></div>

                            <h2 style="margin: 0 0 16px 0; font-size: 20px; font-weight: 600; color: #1e293b;">
                                Hello {name} 👋
                            </h2>
                            
                            <p style="margin: 0 0 32px 0; font-size: 15px; line-height: 1.6; color: #64748b;">
                                Thanks for joining <strong>LuggageLinker</strong>! Please use the secure verification code below to finalize your account setup.
                            </p>

                            <div style="margin-bottom: 32px;">
                                <div class="otp-box" style="
                                    display: inline-block;
                                    background: #f5f3ff;
                                    border: 1px solid #ddd6fe;
                                    border-radius: 16px;
                                    padding: 16px 40px;
                                    font-size: 36px;
                                    font-weight: 700;
                                    letter-spacing: 10px;
                                    color: #4f46e5;
                                    text-indent: 10px; /* Aligns trailing letter-spacing perfectly */
                                ">
                                    {otp_code}
                                </div>
                            </div>

                            <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center" style="margin-bottom: 32px; background-color: #fff1f2; border-radius: 30px; padding: 6px 16px;">
                                <tr>
                                    <td style="font-size: 13px; font-weight: 500; color: #e11d48;">
                                        ⏳ Code expires in <span style="font-weight: 700;">5 minutes</span>
                                    </td>
                                </tr>
                            </table>

                            <p style="margin: 0; font-size: 13px; color: #94a3b8; line-height: 1.5;">
                                If you didn't request this code, you can safely ignore this email.
                            </p>

                        </div>

                        <div style="padding: 32px 20px 0 20px; text-align: center;">
                            <p style="margin: 0 0 8px 0; font-size: 13px; font-weight: 500; color: #64748b;">
                                © 2026 LuggageLinker
                            </p>
                            <p style="margin: 0 0 16px 0; font-size: 12px; color: #94a3b8; letter-spacing: 0.5px;">
                                Secure Travel &bull; Trusted Delivery &bull; Global Community
                            </p>
                            <p style="margin: 0; font-size: 11px; color: #cbd5e1;">
                                This is an automated security message. Please do not reply.
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

    from_email = f"{sender_name or 'User'} <{settings.EMAIL_HOST_USER}>"

    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=plain_text,
            from_email=from_email,
            to=[to_email],
            reply_to=[settings.DEFAULT_FROM_EMAIL]
        )

        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)

        logger.info("OTP email sent to %s", to_email)
        return True

    except (BadHeaderError,) as exc:
        logger.exception("Bad header error sending OTP to %s: %s", to_email, exc)
        return False

    except Exception as exc:
        logger.exception("Unexpected error sending OTP to %s: %s", to_email, exc)
        return False