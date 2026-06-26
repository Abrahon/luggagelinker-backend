from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from shared.constants.roles import UserRole
from rest_framework import serializers
from apps.accounts.models import User
from apps.accounts.models import OTP
from django.contrib.auth.password_validation import validate_password
from shared.services.otp_service import generate_otp, send_otp_email
from django.contrib.auth import authenticate

User = get_user_model()

class SignupSerializer(serializers.Serializer):

    email = serializers.EmailField(
        error_messages={
            "invalid": "Enter a valid email address.",
            "required": "Email field is required.",
            "blank": "Email cannot be empty.",
        }
    )



    password = serializers.CharField(
        write_only=True,
        min_length=8,
        error_messages={
            "min_length": "Password must be at least 8 characters long.",
            "blank": "Password field cannot be empty.",
            "required": "Password is required.",
        },
    )

    confirm_password = serializers.CharField(
        write_only=True,
        min_length=8,
        error_messages={
            "min_length": "Confirm password must be at least 8 characters long.",
            "blank": "Confirm password field cannot be empty.",
            "required": "Confirm password is required.",
        },
    )

    role = serializers.ChoiceField(
        choices=UserRole.choices,
        error_messages={
            "required": "Role field is required.",
            "invalid_choice": "Invalid role. Choose a valid role.",
        }
    )



# send opt serializers
# ---------------------------------
# SEND OTP SERIALIZER
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

        self.context["user"] = user
        return value

    def create(self, validated_data):
        user = self.context["user"]

        # remove previous OTPs for clean latest-flow
        OTP.objects.filter(user=user).delete()

        code = generate_otp()
        OTP.objects.create(user=user, email=user.email, code=code)

        send_otp_email(user.email, code, name=user.name)
        return user


# updated views
from rest_framework import serializers
from django.contrib.auth import get_user_model

User = get_user_model()


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs.get("email", "").strip().lower()
        password = attrs.get("password")

        # Check if user exists
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({
                "email": ["No account found with this email address."]
            })

        # Check password
        if not user.check_password(password):
            raise serializers.ValidationError({
                "password": ["Incorrect password."]
            })

        # Check if account is active / verified
        if not user.is_active:
            raise serializers.ValidationError({
                "email": ["Please verify your email before logging in."]
            })

        attrs["user"] = user
        return attrs