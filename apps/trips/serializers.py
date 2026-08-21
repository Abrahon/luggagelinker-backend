from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers
from apps.reviews.models import Review
from django.db.models import Avg

from .models import Trip



class TripSerializer(serializers.ModelSerializer):

    average_rating = serializers.SerializerMethodField()
    reviews = serializers.SerializerMethodField()

    class Meta:
        model = Trip

        fields = [
            "id",
            "traveler",

            "title",
            "description",

            "from_country",
            "from_city",

            "to_country",
            "to_city",

            "departure_date",
            "arrival_date",

            "max_weight_kg",
            "available_weight_kg",

            "reward_per_kg",
            "currency",

            "status",
            "is_active",
            "is_public",

            # Rating & Review Fields
            "average_rating",
            "reviews",

            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "traveler",
            "available_weight_kg",
            "status",
            "is_active",
            "average_rating",
            "reviews",
            "created_at",
            "updated_at",
        ]

    # ==========================================================
    # AVERAGE RATING & REVIEWS
    # ==========================================================

    def get_average_rating(self, obj):
        """
        Calculates the average rating for this specific trip across all senders.
        Example: (5 + 4) / 2 = 4.5
        """
        avg = Review.objects.filter(booking__trip=obj).aggregate(avg_rating=Avg("rating"))["avg_rating"]
        return round(avg, 1) if avg is not None else 0.0

    def get_reviews(self, obj):
        """
        Lists individual ratings for this trip.
        """
        return list(Review.objects.filter(booking__trip=obj).values("rating"))

    # ==========================================================
    # TITLE
    # ==========================================================

    def validate_title(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError("Trip title is required.")

        if len(value) < 5:
            raise serializers.ValidationError("Title must be at least 5 characters.")

        if len(value) > 200:
            raise serializers.ValidationError("Title cannot exceed 200 characters.")

        return value

    # ==========================================================
    # DESCRIPTION
    # ==========================================================

    def validate_description(self, value):
        if value:
            value = value.strip()
            if len(value) < 20:
                raise serializers.ValidationError("Description must contain at least 20 characters.")
        return value

    # ==========================================================
    # MAX WEIGHT
    # ==========================================================

    def validate_max_weight_kg(self, value):
        if value <= 0:
            raise serializers.ValidationError("Maximum weight must be greater than zero.")

        if value > Decimal("100"):
            raise serializers.ValidationError("Maximum allowed weight is 100 KG.")

        return value

    # ==========================================================
    # REWARD
    # ==========================================================

    def validate_reward_per_kg(self, value):
        if value < 0:
            raise serializers.ValidationError("Reward cannot be negative.")
        return value

    # ==========================================================
    # DEPARTURE DATE
    # ==========================================================

    def validate_departure_date(self, value):
        if value < timezone.localdate():
            raise serializers.ValidationError("Departure date cannot be in the past.")
        return value

    # ==========================================================
    # OBJECT VALIDATION
    # ==========================================================

    def validate(self, attrs):
        from_country = attrs.get("from_country", getattr(self.instance, "from_country", None))
        to_country = attrs.get("to_country", getattr(self.instance, "to_country", None))
        from_city = attrs.get("from_city", getattr(self.instance, "from_city", None))
        to_city = attrs.get("to_city", getattr(self.instance, "to_city", None))

        departure_date = attrs.get("departure_date", getattr(self.instance, "departure_date", None))
        arrival_date = attrs.get("arrival_date", getattr(self.instance, "arrival_date", None))

        max_weight = attrs.get("max_weight_kg", getattr(self.instance, "max_weight_kg", None))
        available_weight = getattr(self.instance, "available_weight_kg", None)

        if from_country and to_country and from_city and to_city:
            if (
                from_country.lower() == to_country.lower()
                and from_city.lower() == to_city.lower()
            ):
                raise serializers.ValidationError(
                    {"to_city": "Destination cannot be the same as departure city."}
                )

        if departure_date and arrival_date and arrival_date < departure_date:
            raise serializers.ValidationError(
                {"arrival_date": "Arrival date must be after departure date."}
            )

        if (
            self.instance
            and max_weight
            and available_weight is not None
            and max_weight < available_weight
        ):
            raise serializers.ValidationError(
                {"max_weight_kg": "Maximum weight cannot be less than available weight."}
            )

        return attrs

    # ==========================================================
    # CREATE
    # ==========================================================

    def create(self, validated_data):
        validated_data["traveler"] = self.context["request"].user
        validated_data["available_weight_kg"] = validated_data["max_weight_kg"]
        return Trip.objects.create(**validated_data)

    # ==========================================================
    # UPDATE
    # ==========================================================

    def update(self, instance, validated_data):
        previous_max = instance.max_weight_kg
        previous_available = instance.available_weight_kg

        new_max = validated_data.get("max_weight_kg", previous_max)
        used_weight = previous_max - previous_available

        instance.available_weight_kg = new_max - used_weight

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()
        return instance


class AdminTripListSerializer(serializers.ModelSerializer):
    traveler_email = serializers.EmailField(
        source="traveler.email",
        read_only=True,
    )

    class Meta:
        model = Trip
        fields = [
            "id",
            "title",
            "traveler_email",
            "from_country",
            "from_city",
            "to_country",
            "to_city",
            "departure_date",
            "arrival_date",
            "max_weight_kg",
            "available_weight_kg",
            "reward_per_kg",
            "currency",
            "status",
            "is_active",
            "created_at",
        ]


class AdminTripSerializer(serializers.ModelSerializer):
    traveler_email = serializers.EmailField(
        source="traveler.email",
        read_only=True,
    )

    class Meta:
        model = Trip
        fields = [
            "id",
            "traveler_email",
            "title",
            "description",
            "from_country",
            "from_city",
            "to_country",
            "to_city",
            "departure_date",
            "arrival_date",
            "max_weight_kg",
            "available_weight_kg",
            "reward_per_kg",
            "currency",
            "status",
            "is_active",
            "is_public",
            "created_at",
            "updated_at",
        ]



# apps/trips/serializers.py

from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.reviews.models import Review


User = get_user_model()


class TravelerReviewSerializer(serializers.ModelSerializer):
    """
    Review displayed on the public traveler profile.
    """

    reviewer = serializers.SerializerMethodField()
    profile_image = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = [
            "id",
            "rating",
            "comment",
            "reviewer",
            "profile_image",
            "created_at",
        ]

    def get_reviewer(self, obj):
        reviewer = getattr(obj, "reviewer", None)

        if reviewer is None:
            return None

        full_name = reviewer.get_full_name()

        return full_name or reviewer.username

    def get_profile_image(self, obj):
        reviewer = getattr(obj, "reviewer", None)

        if reviewer is None:
            return None

        profile = getattr(reviewer, "profile", None)

        if profile and getattr(profile, "profile_image", None):
            try:
                return profile.profile_image.url
            except ValueError:
                return None

        return None



# apps/trips/serializers.py

from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.reviews.models import Review


User = get_user_model()


class TravelerReviewSerializer(serializers.ModelSerializer):

    reviewer = serializers.SerializerMethodField()
    reviewer_profile_image = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = [
            "id",
            "rating",
            "comment",
            "reviewer",
            "reviewer_profile_image",
            "created_at",
        ]

    # ==========================================================
    # REVIEWER NAME
    # ==========================================================

    def get_reviewer(self, obj):

        sender = getattr(obj, "sender", None)

        if not sender:
            return None

        profile = getattr(sender, "profile", None)

        if not profile:
            return None

        first_name = (
            getattr(profile, "first_name", "") or ""
        ).strip()

        last_name = (
            getattr(profile, "last_name", "") or ""
        ).strip()

        full_name = f"{first_name} {last_name}".strip()

        return full_name or None

    # ==========================================================
    # REVIEWER PROFILE IMAGE
    # ==========================================================

    def get_reviewer_profile_image(self, obj):

        sender = getattr(obj, "sender", None)

        if not sender:
            return None

        profile = getattr(sender, "profile", None)

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


        
class TravelerProfileSerializer(serializers.ModelSerializer):

    # ==========================================================
    # BASIC PROFILE
    # ==========================================================

    name = serializers.SerializerMethodField()
    country = serializers.SerializerMethodField()
    profile_image = serializers.SerializerMethodField()

    # ==========================================================
    # RATING STATISTICS
    # ==========================================================

    average_rating = serializers.FloatField(
        source="average_rating_value",
        read_only=True,
    )

    total_reviews = serializers.IntegerField(
        source="total_reviews_value",
        read_only=True,
    )

    # ==========================================================
    # TRAVEL STATISTICS
    # ==========================================================

    completed_trips = serializers.IntegerField(
        source="completed_trips_value",
        read_only=True,
    )

    total_deliveries = serializers.IntegerField(
        source="total_deliveries_value",
        read_only=True,
    )

    successful_deliveries = serializers.IntegerField(
        source="successful_deliveries_value",
        read_only=True,
    )

    # ==========================================================
    # DISPUTE STATISTICS
    # ==========================================================

    disputed_deliveries = serializers.IntegerField(
        source="disputed_deliveries_value",
        read_only=True,
    )

    traveler_fault_disputes = serializers.IntegerField(
        source="traveler_fault_disputes_value",
        read_only=True,
    )

    pending_disputes = serializers.IntegerField(
        source="pending_disputes_value",
        read_only=True,
    )

    # ==========================================================
    # SUCCESS RATE
    # ==========================================================

    success_rate = serializers.FloatField(
        source="success_rate_value",
        read_only=True,
    )

    # ==========================================================
    # REVIEWS
    # ==========================================================

    rating_distribution = serializers.SerializerMethodField()

    recent_reviews = serializers.SerializerMethodField()

    # ==========================================================
    # META
    # ==========================================================

    class Meta:
        model = User

        fields = [
            # Basic profile
            "id",
            "name",
            "country",
            "profile_image",

            # Rating
            "average_rating",
            "total_reviews",

            # Delivery statistics
            "completed_trips",
            "total_deliveries",
            "successful_deliveries",

            # Dispute statistics
            "disputed_deliveries",
            "traveler_fault_disputes",
            "pending_disputes",

            # Success
            "success_rate",

            # Reviews
            "rating_distribution",
            "recent_reviews",
        ]

    # ==========================================================
    # NAME
    # ==========================================================

    def get_name(self, obj):

        profile = getattr(
            obj,
            "profile",
            None,
        )

        if not profile:
            return None

        first_name = (
            getattr(profile, "first_name", "")
            or ""
        ).strip()

        last_name = (
            getattr(profile, "last_name", "")
            or ""
        ).strip()

        full_name = f"{first_name} {last_name}".strip()

        return full_name or None

    # ==========================================================
    # COUNTRY
    # ==========================================================

    def get_country(self, obj):

        profile = getattr(
            obj,
            "profile",
            None,
        )

        if not profile:
            return None

        return (
            getattr(
                profile,
                "country",
                None,
            )
            or None
        )

    # ==========================================================
    # PROFILE IMAGE
    # ==========================================================

    def get_profile_image(self, obj):

        profile = getattr(
            obj,
            "profile",
            None,
        )

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

        except (
            AttributeError,
            ValueError,
        ):
            return None

    # ==========================================================
    # RATING DISTRIBUTION
    # ==========================================================

    def get_rating_distribution(self, obj):

        return getattr(
            obj,
            "rating_distribution_data",
            {
                "5": 0,
                "4": 0,
                "3": 0,
                "2": 0,
                "1": 0,
            },
        )

    # ==========================================================
    # RECENT REVIEWS
    # ==========================================================

    def get_recent_reviews(self, obj):

        reviews = getattr(
            obj,
            "recent_reviews_data",
            [],
        )

        return TravelerReviewSerializer(
            reviews,
            many=True,
            context=self.context,
        ).data