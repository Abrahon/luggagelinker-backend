from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from django.core.cache import cache
from .models import ChatRoom, ChatMessage

User = get_user_model()

class ChatParticipantSerializer(serializers.ModelSerializer):
    """Minified user payload specifically structured for real-time messaging participants."""
    is_online = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "first_name", "last_name", "email", "is_online", "last_seen"]
        read_only_fields = fields

    def get_is_online(self, obj) -> bool:
        """Checks Redis memory store for active active socket footprint."""
        return bool(cache.get(f"user_online_{obj.id}"))


class ChatMessageSerializer(serializers.ModelSerializer):
    """
    Serializes message content securely. 
    
    All routing nodes (room, sender, receiver) are read-only and explicitly 
    injected by the backend View via url parameters and request context.
    """
    class Meta:
        model = ChatMessage
        fields = [
            "id", "room", "sender", "receiver", "message", 
            "message_type", "attachment", "is_read", 
            "is_deleted", "edited_at", "created_at"
        ]
        # 🔒 Room and critical structural routing details are locked to prevent arbitrary injection
        read_only_fields = [
            "id", 
            "room", 
            "sender", 
            "receiver", 
            "message_type", 
            "is_read", 
            "is_deleted", 
            "edited_at", 
            "created_at"
        ]

    def to_representation(self, instance):
        """Masks private data elements instantly if a message has been soft-deleted."""
        ret = super().to_representation(instance)
        if instance.is_deleted:
            ret["message"] = _("This message was deleted.")
            ret["attachment"] = None
        return ret

    def validate(self, attrs):
        """Validates that a message body exists unless an attachment is present."""
        request = self.context.get("request")
        
        # Check if an attachment is arriving via files or data payloads
        has_attachment = request and ("attachment" in request.FILES or "attachment" in request.data)
        has_text = bool(attrs.get("message", "").strip())

        if not has_text and not has_attachment:
            raise serializers.ValidationError(
                {"message": _("Cannot send an empty message without text or a valid file attachment.")}
            )
        return attrs


class ChatRoomSerializer(serializers.ModelSerializer):
    """Optimized room presentation layer."""
    sender = ChatParticipantSerializer(read_only=True)
    traveler = ChatParticipantSerializer(read_only=True)
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = ChatRoom
        fields = [
            "id", "booking", "sender", "traveler", 
            "last_message", "last_message_at", 
            "is_active", "unread_count", "created_at", "updated_at"
        ]
        read_only_fields = fields

    def get_unread_count(self, obj) -> int:
        """Highly optimized unread counter using the explicit receiver column index."""
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            return obj.messages.filter(
                receiver=request.user, 
                is_read=False
            ).count()
        return 0


import os

from rest_framework import serializers

from .models import ChatMessage


class ChatFileUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = (
            "room",
            "attachment",
            "message_type",
            "message",
        )

    def validate_attachment(self, value):
        max_size = 20 * 1024 * 1024  # 20MB

        if value.size > max_size:
            raise serializers.ValidationError(
                "Maximum upload size is 20MB."
            )

        ext = os.path.splitext(value.name)[1].lower()

        allowed = [
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".webp",
            ".pdf",
            ".doc",
            ".docx",
            ".xls",
            ".xlsx",
            ".zip",
            ".mp4",
            ".mov",
            ".avi",
            ".mp3",
            ".wav",
            ".aac",
        ]

        if ext not in allowed:
            raise serializers.ValidationError(
                "Unsupported file type."
            )

        return value

    def validate(self, attrs):

        message_type = attrs.get("message_type")
        attachment = attrs.get("attachment")

        if message_type != ChatMessage.MessageType.TEXT and not attachment:
            raise serializers.ValidationError(
                {
                    "attachment": "Attachment is required."
                }
            )

        return attrs