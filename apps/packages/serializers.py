from decimal import Decimal

from rest_framework import serializers

from .models import Package, PackageImage

from rest_framework import serializers
from .models import PackageImage
from decimal import Decimal
from rest_framework import serializers
from apps.packages.models import Package


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
    # Nested fields representation
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
            # =========================================================================
            # NEW COMPLIANCE, PROOF & STATE CHANNELS INCLUDED IN THE FIELD MATRIX
            # =========================================================================
            "declared_as_legal",
            "terms_accepted",
            "verification_status",
            "risk_score",
            "purchase_receipt",
            "serial_number",
            "imei",
            "traveler_matches_listing",
            "traveler_refusal_reason",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "sender",
            "status",
            "is_active",
            # State engines cannot be manipulated externally by raw payload injections
            "verification_status",
            "risk_score",
            "traveler_matches_listing",
            "traveler_refusal_reason",
            "created_at",
            "updated_at",
        ]

    # =========================
    # COMPLIANCE VALIDATION
    # =========================
    def validate_declared_as_legal(self, value):
        if not value:
            raise serializers.ValidationError("You must declare that this package contains only legal items.")
        return value

    def validate_terms_accepted(self, value):
        if not value:
            raise serializers.ValidationError("You must confirm that your photos accurately represent the package contents.")
        return value

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
    # CROSS-FIELD DATES/LOCATIONS ARCHITECTURE
    # =========================
    def validate(self, attrs):
        pickup_date = attrs.get("pickup_date")
        latest_delivery_date = attrs.get("latest_delivery_date")

        pickup_country = attrs.get("pickup_country")
        destination_country = attrs.get("destination_country")
        pickup_city = attrs.get("pickup_city")
        destination_city = attrs.get("destination_city")

        # 1. Location Integrity Boundary Checks
        if (
            pickup_country
            and destination_country
            and pickup_city
            and destination_city
            and pickup_country.lower().strip() == destination_country.lower().strip()
            and pickup_city.lower().strip() == destination_city.lower().strip()
        ):
            raise serializers.ValidationError({
                "destination_city": "Pickup and destination locations cannot match identical points."
            })

        # 2. Timeline Consistency Check
        if pickup_date and latest_delivery_date:
            if latest_delivery_date < pickup_date:
                raise serializers.ValidationError({
                    "latest_delivery_date": "The delivery buffer cannot schedule before the primary pick-up window."
                })

        return attrs



# =========================================================================
# STANDALONE INPUT VALIDATION SERIALIZERS
# =========================================================================

class AdminReviewSerializer(serializers.Serializer):
    """Handles explicit datatype validation for admin oversight choices."""
    approve = serializers.BooleanField(
        required=True,
        error_messages={"invalid": "The approve field must be a valid boolean (true or false)."}
    )


# class TravelerHandshakeSerializer(serializers.Serializer):
#     """Handles explicit parameter verification during package pickup handoff."""
#     traveler_matches_listing = serializers.BooleanField(required=True)
#     traveler_refusal_reason = serializers.CharField(required=False, allow_blank=True)

#     def validate(self, attrs):
#         matches_listing = attrs.get("traveler_matches_listing")
#         refusal_reason = attrs.get("traveler_refusal_reason", "").strip()

#         # Enforce textual feedback constraint natively inside serialization validation rules
#         if not matches_listing and not refusal_reason:
#             raise serializers.ValidationError({
#                 "traveler_refusal_reason": "A detailed explanation is required when rejecting a physical package parcel."
#             })
            
#         return attrs
    

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