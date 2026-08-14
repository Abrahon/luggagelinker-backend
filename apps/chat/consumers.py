# import json

# from channels.db import database_sync_to_async
# from channels.generic.websocket import AsyncWebsocketConsumer

# from .models import ChatRoom, ChatMessage
# from django.db.models import Count

# import json
# from channels.db import database_sync_to_async
# import logging

# logger = logging.getLogger(__name__)
# from django.utils import timezone
# from channels.db import database_sync_to_async
# from channels.generic.websocket import AsyncWebsocketConsumer
# from .models import ChatRoom, ChatMessage,PinnedMessage

# from apps.notifications.services import create_chat_notification
# from django.contrib.auth import get_user_model
# User = get_user_model()


# class ChatConsumer(AsyncWebsocketConsumer):

#     async def connect(self):
#         self.room_id = str(self.scope["url_route"]["kwargs"]["room_id"])
#         self.room_group_name = f"chat_{self.room_id}"
#         self.presence_group_name = f"presence_{self.room_id}"
#         self.user = self.scope.get("user")

#         if not self.user or self.user.is_anonymous:
#             await self.close(code=4003)
#             return

#         is_authorized = await self.verify_room_membership()
#         if not is_authorized:
#             await self.close(code=4003)
#             return

#         await self.channel_layer.group_add(
#             self.room_group_name,
#             self.channel_name,
#         )
#         await self.channel_layer.group_add(
#             self.presence_group_name,
#             self.channel_name,
#         )
        
#         await self.accept()

#         # ==================== PRESENCE UPDATE: MULTI-TAB ONLINE ====================
#         connection_count = await self.increment_user_connection()

#         if connection_count == 1:
#             await self.set_user_presence("online")

#             await self.channel_layer.group_send(
#                 self.presence_group_name,
#                 {
#                     "type": "presence_event",
#                     "user_id": str(self.user.id),
#                     "status": "online",
#                 },
#             )

#         # 3. Send current room partner's presence directly to THIS newly connected user
#         other_user_id, partner_online = await self.get_partner_presence_info()
#         if other_user_id:
#             await self.send(
#                 text_data=json.dumps(
#                     {
#                         "event": "presence",
#                         "data": {
#                             "user_id": str(other_user_id),
#                             "status": "online" if partner_online else "offline",
#                         },
#                     }
#                 )
#             )

#         read_message_ids = await self.mark_messages_as_read()
#         if read_message_ids:
#             await self.channel_layer.group_send(
#                 self.room_group_name,
#                 {
#                     "type": "read_receipt_event",
#                     "reader_id": str(self.user.id),
#                     "message_ids": read_message_ids,
#                 },
#             )

#         unread_count = await self.get_unread_count()

#         await self.send(
#             text_data=json.dumps({
#                 "event": "unread_count",
#                 "data": {
#                     "count": unread_count,
#                 },
#             })
#         )


#     # async def disconnect(self, close_code):
#     #         # ==================== PRESENCE UPDATE: MULTI-TAB OFFLINE ====================
#     #         if hasattr(self, "user") and self.user and not self.user.is_anonymous:
#     #             # Decrement active connections count
#     #             connection_count = await self.decrement_user_connection()

#     #             # Broadcast "offline" ONLY if all tabs/devices for this user are closed
#     #             if connection_count <= 0:
#     #                 await self.set_user_presence(status="offline")
#     #                 if hasattr(self, "presence_group_name"):
#     #                     await self.channel_layer.group_send(
#     #                         self.presence_group_name,
#     #                         {
#     #                             "type": "presence_event",
#     #                             "user_id": str(self.user.id),
#     #                             "status": "offline",
#     #                         },
#     #                     )

#     #         if hasattr(self, "presence_group_name"):
#     #             await self.set_user_presence(status="offline")
#     #             await self.channel_layer.group_send(
#     #                 self.presence_group_name,
#     #                 {
#     #                     "type": "presence_event",
#     #                     "user_id": str(self.user.id),
#     #                     "status": "offline"
#     #                 }
#     #             )
#     #             await self.channel_layer.group_discard(
#     #                 self.presence_group_name,
#     #                 self.channel_name,
#     #             )

#     #         if hasattr(self, "room_group_name"):
#     #             await self.channel_layer.group_discard(
#     #                 self.room_group_name,
#     #                 self.channel_name,
#     #             )


#     async def disconnect(self, close_code):

#         # ======================================================
#         # PRESENCE UPDATE: MULTI-TAB / MULTI-DEVICE
#         # ======================================================

#         if hasattr(self, "user") and self.user and not self.user.is_anonymous:

