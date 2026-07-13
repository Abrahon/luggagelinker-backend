import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from .models import ChatRoom, ChatMessage


# class ChatConsumer(AsyncWebsocketConsumer):

#     async def connect(self):
#         print("STEP 1")

#         self.room_id = str(self.scope["url_route"]["kwargs"]["room_id"])
#         self.room_group_name = f"chat_{self.room_id}"
#         self.user = self.scope.get("user")

#         print("STEP 2", self.user)

#         if not self.user or self.user.is_anonymous:
#             print("Anonymous")
#             await self.close(code=4003)
#             return

#         print("STEP 3")

#         is_authorized = await self.verify_room_membership()

#         print("STEP 4", is_authorized)

#         if not is_authorized:
#             await self.close(code=4003)
#             return

#         print("STEP 5")

#         await self.channel_layer.group_send(
#             self.room_group_name,
#             {
#                 "type": "read_event",
#                 "reader_id": str(self.user.id),
#             },
#         )

#         print("STEP 6")

#         await self.accept()

#         print("STEP 7")

#         await self.mark_messages_as_read()
        

#         print("STEP 8")


#     async def disconnect(self, close_code):
#         if hasattr(self, "room_group_name"):
#             await self.channel_layer.group_discard(
#                 self.room_group_name,
#                 self.channel_name,
#             )

#     async def receive(self, text_data):
#         try:
#             payload = json.loads(text_data)
#         except json.JSONDecodeError:
#             return

#         event = payload.get("event")
#         data = payload.get("data", {})

#         if event == "message":

#             message = data.get("message", "").strip()

#             if not message:
#                 return

#             msg, receiver_id = await self.save_chat_message(
#                 message=message,
#                 msg_type=ChatMessage.MessageType.TEXT,
#             )

#             await self.channel_layer.group_send(
#                 self.room_group_name,
#                 {
#                     "type": "chat_message",
#                     "message": {
#                         "id": str(msg.id),
#                         "room_id": self.room_id,
#                         "sender_id": str(self.user.id),
#                         "receiver_id": str(receiver_id),
#                         "message": msg.message,
#                         "message_type": msg.message_type,
#                         "attachment": (
#                             msg.attachment.url
#                             if msg.attachment else None
#                         ),
#                         "is_read": msg.is_read,
#                         "created_at": msg.created_at.isoformat(),
#                     },
#                 },
#             )

#         elif event == "typing":

#             await self.channel_layer.group_send(
#                 self.room_group_name,
#                 {
#                     "type": "typing_event",
#                     "user_id": str(self.user.id),
#                     "is_typing": data.get("is_typing", False),
#                 },
#             )

#     async def chat_message(self, event):
#         await self.send(
#             text_data=json.dumps(
#                 {
#                     "event": "message",
#                     "data": event["message"],
#                 }
#             )
#         )

#     async def typing_event(self, event):
#         await self.send(
#             text_data=json.dumps(
#                 {
#                     "event": "typing",
#                     "data": {
#                         "user_id": event["user_id"],
#                         "is_typing": event["is_typing"],
#                     },
#                 }
#             )
#         )

#     @database_sync_to_async
#     def verify_room_membership(self):
#         try:
#             room = ChatRoom.objects.only(
#                 "sender_id",
#                 "traveler_id",
#             ).get(id=self.room_id)

#             self.room_sender_id = room.sender_id
#             self.room_traveler_id = room.traveler_id

#             return self.user.id in (
#                 room.sender_id,
#                 room.traveler_id,
#             )

#         except ChatRoom.DoesNotExist:
#             return False

#     @database_sync_to_async
#     def mark_messages_as_read(self):
#         ChatMessage.objects.filter(
#             room_id=self.room_id,
#             receiver=self.user,
#             is_read=False,
#         ).update(is_read=True)
    
    

#     @database_sync_to_async
#     def save_chat_message(self, message, msg_type):

#         if self.user.id == self.room_sender_id:
#             receiver_id = self.room_traveler_id
#         else:
#             receiver_id = self.room_sender_id

#         msg = ChatMessage.objects.create(
#             room_id=self.room_id,
#             sender=self.user,
#             receiver_id=receiver_id,
#             message=message,
#             message_type=msg_type,
#         )

#         return msg, receiver_id

import json
from django.utils import timezone
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from .models import ChatRoom, ChatMessage


class ChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.room_id = str(self.scope["url_route"]["kwargs"]["room_id"])
        self.room_group_name = f"chat_{self.room_id}"
        self.presence_group_name = f"presence_{self.room_id}"
        self.user = self.scope.get("user")

        if not self.user or self.user.is_anonymous:
            await self.close(code=4003)
            return

        is_authorized = await self.verify_room_membership()
        if not is_authorized:
            await self.close(code=4003)
            return

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name,
        )
        await self.channel_layer.group_add(
            self.presence_group_name,
            self.channel_name,
        )
        
        await self.accept()

        await self.set_user_presence(status="online")
        await self.channel_layer.group_send(
            self.presence_group_name,
            {
                "type": "presence_event",
                "user_id": str(self.user.id),
                "status": "online"
            }
        )

        read_message_ids = await self.mark_messages_as_read()
        if read_message_ids:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "read_receipt_event",
                    "reader_id": str(self.user.id),
                    "message_ids": read_message_ids,
                },
            )

    async def disconnect(self, close_code):
        if hasattr(self, "presence_group_name"):
            await self.set_user_presence(status="offline")
            await self.channel_layer.group_send(
                self.presence_group_name,
                {
                    "type": "presence_event",
                    "user_id": str(self.user.id),
                    "status": "offline"
                }
            )
            await self.channel_layer.group_discard(
                self.presence_group_name,
                self.channel_name,
            )

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
            msg_type = data.get("message_type", ChatMessage.MessageType.TEXT)
            attachment_url = data.get("attachment", None)

            if not message and not attachment_url:
                return

            msg, receiver_id = await self.save_chat_message(
                message=message,
                msg_type=msg_type,
                attachment_url=attachment_url
            )

            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "broadcast_wrapper",
                    "payload": {
                        "event": "message",
                        "data": {
                            "id": str(msg.id),
                            "room_id": self.room_id,
                            "sender_id": str(self.user.id),
                            "receiver_id": str(receiver_id),
                            "message": msg.message,
                            "message_type": msg.message_type,
                            "attachment": msg.attachment if hasattr(msg, 'attachment') and msg.attachment else attachment_url,
                            "is_read": msg.is_read,
                            "is_edited": msg.is_edited,
                            "is_deleted": msg.is_deleted,
                            "created_at": msg.created_at.isoformat(),
                            "updated_at": msg.updated_at.isoformat() if msg.updated_at else None,
                        }
                    }
                }
            )

        elif event == "typing":
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "broadcast_wrapper",
                    "payload": {
                        "event": "typing",
                        "data": {
                            "user_id": str(self.user.id),
                            "is_typing": data.get("is_typing", False)
                        }
                    }
                }
            )

        elif event == "edit_message":
            message_id = data.get("message_id")
            new_text = data.get("message", "").strip()
            
            if not new_text:
                return

            success, updated_at = await self.edit_chat_message(message_id, new_text)
            if success:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "broadcast_wrapper",
                        "payload": {
                            "event": "edit_message",
                            "data": {
                                "message_id": message_id,
                                "message": new_text,
                                "is_edited": True,
                                "updated_at": updated_at.isoformat()
                            }
                        }
                    }
                )

        elif event == "delete_message":
            message_id = data.get("message_id")
            success = await self.delete_chat_message(message_id)
            if success:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "broadcast_wrapper",
                        "payload": {
                            "event": "delete_message",
                            "data": {
                                "message_id": message_id,
                                "is_deleted": True
                            }
                        }
                    }
                )

    async def broadcast_wrapper(self, event):
        await self.send(text_data=json.dumps(event["payload"]))

    async def presence_event(self, event):
        await self.send(
            text_data=json.dumps({
                "event": "presence",
                "data": {
                    "user_id": event["user_id"],
                    "status": event["status"]
                }
            })
        )

    async def read_receipt_event(self, event):
        await self.send(
            text_data=json.dumps({
                "event": "read_receipt",
                "data": {
                    "reader_id": event["reader_id"],
                    "message_ids": event["message_ids"]
                }
            })
        )

    @database_sync_to_async
    def verify_room_membership(self):
        try:
            room = ChatRoom.objects.only("sender_id", "traveler_id").get(id=self.room_id)
            self.room_sender_id = room.sender_id
            self.room_traveler_id = room.traveler_id
            return self.user.id in (room.sender_id, room.traveler_id)
        except ChatRoom.DoesNotExist:
            return False

    @database_sync_to_async
    def save_chat_message(self, message, msg_type, attachment_url=None):
        receiver_id = self.room_traveler_id if self.user.id == self.room_sender_id else self.room_sender_id
        
        msg = ChatMessage.objects.create(
            room_id=self.room_id,
            sender=self.user,
            receiver_id=receiver_id,
            message=message,
            message_type=msg_type,
            attachment=attachment_url
        )
        return msg, receiver_id

    @database_sync_to_async
    def mark_messages_as_read(self):
        messages = list(
            ChatMessage.objects.filter(
                room_id=self.room_id,
                receiver=self.user,
                is_read=False,
            ).only("id")
        )
        ids = [str(i.id) for i in messages]
        if ids:
            ChatMessage.objects.filter(id__in=ids).update(is_read=True)
        return ids

    @database_sync_to_async
    def edit_chat_message(self, message_id, new_text):
        try:
            msg = ChatMessage.objects.get(
                id=message_id, 
                sender=self.user, 
                is_deleted=False
            )
            msg.message = new_text
            msg.is_edited = True
            msg.updated_at = timezone.now()
            msg.save(update_fields=["message", "is_edited", "updated_at"])
            return True, msg.updated_at
        except ChatMessage.DoesNotExist:
            return False, None

    @database_sync_to_async
    def delete_chat_message(self, message_id):
        try:
            msg = ChatMessage.objects.get(id=message_id, sender=self.user)
            msg.is_deleted = True
            msg.message = ""
            msg.save(update_fields=["is_deleted", "message"])
            return True
        except ChatMessage.DoesNotExist:
            return False

    @database_sync_to_async
    def set_user_presence(self, status):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        is_online = True if status == "online" else False
        User.objects.filter(id=self.user.id).update(is_online=is_online, last_seen=timezone.now())