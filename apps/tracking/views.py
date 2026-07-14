from django.shortcuts import render

# Create your views here.
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from .models import ActiveTracker, LocationHistory, TrackingStatus
from .serializers import ActiveTrackerSerializer, LocationHistorySerializer
from apps.chat.models import ChatRoom


class ActiveTrackerCreateView(generics.CreateAPIView):
    """
    POST /api/tracking/start/
    Initializes a tracking session for a room. Restricts initiation to room participants.
    """
    serializer_class = ActiveTrackerSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        room = serializer.validated_data["room"]

        # 1. Enforcement: Must be a participant of the room
        if self.request.user.id not in [room.sender_id, room.traveler_id]:
            raise PermissionDenied("You are not authorized to start tracking for this room.")

        # 2. Enforcement: Prevent overlapping tracking sessions for the same room
        if ActiveTracker.objects.filter(room=room, status=TrackingStatus.STARTED).exists():
            raise ValidationError({"room": "An active tracking session is already underway for this room."})

        serializer.save(
            tracker_user=self.request.user,
            status=TrackingStatus.STARTED
        )


class ActiveTrackerRetrieveView(generics.RetrieveAPIView):
    """
    GET /api/tracking/<uuid:room_id>/
    Pulls the current tracker details along with inline history points.
    """
    serializer_class = ActiveTrackerSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "room_id"

    def get_object(self):
        # Fetch the room first to verify permissions securely
        room = get_object_or_404(ChatRoom, id=self.kwargs["room_id"])

        if self.request.user.id not in [room.sender_id, room.traveler_id]:
            raise PermissionDenied("You do not have permission to view this tracking session.")

        # Removed tracker_user__profile to prevent schema crashes since data lives directly on the User model
        return get_object_or_404(
            ActiveTracker.objects.select_related("tracker_user", "room"),
            room=room
        )


class LocationHistoryListView(generics.ListAPIView):
    """
    GET /api/tracking/<uuid:tracker_id>/history/
    Returns the complete list of logged coordinates for map replay functionality.
    """
    serializer_class = LocationHistorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Fetch tracker and join its room to verify membership in a single query
        tracker = get_object_or_404(
            ActiveTracker.objects.select_related("room"), 
            id=self.kwargs["tracker_id"]
        )
        room = tracker.room

        if self.request.user.id not in [room.sender_id, room.traveler_id]:
            raise PermissionDenied("You do not have access to this tracking session's history.")

        return LocationHistory.objects.filter(tracker=tracker)