from django.db import transaction
from django.core.exceptions import ValidationError

from .models import ChatRoom


class ChatService:

    @staticmethod
    def get_or_create_booking_room(booking):
        """
        Get or create the chat room for a booking.

        One booking = exactly one chat room.
        """

        if not booking.sender_id:
            raise ValidationError("Booking sender is required.")

        if not booking.traveler_id:
            raise ValidationError("Booking traveler is required.")

        room, created = ChatRoom.objects.get_or_create(
            booking=booking,
            defaults={
                "sender_id": booking.sender_id,
                "traveler_id": booking.traveler_id,
                "is_active": True,
            },
        )

        # Safety check in case an old/inconsistent room exists.
        if (
            room.sender_id != booking.sender_id
            or room.traveler_id != booking.traveler_id
        ):
            raise ValidationError(
                "Chat room participants do not match the booking."
            )

        return room, created