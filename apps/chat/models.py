from django.db import models

# Create your models here.
import uuid
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
# Assuming a standard third-party storage package integration or simple configuration layout
# from cloudinary.models import CloudinaryField

class ChatRoom(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Structural Integrity (Uniqueness constraint handled via OneToOneField)
    booking = models.OneToOneField(
        "bookings.Booking", 
        on_delete=models.CASCADE, 
        related_name="chat_room"
    )
    
    # Participants
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name="sender_chat_rooms"
    )
    traveler = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name="traveler_chat_rooms"
    )
    
    # Denormalized Fields for Query Optimization (Prevents N+1 database bottlenecks during list fetches)
    last_message = models.TextField(blank=True, default="")
    last_message_at = models.DateTimeField(null=True, blank=True)
    
    # Operational Lifecycle Control Flags
    is_active = models.BooleanField(default=True, help_text=_("Designates whether this conversation is active or archived."))
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_message_at", "-updated_at"]
        indexes = [
            models.Index(fields=["sender", "traveler"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["last_message_at"]),
        ]

    def __str__(self):
        return f"Room {self.id} | Booking {self.booking_id}"


class ChatMessage(models.Model):
    class MessageType(models.TextChoices):
        TEXT = "TEXT", _("Text")
        IMAGE = "IMAGE", _("Image")
        FILE = "FILE", _("File")
        VIDEO = "VIDEO", _("Video")
        AUDIO = "AUDIO", _("Audio")
        SYSTEM = "SYSTEM", _("System")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(
        ChatRoom, 
        on_delete=models.CASCADE, 
        related_name="messages"
    )
    
    # Routing Nodes
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name="sent_messages"
    )
    receiver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_messages",
    )
    
    # Core Payloads
    message = models.TextField(blank=True, default="")
    message_type = models.CharField(
        max_length=10, 
        choices=MessageType.choices, 
        default=MessageType.TEXT
    )
    
    # Cloudinary asset fields default back to standard parameters if string URIs are passed natively
    attachment = models.FileField(
        upload_to="chat_attachments/%Y/%m/", 
        null=True, 
        blank=True
    )
    reply_to = models.ForeignKey(  
    "self",
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="replies",
    )
    # Ephemeral State & Audit Controls
    is_read = models.BooleanField(default=False)
    is_delivered = models.BooleanField(default=False)

    delivered_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    read_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    is_deleted = models.BooleanField(default=False)
    
    edited_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["room", "created_at"]),
            models.Index(fields=["receiver", "is_read"]),
            models.Index(fields=["is_deleted"]),
        ]

    def __str__(self):
        return f"Msg {self.id} | Type: {self.message_type} | Room {self.room_id}"

    def save(self, *args, **kwargs):
        """
        Overwritten save hook to enforce data propagation onto the parent room entry 
        automatically during atomic message insertion events.
        """
        is_new = self._state.adding
        super().save(*args, **kwargs)
        
        # When a new message arrives, instantly updates denormalized fields on the ChatRoom
        if is_new:
            self.room.last_message_at = self.created_at
            if self.is_deleted:
                self.room.last_message = "This message was deleted."
            elif self.message_type == self.MessageType.IMAGE:
                self.room.last_message = "📷 Sent an attachment."
            else:
                self.room.last_message = self.message
            
            # Use update to avoid triggering room save signals recursively
            ChatRoom.objects.filter(id=self.room_id).update(
                last_message=self.room.last_message,
                last_message_at=self.room.last_message_at
            )


class ChatReaction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    message = models.ForeignKey(
        ChatMessage,
        related_name="reactions",
        on_delete=models.CASCADE,
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )

    emoji = models.CharField(max_length=20)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("message", "user")



# message pin

class PinnedMessage(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    room = models.ForeignKey(
        ChatRoom,
        on_delete=models.CASCADE,
        related_name="pinned_messages",
    )

    message = models.ForeignKey(
        ChatMessage,
        on_delete=models.CASCADE,
        related_name="pins",
    )

    pinned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pinned_messages",
    )

    pinned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-pinned_at"]

        constraints = [
            models.UniqueConstraint(
                fields=["room", "message"],
                name="unique_pinned_message_per_room",
            )
        ]

    def __str__(self):
        return f"{self.room_id} -> {self.message_id}"