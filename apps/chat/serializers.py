from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from django.core.cache import cache
from .models import ChatRoom, ChatMessage

import os
from rest_framework import serializers

User = get_user_model()

class ChatParticipantSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    profile_image = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "full_name",
            "profile_image",
            "is_online",
            "last_seen",
        )

    def get_full_name(self, obj):
        profile = getattr(obj, "profile", None)
        if profile:
            return profile.full_name
        return ""

    def get_profile_image(self, obj):
        profile = getattr(obj, "profile", None)
        if profile and profile.profile_picture:
            return profile.profile_picture.url
        return None

class ChatMessageSerializer(serializers.ModelSerializer):
    attachment = serializers.SerializerMethodField()

    class Meta:
        model = ChatMessage
        fields = (
            "id",
            "room",
            "sender",
            "receiver",
            "message",
            "message_type",
            "attachment",
            "is_delivered",
            "delivered_at",
            "is_read",
            "read_at",
            "is_deleted",
            "edited_at",
            "created_at",
        )

        read_only_fields = (
            "id",
            "room",
            "sender",
            "receiver",
            "is_delivered",
            "delivered_at",
            "is_read",
            "read_at",
            "is_deleted",
            "edited_at",
            "created_at",
        )

    def get_attachment(self, obj):
        if obj.attachment:
            return obj.attachment.url
        return None


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
    """
    Chat room serializer for conversation list.
    Returns only the other participant.
    """

    participant = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    last_message_type = serializers.SerializerMethodField()
    last_message_sender = serializers.SerializerMethodField()

    class Meta:
        model = ChatRoom
        fields = (
            "id",
            "booking",
            "participant",
            "last_message",
            "last_message_type",
            "last_message_sender",
            "last_message_at",
            "is_active",
            "unread_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_participant(self, obj):
        request = self.context.get("request")

        if not request or not request.user.is_authenticated:
            return None

        if obj.sender_id == request.user.id:
            other_user = obj.traveler
        else:
            other_user = obj.sender

        return ChatParticipantSerializer(other_user).data

    def get_unread_count(self, obj):
        request = self.context.get("request")

        if not request or not request.user.is_authenticated:
            return 0

        return obj.messages.filter(
            receiver=request.user,
            is_read=False,
            is_deleted=False,
        ).count()

    def get_last_message_type(self, obj):
        last_message = obj.messages.order_by("-created_at").only(
            "message_type"
        ).first()

        if last_message:
            return last_message.message_type

        return None

    def get_last_message_sender(self, obj):
        last_message = obj.messages.order_by("-created_at").only(
            "sender_id"
        ).first()

        if last_message:
            return str(last_message.sender_id)

        return None



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
        max_size = 20 * 1024 * 1024

        if value.size > max_size:
            raise serializers.ValidationError(
                "Maximum upload size is 20MB."
            )

        ext = os.path.splitext(value.name)[1].lower()

        allowed = [
            ".jpg", ".jpeg", ".png", ".gif", ".webp",
            ".pdf", ".doc", ".docx",
            ".xls", ".xlsx",
            ".zip",
            ".mp4", ".mov", ".avi",
            ".mp3", ".wav", ".aac",
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
                {"attachment": "Attachment is required."}
            )

        return attrs