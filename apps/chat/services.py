from django.db import transaction
from django.core.exceptions import ValidationError

from .models import ChatRoom, ChatMessage


class ChatService:

    @staticmethod
    @transaction.atomic
    def get_or_create_booking_room(booking):
        """
        Get or create the chat room between the sender and traveler.
        """

        # ======================================================
        # 1. VALIDATE PARTICIPANTS
        # ======================================================

        if not booking.sender_id:
            raise ValidationError(
                "Booking sender is required before creating chat room."
            )

        if not booking.traveler_id:
            raise ValidationError(
                "Booking traveler is required before creating chat room."
            )

        # ======================================================
        # 2. CHECK ROOM ALREADY CONNECTED TO THIS BOOKING
        # ======================================================

        room = (
            ChatRoom.objects
            .select_for_update()
            .filter(booking_id=booking.id)
            .first()
        )

        if room:
            if (
                room.sender_id != booking.sender_id
                or room.traveler_id != booking.traveler_id
            ):
                raise ValidationError(
                    "Existing chat room participants do not match the booking."
                )

            if not room.is_active:
                room.is_active = True
                room.save(
                    update_fields=[
                        "is_active",
                        "updated_at",
                    ]
                )

            return room, False

        # ======================================================
        # 3. FIND EXISTING SENDER ↔ TRAVELER CONVERSATION
        # ======================================================

        room = (
            ChatRoom.objects
            .select_for_update()
            .filter(
                sender_id=booking.sender_id,
                traveler_id=booking.traveler_id,
            )
            .order_by("-is_active", "-updated_at")
            .first()
        )

        if room:
            update_fields = []

            if not room.is_active:
                room.is_active = True
                update_fields.append("is_active")

            if room.booking_id != booking.id:
                room.booking = booking
                update_fields.append("booking")

            if update_fields:
                update_fields.append("updated_at")
                room.save(update_fields=update_fields)

            return room, False

        # ======================================================
        # 4. CREATE NEW CONVERSATION
        # ======================================================

        room = ChatRoom.objects.create(
            booking=booking,
            sender_id=booking.sender_id,
            traveler_id=booking.traveler_id,
            is_active=True,
        )

        return room, True

    # ==========================================================
    # CREATE BOOKING REQUEST SYSTEM MESSAGE
    # ==========================================================

    @staticmethod
    @transaction.atomic
    def create_booking_request_message(
        *,
        booking,
        room,
    ):
        from .models import ChatMessage

        sender = booking.sender
        traveler = booking.traveler
        trip = booking.trip
        package = booking.package

        # Get sender's actual profile name
        sender_name = None

        if sender:
            profile = getattr(sender, "profile", None)

            if profile:
                sender_name = getattr(profile, "full_name", None)

            # Fallbacks only if profile name is unavailable
            if not sender_name:
                sender_name = (
                    getattr(sender, "username", None)
                    or getattr(sender, "first_name", None)
                    or getattr(sender, "email", None)
                )

        sender_name = sender_name or "A sender"

        message = (
            f"New booking request from {sender_name}. "
            f"Package: {package.title}. "
            f"Weight: {booking.agreed_weight_kg} kg. "
            f"Route: {trip.from_city} → {trip.to_city}. "
            f"Please review the booking request."
        )

        chat_message = ChatMessage.objects.create(
            room=room,
            sender=sender,
            receiver=traveler,
            message=message,
            message_type=ChatMessage.MessageType.SYSTEM,
            is_delivered=False,
            is_read=False,
        )

        return chat_message