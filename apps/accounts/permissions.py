from rest_framework.permissions import BasePermission


class IsUserAllowed(BasePermission):

    message = "Your account is suspended or banned."

    def has_permission(self, request, view):

        user = request.user

        if not user.is_authenticated:
            return False

        try:

            moderation = user.moderation_profile

            moderation.check_suspension_status()

            if moderation.is_banned:
                return False

            if moderation.is_suspended:
                return False

        except Exception:
            pass

        return True