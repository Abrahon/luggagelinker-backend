from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from .models import Trip


class TripSerializer(serializers.ModelSerializer):

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

            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "traveler",
            "available_weight_kg",
            "status",
            "is_active",
            "created_at",
            "updated_at",
        ]

    # ==========================================================
    # TITLE
    # ==========================================================

    def validate_title(self, value):

        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "Trip title is required."
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

    # ==========================================================
    # DESCRIPTION
    # ==========================================================

    def validate_description(self, value):

        if value:

            value = value.strip()

            if len(value) < 20:
                raise serializers.ValidationError(
                    "Description must contain at least 20 characters."
                )

        return value

    # ==========================================================
    # MAX WEIGHT
    # ==========================================================

    def validate_max_weight_kg(self, value):

        if value <= 0:
            raise serializers.ValidationError(
                "Maximum weight must be greater than zero."
            )

        if value > Decimal("100"):
            raise serializers.ValidationError(
                "Maximum allowed weight is 100 KG."
            )

        return value

    # ==========================================================
    # REWARD
    # ==========================================================

    def validate_reward_per_kg(self, value):

        if value < 0:
            raise serializers.ValidationError(
                "Reward cannot be negative."
            )

        return value

    # ==========================================================
    # DEPARTURE DATE
    # ==========================================================

    def validate_departure_date(self, value):

        if value < timezone.localdate():

            raise serializers.ValidationError(
                "Departure date cannot be in the past."
            )

        return value

    # ==========================================================
    # OBJECT VALIDATION
    # ==========================================================

    def validate(self, attrs):

        from_country = attrs.get(
            "from_country",
            getattr(self.instance, "from_country", None),
        )

        to_country = attrs.get(
            "to_country",
            getattr(self.instance, "to_country", None),
        )

        from_city = attrs.get(
            "from_city",
            getattr(self.instance, "from_city", None),
        )

        to_city = attrs.get(
            "to_city",
            getattr(self.instance, "to_city", None),
        )

        departure_date = attrs.get(
            "departure_date",
            getattr(self.instance, "departure_date", None),
        )

        arrival_date = attrs.get(
            "arrival_date",
            getattr(self.instance, "arrival_date", None),
        )

        max_weight = attrs.get(
            "max_weight_kg",
            getattr(self.instance, "max_weight_kg", None),
        )

        available_weight = getattr(
            self.instance,
            "available_weight_kg",
            None,
        )

        if (
            from_country
            and to_country
            and from_city
            and to_city
        ):

            if (
                from_country.lower() == to_country.lower()
                and from_city.lower() == to_city.lower()
            ):

                raise serializers.ValidationError(
                    {
                        "to_city":
                            "Destination cannot be the same as departure city."
                    }
                )

        if (
            departure_date
            and arrival_date
            and arrival_date < departure_date
        ):

            raise serializers.ValidationError(
                {
                    "arrival_date":
                        "Arrival date must be after departure date."
                }
            )

        if (
            self.instance
            and max_weight
            and available_weight is not None
            and max_weight < available_weight
        ):

            raise serializers.ValidationError(
                {
                    "max_weight_kg":
                        "Maximum weight cannot be less than available weight."
                }
            )

        return attrs

    # ==========================================================
    # CREATE
    # ==========================================================

    def create(self, validated_data):

        validated_data["traveler"] = self.context[
            "request"
        ].user

        validated_data["available_weight_kg"] = validated_data[
            "max_weight_kg"
        ]

        return Trip.objects.create(
            **validated_data
        )

    # ==========================================================
    # UPDATE
    # ==========================================================

    def update(self, instance, validated_data):

        previous_max = instance.max_weight_kg
        previous_available = instance.available_weight_kg

        new_max = validated_data.get(
            "max_weight_kg",
            previous_max,
        )

        used_weight = previous_max - previous_available

        instance.available_weight_kg = new_max - used_weight

        for attr, value in validated_data.items():

            setattr(instance, attr, value)

        instance.save()

        return instance