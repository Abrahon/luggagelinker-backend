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

    # ----------------------------
    # CREATE
    # ----------------------------
    def create(self, validated_data):
        validated_data["sender"] = self.context["request"].user
        return Package.objects.create(**validated_data)
    
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



from rest_framework import serializers

from apps.packages.models import Package, PackageImage


class AdminPackageImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PackageImage
        fields = [
            "id",
            "image",
            "is_primary",
        ]


class AdminPackageSerializer(serializers.ModelSerializer):

    sender_email = serializers.EmailField(
        source="sender.email",
        read_only=True,
    )

    sender_name = serializers.SerializerMethodField()

    images = AdminPackageImageSerializer(
        many=True,
        read_only=True,
    )

    class Meta:
        model = Package

        fields = [
            "id",
            "title",
            "description",
            "category",

            "weight",

            "pickup_country",
            "pickup_city",
            "pickup_address",

            "destination_country",
            "destination_city",
            "destination_address",

            "pickup_date",
            "latest_delivery_date",

            "status",
            "verification_status",
            "risk_score",

            "declared_as_legal",
            "terms_accepted",

            "traveler_matches_listing",
            "traveler_refusal_reason",

            "sender_email",
            "sender_name",

            "images",

            "created_at",
            "updated_at",
        ]

    def get_sender_name(self, obj):
        profile = getattr(obj.sender, "profile", None)

        if not profile:
            return ""

        return f"{profile.first_name} {profile.last_name}"





class PackageDashboardStatsSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    draft = serializers.IntegerField()
    published = serializers.IntegerField()
    matched = serializers.IntegerField()
    booked = serializers.IntegerField()
    in_transit = serializers.IntegerField()
    delivered = serializers.IntegerField()
    cancelled = serializers.IntegerField()
    expired = serializers.IntegerField()



# apps/trips/serializers.py

from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.profiles.models import Profile

User = get_user_model()

class SenderProfileSerializer(serializers.ModelSerializer):

    name = serializers.SerializerMethodField()
    country = serializers.SerializerMethodField()
    phone = serializers.SerializerMethodField()
    profile_image = serializers.SerializerMethodField()

    member_since = serializers.DateTimeField(
        source="date_joined",
        read_only=True,
    )

    total_packages = serializers.IntegerField(
        source="total_packages_value",
        read_only=True,
    )

    successful_deliveries = serializers.IntegerField(
        source="successful_deliveries_value",
        read_only=True,
    )

    cancelled_deliveries = serializers.IntegerField(
        source="cancelled_deliveries_value",
        read_only=True,
    )

    success_rate = serializers.FloatField(
        source="success_rate_value",
        read_only=True,
    )

    is_email_verified = serializers.BooleanField(
        source="is_email_verified_value",
        read_only=True,
    )

    class Meta:
        model = User

        fields = [
            "id",
            "name",
            "country",

            "email",
            "phone",
            "profile_image",

            "member_since",

            "total_packages",
            "successful_deliveries",
            "cancelled_deliveries",
            "success_rate",

            "is_email_verified",
        ]

    def get_name(self, obj):
        profile = getattr(obj, "profile", None)

        if not profile:
            return None

        first_name = getattr(
            profile,
            "first_name",
            "",
        ) or ""

        last_name = getattr(
            profile,
            "last_name",
            "",
        ) or ""

        return (
            f"{first_name} {last_name}"
        ).strip() or None

    def get_country(self, obj):
        profile = getattr(obj, "profile", None)

        if not profile:
            return None

        return getattr(
            profile,
            "country",
            None,
        )

    def get_phone(self, obj):
        profile = getattr(obj, "profile", None)

        if not profile:
            return None

        return getattr(
            profile,
            "phone",
            None,
        ) or None

    def get_profile_image(self, obj):
        profile = getattr(obj, "profile", None)

        if not profile:
            return None

        picture = getattr(
            profile,
            "profile_picture",
            None,
        )

        if not picture:
            return None

        try:
            return picture.url
        except (AttributeError, ValueError):
            return None