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

django_asgi_app = get_asgi_application()

from apps.chat.middleware import JWTQueryAuthMiddleware
from apps.chat.routing import websocket_urlpatterns as chat_urls
from apps.notifications.routing import websocket_urlpatterns as notification_urls

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": JWTQueryAuthMiddleware(
            URLRouter(
                chat_urls + notification_urls
            )
        ),
    }
)