#             connection_count = await self.decrement_user_connection()

#             # Only mark offline when ALL connections are closed
#             if connection_count <= 0:

#                 await self.set_user_presence(
#                     status="offline"
#                 )

#                 if hasattr(self, "presence_group_name"):
#                     await self.channel_layer.group_send(
#                         self.presence_group_name,
#                         {
#                             "type": "presence_event",
#                             "user_id": str(self.user.id),
#                             "status": "offline",
#                         },
#                     )

#         # ======================================================
#         # REMOVE FROM PRESENCE GROUP
#         # ======================================================

#         if hasattr(self, "presence_group_name"):
#             await self.channel_layer.group_discard(
#                 self.presence_group_name,
#                 self.channel_name,
#             )

#         # ======================================================
#         # REMOVE FROM CHAT ROOM
#         # ======================================================

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

#        # recive a message 
#         if event == "message":
#             message = data.get("message", "").strip()
#             msg_type = data.get("message_type", ChatMessage.MessageType.TEXT)
#             attachment_url = data.get("attachment", None)
#             reply_to = data.get("reply_to")
#             audio_duration = data.get("audio_duration", 0)

#             if not message and not attachment_url:
#                 return

#             msg, receiver_id = await self.save_chat_message(
#                 message=message,
#                 msg_type=msg_type,
#                 attachment_url=attachment_url,
#                 reply_to=reply_to,
#                 audio_duration=audio_duration
#             )


#             receiver_unread = await self.get_user_unread_count(receiver_id)

#             await self.channel_layer.group_send(
#                 self.presence_group_name,
#                 {
#                     "type": "unread_count_event",
#                     "user_id": str(receiver_id),
#                     "count": receiver_unread,
#                 },
#             )

#             await self.channel_layer.group_send(
#                 self.room_group_name,
#                 {
#                     "type": "broadcast_wrapper",
#                     "payload": {
#                         "event": "message",
#                         "data": {
#                             "id": str(msg.id),
#                             "room_id": self.room_id,
#                             "sender_id": str(self.user.id),
#                             "receiver_id": str(receiver_id),
#                             "message": msg.message,
#                             "message_type": msg.message_type,
#                             "attachment": (
#                                 msg.attachment.url
#                                 if msg.attachment
#                                 else None
#                             ),
#                             "audio_duration": msg.audio_duration,
                            
#                             "reply_to": (
#                                 {
#                                     "id": str(msg.reply_to.id),
#                                     "message": msg.reply_to.message,
#                                     "sender_id": str(msg.reply_to.sender_id),
#                                     "message_type": msg.reply_to.message_type,
#                                     "audio_duration": msg.audio_duration,
#                                 }
#                                 if msg.reply_to
#                                 else None
#                             ),
                            
#                             "is_read": msg.is_read,
#                             "is_deleted": msg.is_deleted,
#                             "is_edited": msg.edited_at is not None,
#                             "created_at": msg.created_at.isoformat(),
#                             "edited_at": (
#                                 msg.edited_at.isoformat()
#                                 if msg.edited_at
#                                 else None
#                             ),
#                         },
#                     },
#                 },
#             )

#         elif event == "typing":
#             await self.channel_layer.group_send(
#                 self.room_group_name,
#                 {
#                     "type": "broadcast_wrapper",
#                     "payload": {
#                         "event": "typing",
#                         "data": {
#                             "user_id": str(self.user.id),
#                             "is_typing": data.get("is_typing", False)
#                         }
#                     }
#                 }
#             )

#         elif event == "edit_message":
#             message_id = data.get("message_id")
#             new_text = data.get("message", "").strip()
            
#             if not new_text:
#                 return

#             success, updated_at = await self.edit_chat_message(message_id, new_text)
#             if success:
#                 await self.channel_layer.group_send(
#                     self.room_group_name,
#                     {
#                         "type": "broadcast_wrapper",
#                         "payload": {
#                             "event": "edit_message",
#                             "data": {
#                                 "message_id": message_id,
#                                 "message": new_text,
#                                 "is_edited": True,
#                                 "updated_at": updated_at.isoformat()
#                             }
#                         }
#                     }
#                 )

#         elif event == "delete_message":
#             message_id = data.get("message_id")
#             success = await self.delete_chat_message(message_id)
#             if success:
#                 await self.channel_layer.group_send(
#                     self.room_group_name,
#                     {
#                         "type": "broadcast_wrapper",
#                         "payload": {
#                             "event": "delete_message",
#                             "data": {
#                                 "message_id": message_id,
#                                 "is_deleted": True
#                             }
#                         }
#                     }
#                 )
#         elif event == "delivered":
#             message_id = data.get("message_id")
#             success = await self.mark_message_delivered(message_id)

