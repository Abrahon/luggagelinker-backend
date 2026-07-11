import json
from django.utils import timezone
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

from .models import ChatRoom, ChatMessage
from django.utils import timezone
from .models import ChatRoom, ChatMessage

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_id = self.scope["url_route"]["kwargs"]["room_id"]
        self.room_group_name = f"chat_{self.room_id}"
        self.user = self.scope.get("user")

        # 1. Gatekeeper authentication check
        if not self.user or self.user.is_anonymous:
            await self.close(code=4003)
            return

        # 2. Optimized membership verification (Bypasses booking relations)
        is_authorized = await self.verify_room_membership()
        if not is_authorized:
            await self.close(code=4003)
            return

        # 3. Join the Channels room group stream
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        # 4. Handle read receipts immediately upon arrival
        unread_updated = await self.mark_messages_as_read()
        if unread_updated:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "chat_broadcast",
                    "event": "read",
                    "data": {
                        "reader_id": str(self.user.id),
                        "room_id": self.room_id
                    }
                }
            )

    async def disconnect(self, close_code):
        # Graceful leave without dropping database presence stamps
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        """
        Receives WebSocket frames from the frontend client and routes them 
        based on structural event patterns.
        """
        try:
            payload = json.loads(text_data)
            event_type = payload.get("event")
            event_data = payload.get("data", {})
        except (json.JSONDecodeError, TypeError):
            return

        # Handle outgoing text message events
        if event_type == "message":
            message_text = event_data.get("message", "").strip()
            if not message_text:
                return

            # Save the text payload straight to Postgres
            msg_obj, receiver_id = await self.save_chat_message(
                message=message_text,
                msg_type=ChatMessage.MessageType.TEXT
            )

            # Broadcast message object down to all active channel peers
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "chat_broadcast",
                    "event": "message",
                    "data": {
                        "id": str(msg_obj.id),
                        "room_id": self.room_id,
                        "sender_id": str(self.user.id),
                        "receiver_id": str(receiver_id),
                        "message": msg_obj.message,
                        "message_type": msg_obj.message_type,
                        "attachment": None,
                        "is_read": msg_obj.is_read,
                        "is_deleted": msg_obj.is_deleted,
                        "created_at": msg_obj.created_at.isoformat(),
                    }
                }
            )

        # Handle transient typing events (No database tracking needed)
        elif event_type == "typing":
            is_typing = bool(event_data.get("is_typing", False))
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "chat_broadcast",
                    "event": "typing",
                    "data": {
                        "user_id": str(self.user.id),
                        "is_typing": is_typing
                    }
                }
            )

    async def chat_broadcast(self, event):
        """
        Receives structural frame packages sent via channel_layer.group_send
        and forwards them directly to the client socket using unified wrappers.
        """
        await self.send(text_data=json.dumps({
            "event": event["event"],
            "data": event["data"]
        }))

    # --- Database Transaction Layer ---

    @database_sync_to_async
    def verify_room_membership(self) -> bool:
        """Optimized validation. Only pulls essential lookup variables into memory."""
        try:
            room = ChatRoom.objects.only("sender_id", "traveler_id").get(id=self.room_id)
            # Cache active entity variables onto the instance scope for write routing
            self.room_sender_id = room.sender_id
            self.room_traveler_id = room.traveler_id
            return self.user.id in (room.sender_id, room.traveler_id)
        except (ChatRoom.DoesNotExist, ValueError):
            return False

    @database_sync_to_async
    def mark_messages_as_read(self) -> bool:
        """Marks arriving peer payloads as read and returns True if modifications happen."""
        updated_count = ChatMessage.objects.filter(
            room_id=self.room_id, 
            is_read=False
        ).exclude(
            sender=self.user
        ).update(is_read=True)
        
        return updated_count > 0

    @database_sync_to_async
    def save_chat_message(self, message: str, msg_type: str):
        """Atomic persistence layout for standard text communications."""
        # Derive the targeted receiver instantly based on cached instance keys
        receiver_id = self.room_traveler_id if self.user.id == self.room_sender_id else self.room_sender_id
        
        msg = ChatMessage.objects.create(
            room_id=self.room_id,
            sender=self.user,
            receiver_id=receiver_id,
            message=message,
            message_type=msg_type
        )
        return msg, receiver_id