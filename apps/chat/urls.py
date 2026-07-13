from django.urls import path

from .views import ChatHistoryListView,ChatFileUploadView, ChatRoomListView

urlpatterns = [
    path("chat/rooms/<uuid:room_id>/messages/",ChatHistoryListView.as_view(),name="chat-history",),
    path("chat/upload/",ChatFileUploadView.as_view(),name="chat-upload"),
    path("chat/rooms/",ChatRoomListView.as_view(),name="chat-room-list" ),
]