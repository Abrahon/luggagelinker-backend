"""
ASGI config for core project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

# import os

# from django.core.asgi import get_asgi_application

# os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

# application = get_asgi_application()

import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

# 🚨 CRITICAL: Initialize the HTTP ASGI application handler BEFORE importing consumers/routing
# This ensures all standard models and system settings load properly in memory first.
django_asgi_app = get_asgi_application()

# Now safe to import your custom middleware and routes
from apps.chat.middleware import JWTQueryAuthMiddleware
from apps.chat.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    # Handles normal HTTP REST requests
    "http": django_asgi_app,
    
    # Handles persistent WebSocket connections with token security
    "websocket": JWTQueryAuthMiddleware(
        URLRouter(
            websocket_urlpatterns  # 💡 The missing argument is now supplied here!
        )
    ),
})
