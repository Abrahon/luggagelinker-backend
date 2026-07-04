from rest_framework.permissions import BasePermission

class IsPlatformAdmin(BasePermission):
    """Allows access only to authenticated staff users or superusers."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser))