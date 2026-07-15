from rest_framework import serializers

from apps.profiles.models import Profile
from .models import ActiveTracker, LocationHistory


class TrackerUserSerializer(serializers.Serializer):
    """
    Lightweight tracker user serializer.
    Reads profile information without exposing unnecessary user fields.
    """

    id = serializers.UUIDField(read_only=True)
    full_name = serializers.SerializerMethodField()
    profile_image = serializers.SerializerMethodField()
    is_online = serializers.BooleanField(read_only=True)
    last_seen = serializers.DateTimeField(read_only=True)

    def get_full_name(self, obj):
        profile = getattr(obj, "profile", None)
        if profile:
            return profile.full_name
        return ""

    def get_profile_image(self, obj):
        profile = getattr(obj, "profile", None)

        if (
            profile
            and profile.profile_image
        ):
            return profile.profile_image.url

        return None


class LocationHistorySerializer(serializers.ModelSerializer):
    """
    Serializer used only for trip replay/history.
    """

    class Meta:
        model = LocationHistory
        fields = (
            "id",
            "latitude",
            "longitude",
            "speed",
            "heading",
            "accuracy",
            "altitude",
            "recorded_at",
        )

        read_only_fields = fields


class ActiveTrackerSerializer(serializers.ModelSerializer):
    """
    Production serializer.

    Returns ONLY the latest tracking state.
    History is intentionally excluded for performance.
    """

    tracker_user = TrackerUserSerializer(read_only=True)

    room_id = serializers.UUIDField(
        source="room.id",
        read_only=True,
    )

    class Meta:
        model = ActiveTracker

        fields = (
            "id",
            "room_id",
            "tracker_user",

            "current_lat",
            "current_lng",

            "destination_lat",
            "destination_lng",

            "speed",
            "heading",
            "accuracy",
            "altitude",

            "distance_remaining_km",
            "eta_minutes",

            "status",
            "updated_at",
        )

        read_only_fields = (
            "id",
            "tracker_user",

            "current_lat",
            "current_lng",

            "speed",
            "heading",
            "accuracy",
            "altitude",

            "distance_remaining_km",
            "eta_minutes",

            "updated_at",
        )

    def validate(self, attrs):
        """
        Production validations.
        """

        room = attrs.get("room")

        if (
            room
            and not self.instance
            and ActiveTracker.objects.filter(room=room).exists()
        ):
            raise serializers.ValidationError(
                {
                    "room": (
                        "Tracking has already been initialized "
                        "for this room."
                    )
                }
            )

        destination_lat = attrs.get("destination_lat")
        destination_lng = attrs.get("destination_lng")

        if destination_lat is None:
            raise serializers.ValidationError(
                {
                    "destination_lat":
                    "Destination latitude is required."
                }
            )

        if destination_lng is None:
            raise serializers.ValidationError(
                {
                    "destination_lng":
                    "Destination longitude is required."
                }
            )

        if not (-90 <= destination_lat <= 90):
            raise serializers.ValidationError(
                {
                    "destination_lat":
                    "Latitude must be between -90 and 90."
                }
            )

        if not (-180 <= destination_lng <= 180):
            raise serializers.ValidationError(
                {
                    "destination_lng":
                    "Longitude must be between -180 and 180."
                }
            )

        return attrs