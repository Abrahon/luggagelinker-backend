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

    # =========================
    # CREATE
    # =========================

    def create(self, validated_data):

        validated_data["sender"] = self.context["request"].user

        return Package.objects.create(**validated_data)

    # =========================
    # TITLE
    # =========================

    def validate_title(self, value):

        value = value.strip()

        if len(value) < 5:
            raise serializers.ValidationError("Title too short.")

        if len(value) > 200:
            raise serializers.ValidationError("Title too long.")

        return value

    # =========================
    # DESCRIPTION
    # =========================

    def validate_description(self, value):

        value = value.strip()

        if len(value) < 20:
            raise serializers.ValidationError("Description too short.")

        return value

    # =========================
    # WEIGHT
    # =========================

    def validate_weight(self, value):

        if value <= 0:
            raise serializers.ValidationError("Weight must be > 0.")

        if value > Decimal("100"):
            raise serializers.ValidationError("Max weight is 100 KG.")

        return value

    # =========================
    # DECLARED VALUE
    # =========================

    def validate_declared_value(self, value):

        if value < 0:
            raise serializers.ValidationError("Invalid declared value.")

        return value

    # =========================
    # REWARD
    # =========================

    def validate_reward_amount(self, value):

        if value <= 0:
            raise serializers.ValidationError("Reward must be > 0.")

        return value

    # =========================
    # DATE VALIDATION
    # =========================

    def validate(self, attrs):

        pickup_date = attrs.get("pickup_date")
        latest_delivery_date = attrs.get("latest_delivery_date")

        pickup_country = attrs.get("pickup_country")
        destination_country = attrs.get("destination_country")

        pickup_city = attrs.get("pickup_city")
        destination_city = attrs.get("destination_city")

        # same city check
        if (
            pickup_country
            and destination_country
            and pickup_city
            and destination_city
            and pickup_country.lower() == destination_country.lower()
            and pickup_city.lower() == destination_city.lower()
        ):
            raise serializers.ValidationError({
                "destination_city": "Pickup and destination cannot be same."
            })

        # date check
        if pickup_date and latest_delivery_date:
            if latest_delivery_date < pickup_date:
                raise serializers.ValidationError({
                    "latest_delivery_date": "Must be after pickup date."
                })

        return attrs



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