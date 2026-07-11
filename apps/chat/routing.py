from django.urls import path
from .consumers import ChatConsumer

websocket_urlpatterns = [
    # Enforces explicit UUID format verification parameters directly at the socket handshake
    path("ws/chat/room/<uuid:room_id>/", ChatConsumer.as_asgi()),
]