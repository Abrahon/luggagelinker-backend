import re
from datetime import date
from rest_framework import serializers
from apps.profiles.models import Profile, GenderChoices


class ProfileSerializer(serializers.ModelSerializer):
    # Read-only statistical fields to protect integrity against user tampering
    average_rating = serializers.DecimalField(read_only=True, max_digits=3, decimal_places=2)
    total_reviews = serializers.IntegerField(read_only=True)
    
    # Optional fields missing from your model snippet but referenced in your serializer (e.g. if updated asynchronously via signals)
    # If these exist on your real model, keep them here. If they don't, remove them from fields.
    completed_deliveries = serializers.IntegerField(read_only=True, required=False)
    cancelled_deliveries = serializers.IntegerField(read_only=True, required=False)
    total_earnings = serializers.DecimalField(read_only=True, required=False, max_digits=10, decimal_places=2)

    class Meta:
        model = Profile
        fields = [
            "id",
            "first_name",
            "last_name",
            "gender",  # Added missing field
            "phone",
            "country",
            "city",
            "address",
            "postal_code",
            "date_of_birth",
            "profile_picture",
            "bio",
            "average_rating",
            "total_reviews",
            "completed_deliveries",
            "cancelled_deliveries",
            "total_earnings",
            "created_at",
            "updated_at",
        ]
        read_only_fields = (
            "id",
            "created_at",
            "updated_at",
        )
        extra_kwargs = {
            "first_name": {
                "required": True,
                "allow_blank": False,
                "error_messages": {
                    "required": "First name is required.",
                    "blank": "First name cannot be empty.",
                },
            },
            "last_name": {
                "required": True,
                "allow_blank": False,
                "error_messages": {
                    "required": "Last name is required.",
                    "blank": "Last name cannot be empty.",
                },
            },
            "phone": {
                "required": True,
                "allow_blank": False,
                "error_messages": {
                    "required": "Phone number is required.",
                    "blank": "Phone number cannot be empty.",
                },
            },
            "country": {
                "required": True,
                "allow_blank": False,
                "error_messages": {
                    "required": "Country is required.",
                    "blank": "Country cannot be empty.",
                },
            },
            "city": {
                "required": True,
                "allow_blank": False,
                "error_messages": {
                    "required": "City is required.",
                    "blank": "City cannot be empty.",
                },
            },
            "gender": {
                "required": False,
                "allow_blank": True,
            },
            "address": {
                "required": False,
                "allow_blank": True,
            },
            "postal_code": {
                "required": False,
                "allow_blank": True,
            },
            "date_of_birth": {
                "required": True,
                "allow_null": False,
                "error_messages": {
                    "required": "Date of birth is required.",
                    "null": "Date of birth cannot be null.",
                },
            },
            "bio": {
                "required": False,
                "allow_blank": True,
            },
            "profile_picture": {
                "required": False,
                "allow_null": True,
            },
        }

    # -----------------------------------
    # Individual Field Validators
    # -----------------------------------

    def validate_first_name(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("First name must contain at least 2 characters.")
        if not re.fullmatch(r"[A-Za-z ]+", value):
            raise serializers.ValidationError("First name may contain only letters and spaces.")
        return value.title()

    def validate_last_name(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("Last name must contain at least 2 characters.")
        if not re.fullmatch(r"[A-Za-z ]+", value):
            raise serializers.ValidationError("Last name may contain only letters and spaces.")
        return value.title()

    def validate_phone(self, value):
        value = value.strip()
        if not re.fullmatch(r"^\+?[0-9]{8,15}$", value):
            raise serializers.ValidationError("Enter a valid phone number (e.g., +1234567890).")

        # Safely extract user from request context
        request = self.context.get("request")
        if request and request.user and request.user.is_authenticated:
            exists = Profile.objects.exclude(user=request.user).filter(phone=value).exists()
            if exists:
                raise serializers.ValidationError("Phone number already exists.")
        return value

    def validate_country(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("Country name is too short.")
        return value.title()

    def validate_city(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("City name is too short.")
        return value.title()

    def validate_postal_code(self, value):
        if not value:
            return value
        value = value.strip()
        if len(value) > 20:
            raise serializers.ValidationError("Postal code is too long.")
        return value

    def validate_date_of_birth(self, value):
        today = date.today()
        if value > today:
            raise serializers.ValidationError("Date of birth cannot be in the future.")

        age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))

        if age < 18:
            raise serializers.ValidationError("You must be at least 18 years old.")
        if age > 120:
            raise serializers.ValidationError("Please enter a valid date of birth.")
        return value

    def validate_bio(self, value):
        if value and len(value) > 500:
            raise serializers.ValidationError("Bio cannot exceed 500 characters.")
        return value.strip() if value else value