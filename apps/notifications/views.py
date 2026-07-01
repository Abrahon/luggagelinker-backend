from django.shortcuts import render

# Create your views here.
import logging

from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Notification
from .serializers import NotificationSerializer

import logging

from django.db import transaction




logger = logging.getLogger(__name__)


# ===========================================================
# MY NOTIFICATIONS
# ===========================================================

class NotificationListView(generics.ListAPIView):

    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):

        return (
            Notification.objects.filter(
                user=self.request.user,
                is_active=True,
            )
            .order_by("-created_at")
        )

    def list(self, request, *args, **kwargs):

        try:

            queryset = self.get_queryset()

            serializer = self.get_serializer(
                queryset,
                many=True,
            )

            return Response(
                {
                    "success": True,
                    "message": "Notifications retrieved successfully.",
                    "count": queryset.count(),
                    "data": serializer.data,
                },
                status=status.HTTP_200_OK,
            )

        except Exception:

            logger.exception(
                f"Notification list failed. User={request.user.id}"
            )

            return Response(
                {
                    "success": False,
                    "message": "Unable to retrieve notifications.",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )





# ===========================================================
# MARK ALL NOTIFICATIONS AS READ
# ===========================================================

class NotificationReadAllView(generics.GenericAPIView):

    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def patch(self, request, *args, **kwargs):

        try:

            updated_count = (
                Notification.objects.filter(
                    user=request.user,
                    is_active=True,
                    is_read=False,
                )
                .update(
                    is_read=True,
                )
            )

            logger.info(
                f"All notifications marked as read. "
                f"User={request.user.id} "
                f"Updated={updated_count}"
            )

            return Response(
                {
                    "success": True,
                    "message": "All notifications marked as read.",
                    "updated_count": updated_count,
                },
                status=status.HTTP_200_OK,
            )

        except Exception:

            logger.exception(
                f"Failed to mark notifications as read. "
                f"User={request.user.id}"
            )

            return Response(
                {
                    "success": False,
                    "message": "Unable to update notifications.",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )