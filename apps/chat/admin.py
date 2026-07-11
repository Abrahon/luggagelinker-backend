from django.contrib import admin
from .models import ChatRoom, ChatMessage


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    fields = (
        "sender",
        "receiver",
        "message_type",
        "message",
        "attachment",
        "is_read",
        "is_deleted",
        "created_at",
    )
    readonly_fields = (
        "sender",
        "receiver",
        "message_type",
        "message",
        "attachment",
        "is_read",
        "is_deleted",
        "created_at",
    )
    ordering = ("created_at",)
    can_delete = False


@admin.register(ChatRoom)
class ChatRoomAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "booking",
        "sender",
        "traveler",
        "last_message_preview",
        "last_message_at",
        "is_active",
        "created_at",
    )

    list_filter = (
        "is_active",
        "created_at",
    )

    search_fields = (
        "booking__tracking_number",
        "sender__email",
        "sender__first_name",
        "sender__last_name",
        "traveler__email",
        "traveler__first_name",
        "traveler__last_name",
    )

    readonly_fields = (
        "id",
        "booking",
        "sender",
        "traveler",
        "last_message",
        "last_message_at",
        "created_at",
        "updated_at",
    )

    inlines = [ChatMessageInline]

    ordering = ("-last_message_at",)

    def last_message_preview(self, obj):
        if len(obj.last_message) > 50:
            return obj.last_message[:50] + "..."
        return obj.last_message

    last_message_preview.short_description = "Last Message"


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "room",
        "sender",
        "receiver",
        "message_type",
        "short_message",
        "is_read",
        "is_deleted",
        "created_at",
    )

    list_filter = (
        "message_type",
        "is_read",
        "is_deleted",
        "created_at",
    )

    search_fields = (
        "message",
        "sender__email",
        "receiver__email",
        "room__booking__tracking_number",
    )

    readonly_fields = (
        "id",
        "room",
        "sender",
        "receiver",
        "message",
        "attachment",
        "message_type",
        "is_read",
        "is_deleted",
        "edited_at",
        "created_at",
    )

    ordering = ("-created_at",)

    def short_message(self, obj):
        if obj.message_type == ChatMessage.MessageType.IMAGE:
            return "📷 Image"

        if obj.is_deleted:
            return "Deleted"

        if len(obj.message) > 50:
            return obj.message[:50] + "..."

        return obj.message

    short_message.short_description = "Message"