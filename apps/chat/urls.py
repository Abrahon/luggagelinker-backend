from django.urls import path

from .views import ChatHistoryListView

urlpatterns = [
    path(
        "chat/rooms/<uuid:room_id>/messages/",
        ChatHistoryListView.as_view(),
        name="chat-history",
    ),
]