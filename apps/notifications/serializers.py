from rest_framework import serializers
from rest_framework import serializers
from .models import Notification


from rest_framework import serializers
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    sender_name = serializers.CharField(
        source="sender.full_name",
        read_only=True,
    )
    sender_profile_picture = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            "id",
            "title",
            "message",
            "notification_type",

            "object_id",
            "action_url",

            "sender",
            "sender_name",
            "sender_profile_picture",

            "room_id",
            "message_id",

            "is_read",
            "is_active",

            "created_at",
            "updated_at",
        ]

        read_only_fields = fields

    def get_sender_profile_picture(self, obj):
        if obj.sender and hasattr(obj.sender, "profile"):
            if obj.sender.profile.profile_picture:
                return obj.sender.profile.profile_picture.url
        return None




class NotificationReadSerializer(serializers.Serializer):

    is_read = serializers.BooleanField()

    def validate_is_read(self, value):

        if value is not True:

            raise serializers.ValidationError(
                "is_read must be true."
            )

        return value