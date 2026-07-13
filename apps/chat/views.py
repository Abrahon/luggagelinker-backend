from django.shortcuts import render

# Create your views here.


from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.generics import ListAPIView
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import IsAuthenticated

from .models import ChatRoom, ChatMessage
from .serializers import ChatMessageSerializer


class ChatMessagePagination(CursorPagination):
    page_size = 30
    ordering = "-created_at"


class ChatHistoryListView(ListAPIView):
    serializer_class = ChatMessageSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = ChatMessagePagination

    def get_queryset(self):
        room_id = self.kwargs["room_id"]

        room = get_object_or_404(
            ChatRoom.objects.only(
                "id",
                "sender_id",
                "traveler_id",
            ),
            id=room_id,
        )

        if self.request.user.id not in (
            room.sender_id,
            room.traveler_id,
        ):
            return ChatMessage.objects.none()

        return (
            ChatMessage.objects.filter(room=room)
            .select_related("sender", "receiver")
            .order_by("-created_at")
        )