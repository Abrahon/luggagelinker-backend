from rest_framework import serializers
from .models import Match, MatchStatus


# ==========================================================
# MATCH MAIN SERIALIZER
# ==========================================================
from rest_framework import serializers
from .models import Match, MatchStatus


# ==========================================================
# MATCH MAIN SERIALIZER
# ==========================================================

class MatchSerializer(serializers.ModelSerializer):

    # ------------------------------------------------------
    # PACKAGE IMAGE FROM PACKAGEIMAGE MODEL
    # ------------------------------------------------------
    package_image = serializers.SerializerMethodField()

    package_title = serializers.CharField(
        source="package.title",
        read_only=True,
    )

    trip_title = serializers.CharField(
        source="trip.title",
        read_only=True,
    )

    sender = serializers.CharField(
        source="package.sender.email",
        read_only=True,
    )

    traveler = serializers.CharField(
        source="trip.traveler.email",
        read_only=True,
    )

    # ------------------------------------------------------
    # TRAVELER DETAILS FROM PROFILE MODEL
    # ------------------------------------------------------
    traveler_name = serializers.SerializerMethodField()

    traveler_avatar = serializers.SerializerMethodField()

    traveler_rating = serializers.DecimalField(
        source="trip.traveler.profile.average_rating",
        max_digits=3,
        decimal_places=2,
        read_only=True,
        default=0.00,
    )

    total_reviews = serializers.IntegerField(
        source="trip.traveler.profile.total_reviews",
        read_only=True,
        default=0,
    )

    # ------------------------------------------------------
    # TRIP DETAILS & DATES
    # ------------------------------------------------------
    departure_date = serializers.DateField(
        source="trip.departure_date",
        read_only=True,
        default=None,
    )

    arrival_date = serializers.DateField(
        source="trip.arrival_date",
        read_only=True,
        default=None,
    )

    remaining_weight = serializers.DecimalField(
        source="trip.available_weight_kg",
        max_digits=6,
        decimal_places=2,
        read_only=True,
        default=0.00,
    )

    trip_status = serializers.CharField(
        source="trip.status",
        read_only=True,
        default="",
    )

    # ------------------------------------------------------
    # REWARD PER KG & CURRENCY
    # ------------------------------------------------------
    reward_per_kg = serializers.DecimalField(
        source="trip.reward_per_kg",
        max_digits=10,
        decimal_places=2,
        read_only=True,
        default=0.00,
    )

    currency = serializers.CharField(
        source="trip.currency",
        read_only=True,
        default="USD",
    )

    # ------------------------------------------------------
    # PRODUCTION ROUTE FIELDS
    # ------------------------------------------------------
    package_pickup_city = serializers.CharField(
        source="package.pickup_city",
        read_only=True,
    )

    package_pickup_country = serializers.CharField(
        source="package.pickup_country",
        read_only=True,
    )

    package_destination_city = serializers.CharField(
        source="package.destination_city",
        read_only=True,
    )

    package_destination_country = serializers.CharField(
        source="package.destination_country",
        read_only=True,
    )

    traveler_from_city = serializers.CharField(
        source="trip.from_city",
        read_only=True,
    )

    traveler_from_country = serializers.CharField(
        source="trip.from_country",
        read_only=True,
    )

    traveler_to_city = serializers.CharField(
        source="trip.to_city",
        read_only=True,
    )

    traveler_to_country = serializers.CharField(
        source="trip.to_country",
        read_only=True,
    )

    class Meta:
        model = Match

        fields = [
            "id",

            # Package info
            "package",
            "package_title",
            "package_image",
            "sender",
            "package_pickup_city",
            "package_pickup_country",
            "package_destination_city",
            "package_destination_country",

            # Trip info
            "trip",
            "trip_title",
            "traveler",
            "traveler_name",
            "traveler_avatar",
            "traveler_rating",
            "total_reviews",
            "departure_date",
            "arrival_date",
            "remaining_weight",
            "reward_per_kg",
            "currency",
            "trip_status",
            "traveler_from_city",
            "traveler_from_country",
            "traveler_to_city",
            "traveler_to_country",

            # Match meta
            "score",
            "status",
            "is_active",

            "created_at",
            "updated_at",
        ]

        read_only_fields = fields

    # ------------------------------------------------------
    # HELPER METHODS
    # ------------------------------------------------------

    def get_package_image(self, obj):
        package = getattr(obj, "package", None)
        if not package:
            return None

        primary_img = package.images.filter(is_primary=True).first()
        if primary_img and primary_img.image:
            return primary_img.image

        first_img = package.images.first()
        if first_img and first_img.image:
            return first_img.image

        return None

    def get_traveler_name(self, obj):
        traveler = getattr(obj.trip, "traveler", None)
        if not traveler:
            return ""

        profile = getattr(traveler, "profile", None)
        if profile:
            if hasattr(profile, "full_name") and profile.full_name:
                return profile.full_name

            first_name = getattr(profile, "first_name", "").strip()
            last_name = getattr(profile, "last_name", "").strip()
            full_name = f"{first_name} {last_name}".strip()

            if full_name:
                return full_name

            if hasattr(profile, "name") and profile.name:
                return profile.name

        return traveler.email

    def get_traveler_avatar(self, obj):
        traveler = getattr(obj.trip, "traveler", None)
        if not traveler:
            return None

        profile = getattr(traveler, "profile", None)
        if profile and profile.profile_picture:
            return str(profile.profile_picture.url) if hasattr(profile.profile_picture, 'url') else str(profile.profile_picture)

        return None