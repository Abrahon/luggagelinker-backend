from rest_framework import serializers

from .models import Match

from rest_framework import serializers

from .models import Match, MatchStatus

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




class MatchStatusSerializer(serializers.ModelSerializer):

    class Meta:

        model = Match

        fields = [
            "status",
        ]

    def validate_status(self, value):

        allowed_status = [
            MatchStatus.REQUESTED,
            MatchStatus.ACCEPTED,
            MatchStatus.REJECTED,
        ]

        if value not in allowed_status:

            raise serializers.ValidationError(
                "Invalid match status."
            )

        return value





class MatchScoreSerializer(serializers.ModelSerializer):

    class Meta:

        model = Match

        fields = [
            "score",
        ]

    def validate_score(self, value):

        if value < 0 or value > 100:

            raise serializers.ValidationError(
                "Score must be between 0 and 100."
            )

        return value