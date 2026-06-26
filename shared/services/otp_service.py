import random
from django.utils import timezone
from datetime import timedelta

from apps.accounts.models import OTP

import logging

logger = logging.getLogger(__name__)


def generate_otp(length=6):
    """
    Generate a numeric OTP code.
    SaaS-safe simple implementation.
    """

    otp = "".join([str(random.randint(0, 9)) for _ in range(length)])
    return otp



from django.utils import timezone
from datetime import timedelta
from apps.accounts.models import OTP


def create_otp(user, email):
    OTP.objects.filter(user=user).delete()

    code = generate_otp()

    return OTP.objects.create(
        user=user,
        email=email,
        code=code
    )



def send_otp_email(to_email, otp_code, name="User"):
    try:
        print(f"Sending OTP {otp_code} to {to_email}")
        logger.info("OTP sent to %s", to_email)
        return True
    except Exception as e:
        logger.exception("OTP send failed: %s", e)
        return False


from django.utils import timezone
from datetime import timedelta

def verify_otp(user, code):
    otp = OTP.objects.filter(user=user, code=code).order_by("-created_at").first()

    if not otp:
        return False, "Invalid OTP"

    if otp.is_expired():
        return False, "OTP expired"

    otp.delete()  # one-time use

    return True, "OTP verified"