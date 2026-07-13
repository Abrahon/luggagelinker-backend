from django.urls import path

from .views import ChatHistoryListView,ChatFileUploadView

urlpatterns = [
    path("chat/rooms/<uuid:room_id>/messages/",ChatHistoryListView.as_view(),name="chat-history",),
    path( "chat/upload/",ChatFileUploadView.as_view(),name="chat-upload"),
]