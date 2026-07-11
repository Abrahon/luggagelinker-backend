from urllib.parse import parse_qs
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from channels.db import database_sync_to_async
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

User = get_user_model()


@database_sync_to_async
def get_user_from_token(token_string):
    try:
        access_token = AccessToken(token_string)
        user_id = access_token["user_id"]

        return User.objects.get(
            id=user_id,
            is_active=True
        )

    except (InvalidToken, TokenError, User.DoesNotExist):
        return AnonymousUser()


class JWTQueryAuthMiddleware:

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        query_string = scope.get("query_string", b"").decode("utf-8")
        query_params = parse_qs(query_string)

        token = query_params.get("token", [None])[0]

        if token:
            # ✅ THIS WAS MISSING
            scope["user"] = await get_user_from_token(token)
        else:
            scope["user"] = AnonymousUser()

        print("TOKEN:", token)
        print("USER:", scope["user"])

        return await self.inner(scope, receive, send)