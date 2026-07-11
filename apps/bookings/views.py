from django.shortcuts import render

# Create your views here.
import logging
from django.db import models
from django.db.models import Q
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Booking
from .serializers import BookingSerializer, VerifyDeliveryPinSerializer, VerifyPickupPinSerializer
from .services import BookingService
from rest_framework.exceptions import ValidationError
from django.db import transaction
from .serializers import StartTransitSerializer
from apps.bookings.models import BookingStatus
from apps.notifications.models import Notification, NotificationType
# 🟢 Import the validation serializer
from .serializers import VerifyDeliveryPinSerializer
from django.core.exceptions import ValidationError as DjangoValidationError
# 🟢 Import the status enums 
from apps.bookings.models import BookingStatus
# 🟢 IMPORT THE LIFECYCLE SERVICE HERE
from apps.bookings.services import BookingLifecycleService
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError as DRFValidationError
import logging

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
            
        except DRFValidationError as e:
            # 🟢 FIXED: Intercept validation errors and return a clean 400 with the exact message
            return Response(
                {
                    "success": False,
                    "message": "Booking validation failed.",
                    "errors": e.detail,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
            
        except Exception as e:
            # Fallback capture if anything drops at low-level runtime execution bounds
            logger.error(f"Critical execution crash inside BookingCreateView: {str(e)}", exc_info=True)
            return Response(
                {
                    "success": False,
                    "message": "An internal system error occurred while setting up the transaction.",
                    "error_details": str(e) # Show the underlying systemic exception details
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

        except (DRFValidationError, DjangoValidationError) as e:
            # 🟢 FIXED: Safely unpack clean, descriptive error details regardless of exception source
            error_message = "Validation failed handling booking response request."
            
            if hasattr(e, 'detail'): # Handles DRF ValidationErrors
                error_message = e.detail if not isinstance(e.detail, dict) else e.detail.get('detail', e.detail)
            elif hasattr(e, 'messages'): # Handles native Django ValidationErrors lists
                error_message = e.messages[0] if len(e.messages) == 1 else e.messages
            elif hasattr(e, 'message'): # Fallback single message string attribute
                error_message = e.message

            return Response(
                {
                    "success": False, 
                    "message": "Action validation failed.",
                    "errors": error_message
                },
                status=status.HTTP_400_BAD_REQUEST
            )
            
        except Exception as e:
            # Fallback for hidden database connection leaks or core crashes
            logger.error(f"System crash processing action response on booking {id}: {str(e)}", exc_info=True)
            return Response(
                {
                    "success": False, 
                    "message": "An internal system error occurred.",
                    "error_details": str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )



# picup verification view
class BookingPickupVerificationView(generics.GenericAPIView):

    serializer_class = VerifyPickupPinSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):

        serializer = self.get_serializer(
            data=request.data,
            context={"request": request},
        )

        serializer.is_valid(raise_exception=True)

        booking = serializer.validated_data["booking"]

        # ============================================================
        # Traveler refused package
        # ============================================================
        if serializer.validated_data["traveler_matches_listing"] is False:

            BookingLifecycleService.refuse_pickup(
                booking=booking,
                reason=serializer.validated_data["traveler_refusal_reason"],
            )

            return Response(
                {
                    "success": True,
                    "message": (
                        "Pickup refused successfully. "
                        "Booking cancelled and package sent for manual review."
                    ),
                },
                status=status.HTTP_200_OK,
            )

        # ============================================================
        # Traveler accepted package
        # ============================================================
        try:

            updated_booking = (
                BookingLifecycleService.verify_and_execute_pickup(
                    booking
                )
            )

            return Response(
                {
                    "success": True,
                    "message": "Physical package handoff successfully authenticated.",
                    "current_status": updated_booking.status,
                    "picked_up_at": updated_booking.picked_up_at,
                },
                status=status.HTTP_200_OK,
            )

        except DjangoValidationError as e:

            return Response(
                {
                    "success": False,
                    "message": str(e),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
    



# booking intransit verification view



class BookingStartTransitView(generics.GenericAPIView):
    """
    Advances booking state from PICKED_UP -> IN_TRANSIT.
    Delegates database updates and temporal stamps completely to the Service Layer.
    """
    serializer_class = StartTransitSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        # Retrieve the validated booking instance mapped by the serializer
        booking = serializer.validated_data["booking_instance"]

        try:
            # 🟢 Execute business mutations via service routing
            updated_booking = BookingLifecycleService.execute_start_transit(booking)
            
            return Response(
                {
                    "success": True,
                    "message": "Booking status successfully updated to IN_TRANSIT.",
                    "current_status": updated_booking.status,
                    "in_transit_at": updated_booking.in_transit_at
                },
                status=status.HTTP_200_OK
            )
            
        except DjangoValidationError as e:
            return Response(
                {"success": False, "message": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


# bookimng delivery verification view

from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError as DRFValidationError
from django.core.exceptions import ValidationError as DjangoValidationError
import logging

logger = logging.getLogger(__name__)

class BookingDeliveryVerificationView(generics.GenericAPIView):
    """
    Validates the 6-digit physical delivery drop-off token provided by the Receiver.
    Delegates delivery timestamp recording and automated payment release to the Service Layer.
    """
    serializer_class = VerifyDeliveryPinSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        booking = serializer.validated_data["booking_instance"]

        try:
            # 🟢 Route execution to unified delivery + automatic payout handler
            updated_booking = BookingLifecycleService.verify_and_execute_delivery(booking)
            
            return Response(
                {
                    "success": True,
                    "message": "Physical drop-off authenticated. Payment automatically released and order successfully COMPLETED.",
                    "current_status": updated_booking.status,
                    "delivered_at": updated_booking.delivered_at
                },
                status=status.HTTP_200_OK
            )
            
        except (DRFValidationError, DjangoValidationError) as e:
            # Handle state or logic rules validation errors gracefully
            error_message = "Validation failed during delivery execution."
            if hasattr(e, 'detail'):
                error_message = e.detail if not isinstance(e.detail, dict) else e.detail.get('detail', e.detail)
            elif hasattr(e, 'messages'):
                error_message = e.messages[0] if len(e.messages) == 1 else e.messages

            return Response(
                {
                    "success": False, 
                    "message": "Action validation failed.",
                    "errors": error_message
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        except ValueError as val_err:
            # 🟢 FIXED: Catches your custom ledger exceptions (like empty pending balance) 
            # and returns a clean 400 Bad Request instead of a 500 crash.
            logger.warning(f"Financial safety check blocked delivery verification: {str(val_err)}")
            return Response(
                {
                    "success": False,
                    "message": "Financial ledger synchronization check failed.",
                    "errors": str(val_err)
                },
                status=status.HTTP_400_BAD_REQUEST
            )
            
        except Exception as e:
            # Fallback capture if anything drops at low-level runtime execution bounds
            logger.error(f"Critical execution crash inside BookingDeliveryVerificationView: {str(e)}", exc_info=True)
            return Response(
                {
                    "success": False,
                    "message": "An internal system error occurred while finalizing delivery.",
                    "error_details": str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )



class BookingCancellationView(generics.GenericAPIView):
    """
    POST /api/bookings/{id}/cancel/
    Enforces atomic state transitions to CANCELLED and triggers the wallet refund engine.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = BookingSerializer
    queryset = Booking.objects.all()

    def post(self, request, pk, *args, **kwargs):
        try:
            # Route execution down to the unified cancellation service handler
            updated_booking = BookingLifecycleService.cancel_booking(booking_or_id=pk)
            
            return Response(
                {
                    "success": True,
                    "message": "Booking cancelled successfully. Escrow hold reversed and fully refunded to sender.",
                    "current_status": updated_booking.status
                },
                status=status.HTTP_200_OK
            )
            
        except (DjangoValidationError, DRFValidationError) as exc:
            error_messages = exc.messages if hasattr(exc, 'messages') else [str(exc)]
            return Response(
                {
                    "success": False,
                    "message": "Cancellation validation failed.",
                    "errors": error_messages
                },
                status=status.HTTP_400_BAD_REQUEST
            )


from rest_framework import generics, permissions

from apps.bookings.models import Booking
from apps.bookings.serializers import BookingSerializer


class CompletedBookingListView(generics.ListAPIView):
    """
    Returns completed bookings for the authenticated sender.
    """

    serializer_class = BookingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):

        user = self.request.user

        print("=" * 60)
        print("Authenticated:", user.is_authenticated)
        print("User Email:", user.email)
        print("User ID:", user.id)

        queryset = (
            Booking.objects.filter(
                sender_id=user.id,
                status="COMPLETED",
            )
            .select_related(
                "sender",
                "traveler",
                "booking_payment",
            )
            .order_by("-updated_at")
        )

        print("Completed Booking Count:", queryset.count())

        for booking in queryset:
            print(
                booking.id,
                booking.sender.email,
                booking.status,
            )

        print("=" * 60)

        return queryset