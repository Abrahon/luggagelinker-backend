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
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError

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
    email = serializers.EmailField(
        required=True,
        allow_blank=False,
        error_messages={
            "required": "Email address is required.",
            "blank": "Email address is required.",
            "invalid": "Please enter a valid email address.",
        },
    )

    password = serializers.CharField(
        required=True,
        write_only=True,
        allow_blank=False,
        trim_whitespace=False,
        error_messages={
            "required": "Password is required.",
            "blank": "Password is required.",
        },
    )

    def validate(self, attrs):
        email = attrs.get("email", "").strip().lower()
        password = attrs.get("password")

        # =====================================================
        # 1. EMAIL VALIDATION
        # =====================================================

        if not email:
            raise serializers.ValidationError({
                "email": {
                    "code": "email_required",
                    "message": "Email address is required.",
                }
            })

        # =====================================================
        # 2. PASSWORD VALIDATION
        # =====================================================

        if not password:
            raise serializers.ValidationError({
                "password": {
                    "code": "password_required",
                    "message": "Password is required.",
                }
            })

        # =====================================================
        # 3. FIND USER
        # =====================================================

        try:
            user = User.objects.get(email__iexact=email)

        except User.DoesNotExist:
            raise serializers.ValidationError({
                "email": {
                    "code": "account_not_found",
                    "message": "No account found with this email address.",
                }
            })

        # =====================================================
        # 4. CHECK PASSWORD
        # =====================================================

        if not user.check_password(password):
            raise serializers.ValidationError({
                "password": {
                    "code": "invalid_password",
                    "message": "Incorrect password.",
                }
            })

        # =====================================================
        # 5. CHECK ACTIVE STATUS
        # =====================================================

        if not user.is_active:
            raise serializers.ValidationError({
                "email": {
                    "code": "account_inactive",
                    "message": "Your account is inactive.",
                }
            })

        # =====================================================
        # 6. EMAIL VERIFICATION
        # =====================================================

        # Only use this if your User model actually has
        # an email verification field.
        if hasattr(user, "is_email_verified"):
            if not user.is_email_verified:
                raise serializers.ValidationError({
                    "email": {
                        "code": "email_not_verified",
                        "message": "Please verify your email before logging in.",
                    }
                })

        # =====================================================
        # 7. ACCOUNT SUSPENSION
        # =====================================================

        # Only applies if your User model has is_suspended.
        if hasattr(user, "is_suspended"):
            if user.is_suspended:
                raise serializers.ValidationError({
                    "email": {
                        "code": "account_suspended",
                        "message": "Your account has been suspended.",
                    }
                })

        # =====================================================
        # 8. ACCOUNT LOCK
        # =====================================================

        # Only applies if your User model has is_locked.
        if hasattr(user, "is_locked"):
            if user.is_locked:
                raise serializers.ValidationError({
                    "email": {
                        "code": "account_locked",
                        "message": "Your account is temporarily locked.",
                    }
                })

        # =====================================================
        # LOGIN SUCCESS
        # =====================================================

        attrs["user"] = user

        return attrs

# resend otp
# ---------------------------------
# RESEND OTP SERIALIZER
# ---------------------------------
class ResendOTPSerializer(serializers.Serializer):
    email = serializers.EmailField(
        error_messages={
            "required": "Email is required.",
            "blank": "Email cannot be empty.",
            "invalid": "Enter a valid email address.",
        }
    )

    def validate_email(self, value):
        value = value.strip().lower()
        return value




# ---------------------------------
# VERIFY OTP SERIALIZER (FORGOT PASSWORD)
# ---------------------------------
class VerifyOTPForgetSerializer(serializers.Serializer):
    email = serializers.EmailField(
        error_messages={
            "required": "Email is required.",
            "blank": "Email cannot be empty.",
            "invalid": "Enter a valid email address.",
        }
    )
    code = serializers.CharField(
        max_length=6,
        min_length=6,
        error_messages={
            "required": "OTP code is required.",
            "blank": "OTP code cannot be empty.",
        }
    )

    def validate(self, attrs):
        email = attrs.get("email", "").strip().lower()
        code = attrs.get("code", "").strip()

        user = User.objects.filter(email__iexact=email).first()
        if not user:
            raise serializers.ValidationError({"detail": "User not found."})

        otp_obj = OTP.objects.filter(user=user, code=code).order_by("-created_at").first()

        if not otp_obj:
            raise serializers.ValidationError({"detail": "Invalid OTP."})

        if otp_obj.is_expired():
            raise serializers.ValidationError({"detail": "OTP has expired."})

        attrs["user"] = user
        attrs["otp_instance"] = otp_obj
        attrs["email"] = email
        return attrs





