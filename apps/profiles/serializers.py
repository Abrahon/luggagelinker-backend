import re

from rest_framework import serializers

from apps.accounts.models import Profile


class ProfileSerializer(serializers.ModelSerializer):

    class Meta:
        model = Profile

        fields = [
            "id",
            "first_name",
            "last_name",
            "phone",
            "country",
            "city",
            "address",
            "postal_code",
            "profile_picture",
            "bio",
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
                "error_messages": {
                    "required": "First name is required.",
                    "blank": "First name cannot be empty.",
                    "max_length": "First name is too long.",
                },
            },

            "last_name": {
                "required": True,
                "error_messages": {
                    "required": "Last name is required.",
                    "blank": "Last name cannot be empty.",
                    "max_length": "Last name is too long.",
                },
            },

            "phone": {
                "required": True,
                "error_messages": {
                    "required": "Phone number is required.",
                    "blank": "Phone number cannot be empty.",
                },
            },

            "country": {
                "required": True,
                "error_messages": {
                    "required": "Country is required.",
                    "blank": "Country cannot be empty.",
                },
            },

            "city": {
                "required": True,
                "error_messages": {
                    "required": "City is required.",
                    "blank": "City cannot be empty.",
                },
            },

            "address": {
                "required": False,
                "allow_blank": True,
            },

            "postal_code": {
                "required": False,
                "allow_blank": True,
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
    # First Name
    # -----------------------------------

    def validate_first_name(self, value):

        value = value.strip()

        if len(value) < 2:
            raise serializers.ValidationError(
                "First name must contain at least 2 characters."
            )

        if not re.fullmatch(r"[A-Za-z ]+", value):
            raise serializers.ValidationError(
                "First name may contain only letters and spaces."
            )

        return value.title()

    # -----------------------------------
    # Last Name
    # -----------------------------------

    def validate_last_name(self, value):

        value = value.strip()

        if len(value) < 2:
            raise serializers.ValidationError(
                "Last name must contain at least 2 characters."
            )

        if not re.fullmatch(r"[A-Za-z ]+", value):
            raise serializers.ValidationError(
                "Last name may contain only letters and spaces."
            )

        return value.title()

    # -----------------------------------
    # Phone
    # -----------------------------------

    def validate_phone(self, value):

        value = value.strip()

        if not re.fullmatch(r"^\+?[0-9]{8,15}$", value):
            raise serializers.ValidationError(
                "Enter a valid phone number."
            )

        user = self.context["request"].user

        exists = (
            Profile.objects
            .exclude(user=user)
            .filter(phone=value)
            .exists()
        )

        if exists:
            raise serializers.ValidationError(
                "Phone number already exists."
            )

        return value

    # -----------------------------------
    # Country
    # -----------------------------------

    def validate_country(self, value):

        value = value.strip()

        if len(value) < 2:
            raise serializers.ValidationError(
                "Country name is too short."
            )

        return value.title()

    # -----------------------------------
    # City
    # -----------------------------------

    def validate_city(self, value):

        value = value.strip()

        if len(value) < 2:
            raise serializers.ValidationError(
                "City name is too short."
            )

        return value.title()

    # -----------------------------------
    # Postal Code
    # -----------------------------------

    def validate_postal_code(self, value):

        if not value:
            return value

        value = value.strip()

        if len(value) > 20:
            raise serializers.ValidationError(
                "Postal code is too long."
            )

        return value

    # -----------------------------------
    # Bio
    # -----------------------------------

    def validate_bio(self, value):

        if value and len(value) > 500:
            raise serializers.ValidationError(
                "Bio cannot exceed 500 characters."
            )

        return value.strip()

    # -----------------------------------
    # Update
    # -----------------------------------

    def update(self, instance, validated_data):

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()

        return instance