from django.shortcuts import render

# Create your views here.
import logging
from django.db import models
from django.db.models import Q
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Booking
from .serializers import BookingSerializer, VerifyPickupPinSerializer
from .services import BookingService
from rest_framework.exceptions import ValidationError
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction

from apps.bookings.models import BookingStatus
from apps.notifications.models import Notification, NotificationType

logger = logging.getLogger(__name__)




class BookingCreateView(generics.CreateAPIView):
    """
    API Endpoint to initiate a secure P2P shipping transaction from a Match instance.
    """
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        # Pass request context down directly to handle authority flow checks
        serializer = self.get_serializer(data=request.data, context={"request": request})
        
        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "message": "Invalid booking request parameters.",
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Creation logic drops into Service layer inside serializer.save()
            instance = serializer.save()
            
            return Response(
                {
                    "success": True,
                    "message": "Booking request initialized successfully. Valid for 20 minutes.",
                    "data": self.get_serializer(instance).data,
                },
                status=status.HTTP_201_CREATED,
            )
            
        except Exception as e:
            # Fallback capture if anything drops at low-level runtime execution bounds
            logger.error(f"Critical execution crash inside BookingCreateView: {str(e)}", exc_info=True)
            return Response(
                {
                    "success": False,
                    "message": "An internal system error occurred while setting up the transaction.",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class MyBookingListView(generics.ListAPIView):
    """
    Retrieves all active transactions where the logged-in user acts as Sender or Traveler.
    """
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        
        # High Performance Optimization: Pre-fetch SQL relationships in one clean join
        return Booking.objects.filter(is_active=True).select_related(
            "match",
            "package__sender",
            "trip__traveler"
        ).filter(
            Q(sender=user) | Q(traveler=user)
        ).order_by("-created_at")

    def list(self, request, *args, **kwargs):
        try:
            queryset = self.get_queryset()
            
            if not queryset.exists():
                return Response(
                    {
                        "success": True,
                        "message": "No logistics bookings found.",
                        "data": [],
                    },
                    status=status.HTTP_200_OK,
                )

            # Paginate or stream data array payload cleanly
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = self.get_serializer(queryset, many=True)
            return Response(
                {
                    "success": True,
                    "message": "User dashboard transactions fetched successfully.",
                    "data": serializer.data,
                },
                status=status.HTTP_200_OK,
            )
            
        except Exception as e:
            logger.error(f"Failed to fetch dataset in MyBookingListView: {str(e)}", exc_info=True)
            return Response(
                {
                    "success": False,
                    "message": "Failed to retrieve transaction lists.",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class BookingDetailView(generics.RetrieveAPIView):
    """
    Fetches details of a specific booking instance with security group perimeter checks.
    """
    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "id"

    def get_queryset(self):
        user = self.request.user
        
        # Ensure users can only look up objects belonging directly to them
        return Booking.objects.filter(is_active=True).select_related(
            "match",
            "package__sender",
            "trip__traveler"
        ).filter(
            Q(sender=user) | Q(traveler=user)
        )

    def retrieve(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            
            return Response(
                {
                    "success": True,
                    "message": "Secure transaction details loaded.",
                    "data": serializer.data,
                },
                status=status.HTTP_200_OK,
            )
            
        except Booking.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "The requested booking profile was not found or access is unauthorized.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )


class BookingRespondView(generics.UpdateAPIView):
    """
    Endpoint for travelers to ACCEPT or REJECT an incoming pending booking request.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, id, *args, **kwargs):
        action = request.data.get("action", "").upper()
        if action not in ["ACCEPT", "REJECT"]:
            return Response(
                {"success": False, "message": "Invalid action. Must be 'ACCEPT' or 'REJECT'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            booking = BookingService.respond_to_booking_request(
                booking_id=id,
                traveler=request.user,
                action=action
            )
            return Response({
                "success": True,
                "message": f"Successfully responded to booking request with: {action}.",
                "data": {
                    "tracking_number": booking.tracking_number,
                    "status": booking.status
                }
            }, status=status.HTTP_200_OK)

        except ValidationError as e:
            return Response(
                {"success": False, "message": e.message if hasattr(e, 'message') else str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )



# picup verification view
class BookingPickupVerificationView(generics.GenericAPIView):
    """
    Validates the 6-digit physical handoff authorization token provided by the Sender.
    Transitions Booking State from CONFIRMED -> PICKED_UP while escrow holds firm.
    """
    serializer_class = VerifyPickupPinSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        booking = serializer.validated_data["booking"]

        with transaction.atomic():
            # Advance state safely inside an database transaction container
            booking.status = BookingStatus.PICKED_UP
            booking.save(update_fields=["status"])

            # Send automated system notifications confirming the handoff completed successfully
            Notification.objects.create(
                user=booking.sender,
                title="Package Handed Over Successfully",
                message=f"Traveler verified the pickup token for order #{booking.tracking_number}. Status updated to PICKED_UP.",
                notification_type=NotificationType.DELIVERY,
                object_id=booking.id,
            )
            Notification.objects.create(
                user=booking.traveler,
                title="Handoff Confirmed",
                message=f"Pickup verified successfully for order #{booking.tracking_number}. You may now begin delivery routing.",
                notification_type=NotificationType.DELIVERY,
                object_id=booking.id,
            )

        return Response(
            {
                "success": True,
                "message": "Physical package handoff successfully authenticated.",
                "current_status": BookingStatus.PICKED_UP
            },
            status=status.HTTP_200_OK
        )