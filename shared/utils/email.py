import logging
import random

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, BadHeaderError
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def generate_otp():
    return str(random.randint(100000, 999999))


def send_otp_email(to_email, otp_code, name="User", sender_name=None):

    subject = "🔐 Your OTP Code for Verification"

    html_content = f"""
    <div style="font-family:Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
                max-width:600px;margin:0 auto;background:#ffffff;border:1px solid #eaeaea;
                border-radius:12px;overflow:hidden;">

        <!-- HEADER -->
        <div style="background:linear-gradient(135deg,#4f46e5,#6366f1);
                    padding:24px;text-align:center;color:white;">
            <h1 style="margin:0;font-size:20px;">LuggageLinker Security</h1>
            <p style="margin:6px 0 0;font-size:13px;opacity:0.9;">Email Verification OTP</p>
        </div>

        <!-- BODY -->
        <div style="padding:32px;text-align:center;">

            <h2 style="color:#111827;margin-bottom:10px;font-size:18px;">
                Hi {name} 👋
            </h2>

            <p style="color:#6b7280;font-size:14px;line-height:1.6;">
                Use the verification code below to complete your signup.
                This code is valid for <strong>5 minutes</strong>.
            </p>

            <!-- OTP BOX -->
            <div style="margin:28px 0;">
                <div style="display:inline-block;
                            background:#f3f4f6;
                            border:1px dashed #d1d5db;
                            padding:16px 28px;
                            font-size:28px;
                            letter-spacing:6px;
                            font-weight:700;
                            color:#111827;
                            border-radius:10px;">
                    {otp_code}
                </div>
            </div>

            <p style="font-size:12px;color:#9ca3af;">
                Do not share this code with anyone. LuggageLinker will never ask for it.
            </p>

        </div>

        <!-- FOOTER -->
        <div style="background:#f9fafb;padding:16px;text-align:center;">
            <p style="font-size:11px;color:#9ca3af;margin:0;">
                © LuggageLinker Security Team • If you didn’t request this, ignore this email.
            </p>
        </div>

    </div>
    """

    plain_text = strip_tags(html_content)

    from_email = f"{sender_name or 'System'} <{settings.EMAIL_HOST_USER}>"

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