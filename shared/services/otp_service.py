import random
from django.utils import timezone
from datetime import timedelta

from apps.accounts.models import OTP

def generate_otp(length=6):
    """
    Generate a numeric OTP code.
    SaaS-safe simple implementation.
    """

    otp = "".join([str(random.randint(0, 9)) for _ in range(length)])
    return otp



def create_otp(user, email, purpose="signup", expiry_minutes=5):

    # invalidate previous OTPs (soft invalidate - SAFE)
    OTP.objects.filter(
        user=user,
        purpose=purpose,
        is_used=False
    ).update(is_used=True)

    code = generate_otp()

    otp_obj = OTP.objects.create(
        user=user,
        email=email,
        code=code,
        purpose=purpose,
        expires_at=timezone.now() + timedelta(minutes=expiry_minutes)
    )

    return otp_obj


def verify_otp(user, code, purpose="signup"):

    try:
        otp_obj = OTP.objects.get(
            user=user,
            code=code,
            purpose=purpose,
            is_used=False
        )
    except OTP.DoesNotExist:
        return False, "Invalid OTP"

    # expiry check
    if otp_obj.is_expired():
        return False, "OTP expired"

    # attempts limit (optional safety if you added attempts field)
    if hasattr(otp_obj, "attempts"):
        if otp_obj.attempts >= 5:
            return False, "Too many attempts"

    # mark as used
    otp_obj.is_used = True
    otp_obj.save()

    return True, "OTP verified"