#             if success:
#                 await self.channel_layer.group_send(
#                     self.room_group_name,
#                     {
#                         "type": "delivered_event",
#                         "message_id": message_id,
#                     },
            
#                 )


#         #react message   
#         elif event == "reaction":

#             message_id = data.get("message_id")
#             emoji = data.get("emoji")

#             reaction = await self.add_reaction(
#                 message_id,
#                 emoji,
#             )

#             if reaction:

#                 await self.channel_layer.group_send(
#                     self.room_group_name,
#                     {
#                         "type": "broadcast_wrapper",
#                         "payload": {
#                             "event": "reaction",
#                             "data": reaction,
#                         },
#                     },
#                 )

#         # pin message 
#         elif event == "pin_message":

#             message_id = data.get("message_id")

#             pin = await self.pin_message(message_id)

#             if pin:
#                 await self.channel_layer.group_send(
#                     self.room_group_name,
#                     {
#                         "type": "pin_message_event",
#                         "pin": pin,
#                     },
#                 )

#         # unpin message

#         elif event == "unpin_message":

#             message_id = data.get("message_id")

#             success = await self.unpin_message(message_id)

#             if success:
#                 await self.channel_layer.group_send(
#                     self.room_group_name,
#                     {
#                         "type": "unpin_message_event",
#                         "message_id": message_id,
#                     },
#                 )


#     async def broadcast_wrapper(self, event):
#         await self.send(text_data=json.dumps(event["payload"]))

    
#     async def chat_message(self, event):
#         await self.send(
#             text_data=json.dumps({
#                 "event": "message",
#                 "data": event["message"],
#             })
#         )
    

#     async def typing_event(self, event):
#         await self.send(
#             text_data=json.dumps({
#                 "event": "typing",
#                 "data": {
#                     "user_id": event["user_id"],
#                     "is_typing": event["is_typing"],
#                 },
#             })
#         )

#     async def presence_event(self, event):
#         await self.send(
#             text_data=json.dumps({
#                 "event": "presence",
#                 "data": {
#                     "user_id": event["user_id"],
#                     "status": event["status"]
#                 }
#             })
#         )

#     async def read_receipt_event(self, event):
#         await self.send(
#             text_data=json.dumps({
#                 "event": "read_receipt",
#                 "data": {
#                     "reader_id": event["reader_id"],
#                     "message_ids": event["message_ids"]
#                 }
#             })
#         )

#     async def delivered_event(self, event):
#         await self.send(
#             text_data=json.dumps({
#                 "event": "delivered",
#                 "data": {
#                     "message_id": event["message_id"],
#                 },
#             })
#         )
    
#     async def unread_count_event(self, event):
#             if str(self.user.id) != event["user_id"]:
#                 return
#             await self.send(
#                 text_data=json.dumps({
#                     "event": "unread_count",
#                     "data": {
#                         "count": event["count"],
#                     },
#                 })
#             )
    

#     # pin messaeg 
#     async def pin_message_event(self, event):

#         await self.send(
#             text_data=json.dumps(
#                 {
#                     "event": "pin_message",
#                     "data": event["pin"],
#                 }
#             )
#         )

#     # unpin message
#     async def unpin_message_event(self, event):

#         await self.send(
#             text_data=json.dumps(
#                 {
#                     "event": "unpin_message",
#                     "data": {
#                         "message_id": event["message_id"],
#                     },
#                 }
#             )
#         )

#     @database_sync_to_async
#     def verify_room_membership(self):
#         try:
#             room = ChatRoom.objects.only("sender_id", "traveler_id").get(id=self.room_id)
#             self.room_sender_id = room.sender_id
#             self.room_traveler_id = room.traveler_id
#             return self.user.id in (room.sender_id, room.traveler_id)
#         except ChatRoom.DoesNotExist:
#             return False



#     @database_sync_to_async
#     def save_chat_message(
#         self,
#         message,
#         msg_type,
#         attachment_url=None,
#         reply_to=None,
#         audio_duration=0,
#     ):
#         if self.user.id == self.room_sender_id:
#             receiver_id = self.room_traveler_id
#         else:
#             receiver_id = self.room_sender_id

#         # Load replied message
#         reply_message = None

#         if reply_to:
#             try:
#                 reply_message = ChatMessage.objects.get(
#                     id=reply_to,
#                     room_id=self.room_id,
#                 )
#             except ChatMessage.DoesNotExist:
#                 reply_message = None

