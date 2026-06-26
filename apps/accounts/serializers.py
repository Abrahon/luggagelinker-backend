from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from shared.constants.roles import UserRole
from rest_framework import serializers
from apps.accounts.models import User
from apps.accounts.models import OTP
from shared.services.otp_service import generate_otp, send_otp_email

User = get_user_model()

class SignupSerializer(serializers.ModelSerializer):

    password = serializers.CharField(
        write_only=True,
        min_length=8,
        error_messages={
            "required": "Password is required.",
            "blank": "Password cannot be empty.",
            "min_length": "Password must be at least 8 characters long.",
        }
    )

    confirm_password = serializers.CharField(
        write_only=True,
        min_length=8,
        error_messages={
            "required": "Confirm password is required.",
            "blank": "Confirm password cannot be empty.",
        }
    )

    class Meta:
        model = User
        fields = [
            "email",
            "role",
            "password",
            "confirm_password",
        ]

        extra_kwargs = {
            "email": {
                "error_messages": {
                    "required": "Email is required.",
                    "blank": "Email cannot be empty.",
                    "invalid": "Enter a valid email address.",
                }
            },
            "role": {
                "error_messages": {
                    "required": "Role is required.",
                    "invalid_choice": "Invalid role selected.",
                }
            }
        }

    # =========================
    # 🔥 FIELD VALIDATION
    # =========================
    def validate(self, attrs):

        email = attrs.get("email")

        # 1. password match check
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({
                "confirm_password": "Passwords do not match."
            })

        # 2. strong password validation
        try:
            validate_password(attrs["password"])
        except ValidationError as e:
            raise serializers.ValidationError({
                "password": list(e.messages)
            })

        # 3. duplicate email check (SaaS safe)
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError({
                "email": "User with this email already exists."
            })

        return attrs

    # =========================
    # 🔥 CREATE USER LOGIC
    # =========================
    def create(self, validated_data):

        validated_data.pop("confirm_password")

        password = validated_data.pop("password")

        user = User.objects.create_user(
            email=validated_data["email"],
            role=validated_data.get("role", UserRole.SENDER),
        )

        user.set_password(password)
        user.save()

        return user


# send opt serializers
# ---------------------------------
# SEND OTP SERIALIZER
# ---------------------------------
class SendOTPSerializer(serializers.Serializer):

    email = serializers.EmailField(
        error_messages={
            "required": "Email is required.",
            "blank": "Email cannot be empty.",
            "invalid": "Enter a valid email address.",
        }
    )

    def validate_email(self, value):
        value = value.strip().lower()

        user = User.objects.filter(email__iexact=value).first()

        if not user:
            raise serializers.ValidationError("User with this email does not exist.")

        # optional: prevent spam resend
        from django.utils import timezone
        from datetime import timedelta

        recent_otp = OTP.objects.filter(
            email=value
        ).order_by("-created_at").first()

        if recent_otp and (timezone.now() - recent_otp.created_at).seconds < 60:
            raise serializers.ValidationError("Please wait before requesting another OTP.")

        self.context["user"] = user
        return value

    def create(self, validated_data):
        user = self.context["user"]

        # ----------------------------
        # CLEAN OLD OTPs
        # ----------------------------
        OTP.objects.filter(
            user=user,
            email=user.email
        ).delete()

        # ----------------------------
        # GENERATE OTP
        # ----------------------------
        code = generate_otp()

        OTP.objects.create(
            user=user,
            email=user.email,
            code=code,
            purpose="email_verification"
        )

        # ----------------------------
        # SEND EMAIL (SAFE CALL)
        # ----------------------------
        try:
            send_otp_email(
                to_email=user.email,
                otp_code=code,
                name=user.email  # fallback safe
            )
        except Exception:
            raise serializers.ValidationError("Failed to send OTP email. Try again later.")

        return user