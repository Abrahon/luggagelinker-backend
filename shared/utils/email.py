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

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
    </head>

    <body style="margin:0;padding:40px 20px;background:#f4f7fb;font-family:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;">

        <!-- Email Preheader -->
        <div style="display:none;font-size:1px;color:#fff;max-height:0;max-width:0;opacity:0;overflow:hidden;">
            Your LuggageLinker verification code is {otp_code}. Valid for 5 minutes.
        </div>

        <div style="max-width:600px;margin:0 auto;background:#ffffff;border:1px solid #e5e7eb;border-radius:16px;overflow:hidden;box-shadow:0 8px 30px rgba(0,0,0,.08);">

            <!-- HEADER -->
            <div style="background:linear-gradient(135deg,#4f46e5,#6366f1);padding:32px;text-align:center;color:#ffffff;">

                <div style="font-size:42px;margin-bottom:10px;">🔐</div>

                <h1 style="margin:0;font-size:24px;font-weight:700;">
                    LuggageLinker
                </h1>

            <p style="margin:8px 0 0;font-size:14px;font-weight:500;color:#FDE68A;">
                Secure Email Verification
            </p>

            </div>

            <!-- BODY -->
            <div style="padding:40px;text-align:center;">

                <h2 style="margin-top:0;color:#111827;font-size:22px;">
                    Hello {name} 👋
                </h2>

                <p style="margin:18px 0;color:#6b7280;font-size:15px;line-height:1.8;">
                    Welcome to <strong>LuggageLinker</strong>.<br>
                    Use the verification code below to complete your account registration.
                </p>

                <!-- OTP BOX -->
                <div style="margin:35px 0;">

                    <div style="
                        display:inline-block;
                        background:#eef2ff;
                        border:2px dashed #6366f1;
                        border-radius:14px;
                        padding:18px 38px;
                        font-size:34px;
                        font-weight:700;
                        letter-spacing:8px;
                        color:#4338ca;
                        user-select:all;
                    ">
                        {otp_code}
                    </div>

                </div>

                <p style="font-size:15px;color:#374151;">
                    ⏳ This verification code expires in
                    <strong style="color:#dc2626;">5 minutes</strong>.
                </p>

            <!-- FOOTER -->
            <div style="background:#f9fafb;padding:24px;text-align:center;border-top:1px solid #e5e7eb;">

                <p style="margin:0;font-size:13px;color:#9ca3af;">
                    © 2026 LuggageLinker
                </p>

                <p style="margin:8px 0 0;font-size:12px;color:#9ca3af;">
                    Secure Travel • Trusted Delivery • Global Community
                </p>

                <p style="margin:12px 0 0;font-size:11px;color:#c0c4cc;">
                    This is an automated email. Please do not reply.
                </p>

            </div>

        </div>

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