#         # Create message
#         msg = ChatMessage.objects.create(
#             room_id=self.room_id,
#             sender=self.user,
#             receiver_id=receiver_id,
#             message=message,
#             message_type=msg_type,
#             attachment=attachment_url,
#             reply_to=reply_message,
#             # Keep only if ChatMessage has this field
#             # audio_duration=audio_duration,
#         )

#         # Get receiver
#         receiver = User.objects.get(
#             id=receiver_id
#         )

#         # Create notification through centralized service
#         create_chat_notification(
#             receiver=receiver,
#             sender=self.user,
#             message=msg.message or "Sent an attachment.",
#             room_id=self.room_id,
#             message_id=msg.id,
#         )

#         return msg, receiver_id

#     @database_sync_to_async
#     def mark_messages_as_read(self):
#         messages = list(
#             ChatMessage.objects.filter(
#                 room_id=self.room_id,
#                 receiver=self.user,
#                 is_read=False,
#             ).only("id")
#         )
#         ids = [str(i.id) for i in messages]
#         if ids:
#             ChatMessage.objects.filter(id__in=ids).update(is_read=True)
#         return ids

#     @database_sync_to_async
#     def edit_chat_message(self, message_id, new_text):
#         try:
#             msg = ChatMessage.objects.get(
#                 id=message_id, 
#                 sender=self.user, 
#                 is_deleted=False
#             )
#             msg.message = new_text
#             msg.is_edited = True
#             msg.updated_at = timezone.now()
#             msg.save(update_fields=["message", "is_edited", "updated_at"])
#             return True, msg.updated_at
#         except ChatMessage.DoesNotExist:
#             return False, None

#     @database_sync_to_async
#     def delete_chat_message(self, message_id):
#         try:
#             msg = ChatMessage.objects.get(
#                 id=message_id,
#                 sender=self.user,
#                 room_id=self.room_id,
#             )
#         except ChatMessage.DoesNotExist:
#             return False

#         # Delete physical file from storage
#         if msg.attachment:
#             try:
#                 msg.attachment.delete(save=False)
#             except Exception:
#                 logger.exception(
#                     "Failed to delete attachment for message %s",
#                     msg.id,
#                 )

#         # Soft delete message
#         msg.is_deleted = True
#         msg.message = ""
#         msg.attachment = None

#         msg.save(
#             update_fields=[
#                 "is_deleted",
#                 "message",
#                 "attachment",
#                 "updated_at",
#             ]
#         )

#         return True

#     @database_sync_to_async
#     def set_user_presence(self, status):
#         from django.contrib.auth import get_user_model
#         User = get_user_model()
#         is_online = True if status == "online" else False
#         User.objects.filter(id=self.user.id).update(is_online=is_online, last_seen=timezone.now())


#     @database_sync_to_async
#     def update_presence(self, online: bool):
#         self.user.is_online = online

#         if not online:
#             self.user.last_seen = timezone.now()

#         self.user.save(
#             update_fields=[
#                 "is_online",
#                 "last_seen",
#             ]
#         )
    

#     @database_sync_to_async
#     def set_user_presence(self, status):
#         self.user.is_online = status == "online"

#         if status == "offline":
#             self.user.last_seen = timezone.now()

#         self.user.save(
#             update_fields=[
#                 "is_online",
#                 "last_seen",
#             ]
#         )
#     @database_sync_to_async
#     def mark_message_delivered(self, message_id):
#         try:
#             msg = ChatMessage.objects.get(id=message_id)

#             if not msg.is_delivered:
#                 msg.is_delivered = True
#                 msg.delivered_at = timezone.now()
#                 msg.save(update_fields=[
#                     "is_delivered",
#                     "delivered_at",
#                 ])

#             return True

#         except ChatMessage.DoesNotExist:
#             return False



#     @database_sync_to_async
#     def get_unread_count(self):
#         return ChatMessage.objects.filter(
#             receiver=self.user,
#             is_read=False,
#         ).count()


#     @database_sync_to_async
#     def get_user_unread_count(self, user_id):
#         return ChatMessage.objects.filter(
#             receiver_id=user_id,
#             is_read=False,
#         ).count()



#     # react message 
#     @database_sync_to_async
#     def add_reaction(
#         self,
#         message_id,
#         emoji,
#     ):
#         from .models import ChatReaction

#         try:

#             message = ChatMessage.objects.get(
#                 id=message_id,
#                 room_id=self.room_id,
#             )

#             reaction, created = ChatReaction.objects.update_or_create(
#                 message=message,
#                 user=self.user,
#                 defaults={
#                     "emoji": emoji,
#                 },
#             )

