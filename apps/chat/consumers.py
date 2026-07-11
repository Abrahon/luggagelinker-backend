import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from .models import ChatRoom, ChatMessage


class ChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.room_id = str(self.scope["url_route"]["kwargs"]["room_id"])
        self.room_group_name = f"chat_{self.room_id}"
        self.user = self.scope.get("user")

        # User must be authenticated
        if not self.user or self.user.is_anonymous:
            await self.close(code=4003)
            return

        # User must belong to this room
        is_authorized = await self.verify_room_membership()

        if not is_authorized:
            await self.close(code=4003)
            return

        # Join websocket group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name,
        )

        await self.accept()

        # Mark unread messages as read
        await self.mark_messages_as_read()

    async def disconnect(self, close_code):
        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name,
            )

    async def receive(self, text_data):
        try:
            payload = json.loads(text_data)
        except json.JSONDecodeError:
            return

        event = payload.get("event")
        data = payload.get("data", {})

        if event == "message":

            message = data.get("message", "").strip()

            if not message:
                return

            msg, receiver_id = await self.save_chat_message(
                message=message,
                msg_type=ChatMessage.MessageType.TEXT,
            )

            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "chat_message",
                    "message": {
                        "id": str(msg.id),
                        "room_id": self.room_id,
                        "sender_id": str(self.user.id),
                        "receiver_id": str(receiver_id),
                        "message": msg.message,
                        "message_type": msg.message_type,
                        "attachment": (
                            msg.attachment.url
                            if msg.attachment else None
                        ),
                        "is_read": msg.is_read,
                        "created_at": msg.created_at.isoformat(),
                    },
                },
            )

        elif event == "typing":

            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "typing_event",
                    "user_id": str(self.user.id),
                    "is_typing": data.get("is_typing", False),
                },
            )

    async def chat_message(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "event": "message",
                    "data": event["message"],
                }
            )
        )

    async def typing_event(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "event": "typing",
                    "data": {
                        "user_id": event["user_id"],
                        "is_typing": event["is_typing"],
                    },
                }
            )
        )

    @database_sync_to_async
    def verify_room_membership(self):
        try:
            room = ChatRoom.objects.only(
                "sender_id",
                "traveler_id",
            ).get(id=self.room_id)

            self.room_sender_id = room.sender_id
            self.room_traveler_id = room.traveler_id

            return self.user.id in (
                room.sender_id,
                room.traveler_id,
            )

        except ChatRoom.DoesNotExist:
            return False

    @database_sync_to_async
    def mark_messages_as_read(self):
        ChatMessage.objects.filter(
            room_id=self.room_id,
            receiver=self.user,
            is_read=False,
        ).update(is_read=True)

    @database_sync_to_async
    def save_chat_message(self, message, msg_type):

        if self.user.id == self.room_sender_id:
            receiver_id = self.room_traveler_id
        else:
            receiver_id = self.room_sender_id

        msg = ChatMessage.objects.create(
            room_id=self.room_id,
            sender=self.user,
            receiver_id=receiver_id,
            message=message,
            message_type=msg_type,
        )

        return msg, receiver_id