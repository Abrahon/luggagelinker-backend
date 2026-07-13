from django.shortcuts import render

# Create your views here.


from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.generics import ListAPIView
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import IsAuthenticated

from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.parsers import FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import ChatRoom
from .models import ChatMessage
from .serializers import ChatFileUploadSerializer
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



class ChatFileUploadView(APIView):

    permission_classes = [IsAuthenticated]

    parser_classes = [
        MultiPartParser,
        FormParser,
    ]

    def post(self, request):

        serializer = ChatFileUploadSerializer(
            data=request.data
        )

        serializer.is_valid(raise_exception=True)

        room = serializer.validated_data["room"]

        if request.user.id not in (
            room.sender_id,
            room.traveler_id,
        ):
            return Response(
                {
                    "detail": "You are not a participant of this room."
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if request.user.id == room.sender_id:
            receiver_id = room.traveler_id
        else:
            receiver_id = room.sender_id

        message = ChatMessage.objects.create(
            room=room,
            sender=request.user,
            receiver_id=receiver_id,
            message=serializer.validated_data.get(
                "message",
                "",
            ),
            message_type=serializer.validated_data["message_type"],
            attachment=serializer.validated_data["attachment"],
        )

        return Response(
            {
                "id": str(message.id),
                "room_id": str(room.id),
                "sender_id": str(request.user.id),
                "receiver_id": str(receiver_id),
                "message": message.message,
                "message_type": message.message_type,
                "attachment": (
                    request.build_absolute_uri(
                        message.attachment.url
                    )
                    if message.attachment
                    else None
                ),
                "is_read": message.is_read,
                "created_at": message.created_at,
            },
            status=status.HTTP_201_CREATED,
        )