#             return {
#                 "message_id": str(message.id),
#                 "user_id": str(self.user.id),
#                 "emoji": emoji,
#             }

#         except ChatMessage.DoesNotExist:
#             return None


# # pin messaeg 
#     @database_sync_to_async
#     def pin_message(self, message_id):

#         try:

#             message = ChatMessage.objects.get(
#                 id=message_id,
#                 room_id=self.room_id,
#             )

#         except ChatMessage.DoesNotExist:
#             return None

#         PinnedMessage.objects.filter(
#             room_id=self.room_id,
#         ).delete()

#         pin = PinnedMessage.objects.create(
#             room_id=self.room_id,
#             message=message,
#             pinned_by=self.user,
#         )

#         return {
#             "id": str(pin.id),
#             "message_id": str(message.id),
#             "message": message.message,
#             "sender_id": str(message.sender_id),
#             "message_type": message.message_type,
#             "attachment": (
#                 message.attachment.url
#                 if message.attachment
#                 else None
#             ),
#             "pinned_by": str(self.user.id),
#             "pinned_at": pin.pinned_at.isoformat(),
#         }


#     # unpin message 
#     @database_sync_to_async
#     def unpin_message(self, message_id):

#         deleted, _ = PinnedMessage.objects.filter(
#             room_id=self.room_id,
#             message_id=message_id,
#         ).delete()

#         return deleted > 0



#     # ==========================================================
#     # MULTI-TAB / MULTI-DEVICE PRESENCE CONNECTION TRACKING
#     # ==========================================================

#         # ==========================================================
#     # CONNECTION COUNT
#     # IMPORTANT: THIS MUST BE INSIDE ChatConsumer
#     # ==========================================================

#     @database_sync_to_async
#     def increment_user_connection(self):
#         """
#         Increment active WebSocket connections for this user.

#         If the user has multiple tabs/devices open, the user
#         remains online until the last connection disconnects.
#         """
#         from django.core.cache import cache

#         key = f"chat_presence_connections:{self.user.id}"

#         try:
#             connection_count = cache.incr(key)
#         except ValueError:
#             cache.set(
#                 key,
#                 1,
#                 timeout=60 * 60 * 24,
#             )
#             connection_count = 1

#         return connection_count

#     @database_sync_to_async
#     def decrement_user_connection(self):
#         """
#         Decrement active WebSocket connections.

#         Returns 0 when the user has no active connections.
#         """
#         from django.core.cache import cache

#         key = f"chat_presence_connections:{self.user.id}"

#         try:
#             connection_count = cache.decr(key)
#         except ValueError:
#             return 0

#         if connection_count <= 0:
#             cache.delete(key)
#             return 0

#         return connection_count

# # voice message



import json
import logging
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from .models import ChatRoom, ChatMessage, PinnedMessage, ChatReaction
from apps.notifications.services import create_chat_notification

logger = logging.getLogger(__name__)
User = get_user_model()


