from django.db import transaction
from django.core.exceptions import ValidationError

from .models import ChatRoom


class ChatService:

    @staticmethod
    @transaction.atomic
    def get_or_create_booking_room(booking):
        """
        Get or create a chat room for the sender/traveler pair.

        Business rule:
            One sender + one traveler = ONE chat room.

        Multiple bookings between the same sender and traveler
        reuse the same chat room.
        """

        if not booking.sender_id:
            raise ValidationError(
                "Booking sender is required."
            )

        if not booking.traveler_id:
            raise ValidationError(
                "Booking traveler is required."
            )

        if booking.sender_id == booking.traveler_id:
            raise ValidationError(
                "Sender and traveler cannot be the same user."
            )

        # --------------------------------------------------
        # FIND EXISTING ROOM
        # --------------------------------------------------

        room = (
            ChatRoom.objects
            .select_for_update()
            .filter(
                sender_id=booking.sender_id,
                traveler_id=booking.traveler_id,
            )
            .first()
        )

        # --------------------------------------------------
        # EXISTING ROOM
        # --------------------------------------------------

        if room:
            # Keep the room active when a new booking creates/
            # reuses the conversation.
            if not room.is_active:
                room.is_active = True
                room.save(update_fields=["is_active", "updated_at"])

            # Attach this booking if you want the latest/current
            # booking represented on the room.
            if room.booking_id != booking.id:
                room.booking = booking
                room.save(update_fields=["booking", "updated_at"])

            return room, False

        # --------------------------------------------------
        # CREATE NEW ROOM
        # --------------------------------------------------

        room = ChatRoom.objects.create(
            booking=booking,
            sender_id=booking.sender_id,
            traveler_id=booking.traveler_id,
            is_active=True,
        )

        return room, True