from decimal import Decimal

from rest_framework import serializers

from .models import Package, PackageImage

from rest_framework import serializers

from .models import PackageImage


# ===========================================================
# PACKAGE IMAGE
# ===========================================================

class PackageImageSerializer(serializers.ModelSerializer):

    class Meta:
        model = PackageImage
        fields = [
            "id",
            "image",
            "is_primary",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
        ]


# ===========================================================
# PACKAGE
# ===========================================================

class PackageSerializer(serializers.ModelSerializer):

    images = PackageImageSerializer(
        many=True,
        read_only=True,
    )

    class Meta:

        model = Package

        fields = [
            "id",
            "sender",

            "title",
            "description",
            "category",

            "weight",
            "declared_value",
            "reward_amount",
            "currency",

            "pickup_country",
            "pickup_city",
            "pickup_address",

            "destination_country",
            "destination_city",
            "destination_address",

            "pickup_date",
            "latest_delivery_date",

            "is_fragile",
            "requires_signature",
            "is_public",

            "status",
            "is_active",

            "images",

            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "sender",
            "status",
            "is_active",
            "created_at",
            "updated_at",
        ]

    # ===========================================================
    # TITLE
    # ===========================================================

    def validate_title(self, value):

        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "Package title is required."
            )

        if len(value) < 5:
            raise serializers.ValidationError(
                "Title must be at least 5 characters."
            )

        if len(value) > 200:
            raise serializers.ValidationError(
                "Title cannot exceed 200 characters."
            )

        return value

    # ===========================================================
    # DESCRIPTION
    # ===========================================================

    def validate_description(self, value):

        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "Description is required."
            )

        if len(value) < 20:
            raise serializers.ValidationError(
                "Description must contain at least 20 characters."
            )

        return value

    # ===========================================================
    # WEIGHT
    # ===========================================================

    def validate_weight(self, value):

        if value <= 0:
            raise serializers.ValidationError(
                "Weight must be greater than zero."
            )

        if value > Decimal("100"):
            raise serializers.ValidationError(
                "Maximum allowed weight is 100 KG."
            )

        return value

    # ===========================================================
    # DECLARED VALUE
    # ===========================================================

    def validate_declared_value(self, value):

        if value < 0:
            raise serializers.ValidationError(
                "Declared value cannot be negative."
            )

        return value

    # ===========================================================
    # REWARD
    # ===========================================================

    def validate_reward_amount(self, value):

        if value <= 0:
            raise serializers.ValidationError(
                "Reward amount must be greater than zero."
            )

        return value

    # ===========================================================
    # PICKUP DATE
    # ===========================================================

    def validate_pickup_date(self, value):

        from django.utils import timezone

        if value < timezone.localdate():
            raise serializers.ValidationError(
                "Pickup date cannot be in the past."
            )

        return value

    # ===========================================================
    # OBJECT VALIDATION
    # ===========================================================

    def validate(self, attrs):

        pickup_country = attrs.get("pickup_country")
        destination_country = attrs.get("destination_country")

        pickup_city = attrs.get("pickup_city")
        destination_city = attrs.get("destination_city")

        pickup_date = attrs.get("pickup_date")
        latest_delivery_date = attrs.get(
            "latest_delivery_date"
        )

        if (
            pickup_country
            and destination_country
            and pickup_country.lower() == destination_country.lower()
            and pickup_city
            and destination_city
            and pickup_city.lower() == destination_city.lower()
        ):
            raise serializers.ValidationError(
                {
                    "destination_city":
                        "Pickup and destination cannot be the same."
                }
            )

        if (
            pickup_date
            and latest_delivery_date
            and latest_delivery_date < pickup_date
        ):
            raise serializers.ValidationError(
                {
                    "latest_delivery_date":
                        "Delivery date must be after pickup date."
                }
            )

        return attrs

    # ===========================================================
    # CREATE
    # ===========================================================

    def create(self, validated_data):

        validated_data["sender"] = self.context[
            "request"
        ].user

        return Package.objects.create(**validated_data)

    # ===========================================================
    # UPDATE
    # ===========================================================

    def update(self, instance, validated_data):

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()

        return instance




# ==========================================================
# Package Image Response Serializer
# ==========================================================

class PackageImageSerializer(serializers.ModelSerializer):

    class Meta:

        model = PackageImage

        fields = (
            "id",
            "package",
            "image",
            "is_primary",
            "created_at",
        )

        read_only_fields = (
            "id",
            "package",
            "image",
            "created_at",
        )


# ==========================================================
# Upload Image Serializer
# ==========================================================

class PackageImageUploadSerializer(serializers.Serializer):

    image = serializers.ImageField(
        required=True,
        error_messages={
            "required": "Image is required.",
            "invalid": "Please upload a valid image.",
        },
    )

    MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB

    ALLOWED_EXTENSIONS = (
        "jpg",
        "jpeg",
        "png",
        "webp",
    )

    def validate_image(self, image):

        # ----------------------------
        # File Size Validation
        # ----------------------------

        if image.size > self.MAX_IMAGE_SIZE:

            raise serializers.ValidationError(
                "Image size cannot exceed 5 MB."
            )

        # ----------------------------
        # Extension Validation
        # ----------------------------

        extension = image.name.rsplit(".", 1)[-1].lower()

        if extension not in self.ALLOWED_EXTENSIONS:

            raise serializers.ValidationError(
                "Only JPG, JPEG, PNG and WEBP files are allowed."
            )

        return image