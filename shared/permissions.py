from rest_framework.permissions import BasePermission

from shared.constants.roles import UserRole


class IsAdmin(BasePermission):
    message = "You do not have permission to perform this action."

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == UserRole.ADMIN
        )