class ChatConsumer(AsyncWebsocketConsumer):

    # =========================================================================
    # WEBSOCKET CONNECT & DISCONNECT
    # =========================================================================

    # async def connect(self):
    #     self.room_id = str(self.scope["url_route"]["kwargs"]["room_id"])
    #     self.room_group_name = f"chat_{self.room_id}"
    #     self.presence_group_name = f"presence_{self.room_id}"
    #     self.user = self.scope.get("user")

    #     # Reject unauthenticated users immediately without joining groups
    #     if not self.user or self.user.is_anonymous:
    #         await self.close(code=4003)
    #         return

    #     is_authorized = await self.verify_room_membership()
    #     if not is_authorized:
    #         await self.close(code=4003)
    #         return

    #     # Accept connection first
    #     await self.accept()

    #     # Join groups AFTER accepting connection
    #     await self.channel_layer.group_add(
    #         self.room_group_name,
    #         self.channel_name,
    #     )
    #     await self.channel_layer.group_add(
    #         self.presence_group_name,
    #         self.channel_name,
    #     )

    #     # 1. Track connection count in Cache
    #     connection_count = await self.increment_user_connection()

    #     # 2. Only broadcast "online" on first active socket connection
    #     if connection_count == 1:
    #         await self.set_user_presence(status="online")
    #         await self.channel_layer.group_send(
    #             self.presence_group_name,
    #             {
    #                 "type": "presence_event",
    #                 "user_id": str(self.user.id),
    #                 "status": "online",
    #             },
    #         )

    #     # 3. Send partner's presence status directly to this client
    #     other_user_id, partner_online = await self.get_partner_presence_info()
    #     if other_user_id:
    #         await self.send(
    #             text_data=json.dumps({
    #                 "event": "presence",
    #                 "data": {
    #                     "user_id": str(other_user_id),
    #                     "status": "online" if partner_online else "offline",
    #                 },
    #             })
    #         )

    #     # 4. Mark unread incoming messages as read
    #     read_message_ids = await self.mark_messages_as_read()
    #     if read_message_ids:
    #         await self.channel_layer.group_send(
    #             self.room_group_name,
    #             {
    #                 "type": "read_receipt_event",
    #                 "reader_id": str(self.user.id),
    #                 "message_ids": read_message_ids,
    #             },
    #         )

    #     # 5. Send unread message count to this client
    #     unread_count = await self.get_unread_count()
    #     await self.send(
    #         text_data=json.dumps({
    #             "event": "unread_count",
    #             "data": {
    #                 "count": unread_count,
    #             },
    #         })
    #     )

    async def connect(self):
        self.room_id = str(self.scope["url_route"]["kwargs"]["room_id"])
        self.room_group_name = f"chat_{self.room_id}"
        self.presence_group_name = f"presence_{self.room_id}"
        self.user = self.scope.get("user")

        # 🔍 DEBUG LOGS
        logger.info(f"--- WS CONNECT ATTEMPT --- Room: {self.room_id} | User: {self.user}")

        if not self.user or self.user.is_anonymous:
            logger.error("WS REJECTED: User is Anonymous or missing from scope")
            await self.close(code=4003)
            return


        is_authorized = await self.verify_room_membership()
        if not is_authorized:
            logger.error(f"WS REJECTED: User {self.user.id} not authorized for room {self.room_id}")
            await self.close(code=4003)
            return

        await self.accept()
    # ... rest of connect ...
    async def disconnect(self, close_code):
        # 1. ALWAYS remove channel from groups FIRST to prevent channel leaks
        if hasattr(self, "presence_group_name"):
            await self.channel_layer.group_discard(
                self.presence_group_name,
                self.channel_name,
            )

        if hasattr(self, "room_group_name"):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name,
            )

        # 2. Manage user presence count
        if hasattr(self, "user") and self.user and not self.user.is_anonymous:
            connection_count = await self.decrement_user_connection()

            # Broadcast "offline" ONLY if all tabs/devices are closed
            if connection_count <= 0:
                await self.set_user_presence(status="offline")
                if hasattr(self, "presence_group_name"):
                    await self.channel_layer.group_send(
                        self.presence_group_name,
                        {
                            "type": "presence_event",
                            "user_id": str(self.user.id),
                            "status": "offline",
                        },
                    )

    # =========================================================================
    # WEBSOCKET RECEIVE ROUTER
    # =========================================================================

    async def receive(self, text_data):
        try:
            payload = json.loads(text_data)
        except json.JSONDecodeError:
            return

        event = payload.get("event")
        data = payload.get("data", {})

        # --- Send Message ---
        if event == "message":
            message = data.get("message", "").strip()
            msg_type = data.get("message_type", ChatMessage.MessageType.TEXT)
            attachment_url = data.get("attachment", None)
            reply_to = data.get("reply_to")
            audio_duration = data.get("audio_duration", 0)

            if not message and not attachment_url:
                return

            msg, receiver_id = await self.save_chat_message(
                message=message,
                msg_type=msg_type,
                attachment_url=attachment_url,
                reply_to=reply_to,
                audio_duration=audio_duration,
            )

            receiver_unread = await self.get_user_unread_count(receiver_id)

            await self.channel_layer.group_send(
                self.presence_group_name,
                {
                    "type": "unread_count_event",
                    "user_id": str(receiver_id),
                    "count": receiver_unread,
                },
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
                            "attachment": (
                                msg.attachment.url if msg.attachment else None
                            ),
                            "audio_duration": msg.audio_duration,
                            "reply_to": (
                                {
                                    "id": str(msg.reply_to.id),
                                    "message": msg.reply_to.message,
                                    "sender_id": str(msg.reply_to.sender_id),
                                    "message_type": msg.reply_to.message_type,
                                    "audio_duration": msg.reply_to.audio_duration,
                                }
                                if msg.reply_to
                                else None
                            ),
                            "is_read": msg.is_read,
                            "is_deleted": msg.is_deleted,
                            "is_edited": msg.edited_at is not None,
                            "created_at": msg.created_at.isoformat(),
                            "edited_at": (
                                msg.edited_at.isoformat()
                                if msg.edited_at
                                else None
                            ),
                        },
                    },
                },
            )

        # --- Typing Indicator ---
        elif event == "typing":
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "broadcast_wrapper",
                    "payload": {
                        "event": "typing",
                        "data": {
                            "user_id": str(self.user.id),
                            "is_typing": data.get("is_typing", False),
                        },
                    },
                },
            )

        # --- Edit Message ---
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
                                "updated_at": updated_at.isoformat(),
                            },
                        },
                    },
                )

        # --- Delete Message ---
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
                                "is_deleted": True,
                            },
                        },
                    },
                )

        # --- Message Delivered ---
        elif event == "delivered":
            message_id = data.get("message_id")
            success = await self.mark_message_delivered(message_id)

            if success:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "delivered_event",
                        "message_id": message_id,
                    },
                )

        # --- Add Reaction ---
        elif event == "reaction":
            message_id = data.get("message_id")
            emoji = data.get("emoji")

            reaction = await self.add_reaction(message_id, emoji)

            if reaction:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "broadcast_wrapper",
                        "payload": {
                            "event": "reaction",
                            "data": reaction,
                        },
                    },
                )

        # --- Pin Message ---
        elif event == "pin_message":
            message_id = data.get("message_id")
            pin = await self.pin_message(message_id)

            if pin:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "pin_message_event",
                        "pin": pin,
                    },
                )

        # --- Unpin Message ---
        elif event == "unpin_message":
            message_id = data.get("message_id")
            success = await self.unpin_message(message_id)

            if success:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "unpin_message_event",
                        "message_id": message_id,
                    },
                )

    # =========================================================================
    # EVENT HANDLERS FOR BROADCASTING TO CLIENT
    # =========================================================================

    async def broadcast_wrapper(self, event):
        await self.send(text_data=json.dumps(event["payload"]))

    async def chat_message(self, event):
        await self.send(
            text_data=json.dumps({
                "event": "message",
                "data": event["message"],
            })
        )

    async def typing_event(self, event):
        await self.send(
            text_data=json.dumps({
                "event": "typing",
                "data": {
                    "user_id": event["user_id"],
                    "is_typing": event["is_typing"],
                },
            })
        )

    async def presence_event(self, event):
        await self.send(
            text_data=json.dumps({
                "event": "presence",
                "data": {
                    "user_id": event["user_id"],
                    "status": event["status"],
                },
            })
        )

    async def read_receipt_event(self, event):
        await self.send(
            text_data=json.dumps({
                "event": "read_receipt",
                "data": {
                    "reader_id": event["reader_id"],
                    "message_ids": event["message_ids"],
                },
            })
        )

    async def delivered_event(self, event):
        await self.send(
            text_data=json.dumps({
                "event": "delivered",
                "data": {
                    "message_id": event["message_id"],
                },
            })
        )

    async def unread_count_event(self, event):
        if str(self.user.id) != event["user_id"]:
            return
        await self.send(
            text_data=json.dumps({
                "event": "unread_count",
                "data": {
                    "count": event["count"],
                },
            })
        )

    async def pin_message_event(self, event):
        await self.send(
            text_data=json.dumps({
                "event": "pin_message",
                "data": event["pin"],
            })
        )

    async def unpin_message_event(self, event):
        await self.send(
            text_data=json.dumps({
                "event": "unpin_message",
                "data": {
                    "message_id": event["message_id"],
                },
            })
        )

    # =========================================================================
    # DATABASE & CACHE HELPER METHODS
    # =========================================================================

    @database_sync_to_async
    def increment_user_connection(self):
        key = f"chat_presence_connections:{self.user.id}"
        try:
            connection_count = cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=60 * 60 * 24)
            connection_count = 1
        return connection_count

    @database_sync_to_async
    def decrement_user_connection(self):
        key = f"chat_presence_connections:{self.user.id}"
        try:
            connection_count = cache.decr(key)
        except ValueError:
            return 0

        if connection_count <= 0:
            cache.delete(key)
            return 0

        return connection_count

    @database_sync_to_async
    def get_partner_presence_info(self):
        try:
            room = ChatRoom.objects.only("sender_id", "traveler_id").get(id=self.room_id)
            other_user_id = (
                room.traveler_id if str(self.user.id) == str(room.sender_id) else room.sender_id
            )
            partner = User.objects.only("is_online").get(id=other_user_id)
            return str(other_user_id), partner.is_online
        except (ChatRoom.DoesNotExist, User.DoesNotExist):
            return None, False

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
    def set_user_presence(self, status):
        is_online = status == "online"
        kwargs = {"is_online": is_online}
        if not is_online:
            kwargs["last_seen"] = timezone.now()
        User.objects.filter(id=self.user.id).update(**kwargs)

    @database_sync_to_async
    def save_chat_message(
        self,
        message,
        msg_type,
        attachment_url=None,
        reply_to=None,
        audio_duration=0,
    ):
        receiver_id = (
            self.room_traveler_id if self.user.id == self.room_sender_id else self.room_sender_id
        )

        reply_message = None
        if reply_to:
            try:
                reply_message = ChatMessage.objects.get(
                    id=reply_to,
                    room_id=self.room_id,
                )
            except ChatMessage.DoesNotExist:
                reply_message = None

        msg = ChatMessage.objects.create(
            room_id=self.room_id,
            sender=self.user,
            receiver_id=receiver_id,
            message=message,
            message_type=msg_type,
            attachment=attachment_url,
            reply_to=reply_message,
            audio_duration=audio_duration,
        )

        try:
            receiver = User.objects.get(id=receiver_id)
            create_chat_notification(
                receiver=receiver,
                sender=self.user,
                message=msg.message or "Sent an attachment.",
                room_id=self.room_id,
                message_id=msg.id,
            )
        except Exception:
            logger.exception("Failed to send chat notification")

        return msg, receiver_id

    @database_sync_to_async
    def mark_messages_as_read(self):
        messages = list(
            ChatMessage.objects.filter(
                room_id=self.room_id,
                receiver=self.user,
                is_read=False,
            ).values_list("id", flat=True)
        )
        ids = [str(m_id) for m_id in messages]
        if ids:
            ChatMessage.objects.filter(id__in=ids).update(is_read=True)
        return ids

    @database_sync_to_async
    def edit_chat_message(self, message_id, new_text):
        try:
            msg = ChatMessage.objects.get(
                id=message_id,
                sender=self.user,
                is_deleted=False,
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
            msg = ChatMessage.objects.get(
                id=message_id,
                sender=self.user,
                room_id=self.room_id,
            )
        except ChatMessage.DoesNotExist:
            return False

        # Safely delete attachment file
        if msg.attachment:
            try:
                msg.attachment.delete(save=False)
            except Exception:
                logger.exception("Failed to delete attachment for message %s", msg.id)

        # Soft delete
        msg.is_deleted = True
        msg.message = ""
        msg.attachment = None

        # REMOVED 'updated_at' to prevent FieldError crash
        msg.save(
            update_fields=[
                "is_deleted",
                "message",
                "attachment",
            ]
        )

        return True


    @database_sync_to_async
    def mark_message_delivered(self, message_id):
        try:
            msg = ChatMessage.objects.get(id=message_id)
            if not msg.is_delivered:
                msg.is_delivered = True
                msg.delivered_at = timezone.now()
                msg.save(update_fields=["is_delivered", "delivered_at"])
            return True
        except ChatMessage.DoesNotExist:
            return False

    @database_sync_to_async
    def get_unread_count(self):
        return ChatMessage.objects.filter(
            receiver=self.user,
            is_read=False,
        ).count()

    @database_sync_to_async
    def get_user_unread_count(self, user_id):
        return ChatMessage.objects.filter(
            receiver_id=user_id,
            is_read=False,
        ).count()

    @database_sync_to_async
    def add_reaction(self, message_id, emoji):
        try:
            message = ChatMessage.objects.get(
                id=message_id,
                room_id=self.room_id,
            )
            ChatReaction.objects.update_or_create(
                message=message,
                user=self.user,
                defaults={"emoji": emoji},
            )
            return {
                "message_id": str(message.id),
                "user_id": str(self.user.id),
                "emoji": emoji,
            }
        except ChatMessage.DoesNotExist:
            return None

    @database_sync_to_async
    def pin_message(self, message_id):
        try:
            message = ChatMessage.objects.get(
                id=message_id,
                room_id=self.room_id,
            )
        except ChatMessage.DoesNotExist:
            return None

        PinnedMessage.objects.filter(room_id=self.room_id).delete()

        pin = PinnedMessage.objects.create(
            room_id=self.room_id,
            message=message,
            pinned_by=self.user,
        )

        return {
            "id": str(pin.id),
            "message_id": str(message.id),
            "message": message.message,
            "sender_id": str(message.sender_id),
            "message_type": message.message_type,
            "attachment": (
                message.attachment.url if message.attachment else None
            ),
            "pinned_by": str(self.user.id),
            "pinned_at": pin.pinned_at.isoformat(),
        }

    @database_sync_to_async
    def unpin_message(self, message_id):
        deleted, _ = PinnedMessage.objects.filter(
            room_id=self.room_id,
            message_id=message_id,
        ).delete()
        return deleted > 0
