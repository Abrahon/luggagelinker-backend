from rest_framework import serializers
from rest_framework import serializers
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):

    class Meta:

        model = Notification

        fields = [
            "id",

            "title",
            "message",

            "notification_type",

            "object_id",
            "action_url",

            "is_read",
            "is_active",

            "created_at",
            "updated_at",
        ]

        read_only_fields = fields





class NotificationReadSerializer(serializers.Serializer):

    is_read = serializers.BooleanField()

    def validate_is_read(self, value):

        if value is not True:

            raise serializers.ValidationError(
                "is_read must be true."
            )

        return value