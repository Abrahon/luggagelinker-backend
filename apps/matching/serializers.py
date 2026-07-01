from rest_framework import serializers

from .models import Match


class MatchSerializer(serializers.ModelSerializer):

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

    class Meta:

        model = Match

        fields = [
            "id",

            "package",
            "package_title",

            "trip",
            "trip_title",

            "sender",
            "traveler",

            "score",

            "status",
            "is_active",

            "created_at",
            "updated_at",
        ]

        read_only_fields = fields