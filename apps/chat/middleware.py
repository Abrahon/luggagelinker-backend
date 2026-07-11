from urllib.parse import parse_qs
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from channels.db import database_sync_to_async
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

User = get_user_model()

@database_sync_to_async
def get_user_from_token(token_string):
    """
    Decodes the JWT access token, verifies its integrity, 
    and securely fetches the associated active user from the database.
    """
    try:
        # Validate signature, structure, and check expiration rules automatically
        access_token = AccessToken(token_string)
        user_id = access_token.get("user_id")
        
        if not user_id:
            return AnonymousUser()
            
        return User.objects.get(id=user_id, is_active=True)
        
    except (InvalidToken, TokenError, User.DoesNotExist):
        # Fallback cleanly to anonymous status if validation fails for any reason
        return AnonymousUser()


class JWTQueryAuthMiddleware:
    """
    Custom ASGI middleware that extracts a user object via an access token 
    passed inside the WebSocket connection query string components.
    
    Example URL format pattern:
    ws://127.0.0.1:8000/ws/chat/room/<uuid:id>/?token=eyJhbGciOiJIUzI...
    """
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        # 1. Extract raw byte parameters from connection scopes safely
        query_string = scope.get("query_string", b"").decode("utf-8")
        query_params = parse_qs(query_string)
        
        # 2. Extract the token value if it exists in the parameter layout
        token = query_params.get("token", [None])[0]
        
        # 3. Inject authenticated user record or AnonymousUser directly into scope
        if token:
            scope["user"] = await get_user_from_token(token)
        else:
            scope["user"] = AnonymousUser()
            
        # 4. Forward execution to the downstream inner routers or consumer nodes
        return await self.inner(scope, receive, send)