class ResetPasswordSerializer(serializers.Serializer):
    reset_token = serializers.CharField(required=True)
    new_password = serializers.CharField(
        write_only=True,
        required=True,
        min_length=8,
        validators=[validate_password]
    )
    confirm_password = serializers.CharField(
        write_only=True,
        required=True,
        min_length=8
    )

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": "Passwords do not match."}
            )
        return attrs



# change passowrd\

# ---------------------------------
# CHANGE PASSWORD SERIALIZER
# ---------------------------------
class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(
        write_only=True,
        error_messages={
            "required": "Old password is required.",
            "blank": "Old password cannot be empty.",
        }
    )
    new_password = serializers.CharField(
        write_only=True,
        min_length=8,
        error_messages={
            "required": "New password is required.",
            "blank": "New password cannot be empty.",
            "min_length": "Password must be at least 8 characters long.",
        }
    )
    confirm_password = serializers.CharField(
        write_only=True,
        min_length=8,
        error_messages={
            "required": "Confirm password is required.",
            "blank": "Confirm password cannot be empty.",
            "min_length": "Confirm password must be at least 8 characters long.",
        }
    )

    def validate(self, attrs):
        request = self.context.get("request")
        user = request.user

        old_password = attrs.get("old_password")
        new_password = attrs.get("new_password")
        confirm_password = attrs.get("confirm_password")

        if not user.check_password(old_password):
            raise serializers.ValidationError(
                {"old_password": "Old password is incorrect."}
            )

        if new_password != confirm_password:
            raise serializers.ValidationError(
                {"confirm_password": "Passwords do not match."}
            )

        try:
            password_validation.validate_password(new_password, user=user)
        except DjangoValidationError as e:
            raise serializers.ValidationError({"new_password": list(e.messages)})

        return attrs
    

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user




from rest_framework import serializers
from django.contrib.auth import get_user_model

User = get_user_model()


class AdminUserListSerializer(serializers.ModelSerializer):
    """Serializer for listing users in the admin panel."""

    name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "name",
            "email",
            "role",
            "is_active",
            "is_online",
            "last_seen",
            "is_staff",
            "is_verified",
            "date_joined",
            "updated_at",
        ]
        read_only_fields = fields

    def get_name(self, obj):
        # Uses the `full_name` property from your Profile model directly
        if hasattr(obj, "profile") and obj.profile:
            return obj.profile.full_name
        return ""

class UserStatusUpdateSerializer(serializers.Serializer):
    """
    Optional serializer to validate responses or reason when updating status.
    """

    is_active = serializers.BooleanField(read_only=True)
    message = serializers.CharField(read_only=True)



class MonthlyUserGrowthSerializer(serializers.Serializer):
    """Serializer for monthly user growth data across all time."""
    year = serializers.IntegerField()
    month = serializers.IntegerField()
    month_name = serializers.CharField()
    total_users = serializers.IntegerField()
    active_users = serializers.IntegerField()




class UserRoleDistributionSerializer(serializers.Serializer):
    """Serializer to represent user counts and percentages by role."""
    total_users = serializers.IntegerField()
    roles = serializers.DictField(
        child=serializers.DictField(child=serializers.FloatField())
    )




class MonthlyRevenueItemSerializer(serializers.Serializer):
    """Serializer for monthly revenue aggregation data."""

    year = serializers.IntegerField()
    month = serializers.IntegerField()
    month_name = serializers.CharField()
    total_revenue = serializers.FloatField()
    platform_fee_revenue = serializers.FloatField()
    transaction_count = serializers.IntegerField()
    paying_users = serializers.IntegerField()





class UserBriefSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    profile_picture = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "full_name",
            "profile_picture",
        ]

    def get_full_name(self, obj):
        profile = getattr(obj, "profile", None)

        if profile:
            return " ".join(
                filter(
                    None,
                    [
                        profile.first_name,
                        profile.last_name,
                    ],
                )
            )

        return obj.email

    def get_profile_picture(self, obj):
        profile = getattr(obj, "profile", None)

        if profile and profile.profile_picture:
            return profile.profile_picture.url

        return None