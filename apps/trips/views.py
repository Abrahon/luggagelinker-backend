from django.shortcuts import render

# Create your views here.
import logging

from django.db import transaction
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import IsUserAllowed
from apps.matching.services.trip_matching import run_trip_matching
from apps.matching.services.trip_matching import run_trip_matching
from .models import Trip
from .serializers import TripSerializer
from django.db import transaction
from django.shortcuts import get_object_or_404

from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.trips.models import Trip, TripStatus
from apps.bookings.models import Booking, BookingStatus
from apps.matching.models import Match
from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, Q

from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from apps.reviews.models import Review

from .models import Trip, TripStatus
from .serializers import TravelerProfileSerializer


User = get_user_model()

from .serializers import AdminTripSerializer


logger = logging.getLogger(__name__)

class CreateTripListView(generics.ListCreateAPIView):

    serializer_class = TripSerializer
    permission_classes = [IsAuthenticated, IsUserAllowed]

    # ==========================================================
    # LIST PUBLIC TRIPS + SEARCH
    # ==========================================================

    def get_queryset(self):
        queryset = (
            Trip.objects
            .select_related("traveler")
            .filter(
                is_active=True,
                is_public=True,
                status=TripStatus.PLANNED,
            )
            .order_by("-created_at")
        )

        # ------------------------------------------
        # SEARCH PARAMETERS
        # ------------------------------------------

        from_country = self.request.query_params.get("from_country")
        from_city = self.request.query_params.get("from_city")

        to_country = self.request.query_params.get("to_country")
        to_city = self.request.query_params.get("to_city")

        departure_date = self.request.query_params.get("departure_date")

        # ------------------------------------------
        # FROM
        # ------------------------------------------

        if from_country:
            queryset = queryset.filter(
                from_country__iexact=from_country.strip()
            )

        if from_city:
            queryset = queryset.filter(
                from_city__icontains=from_city.strip()
            )

        # ------------------------------------------
        # TO
        # ------------------------------------------

        if to_country:
            queryset = queryset.filter(
                to_country__iexact=to_country.strip()
            )

        if to_city:
            queryset = queryset.filter(
                to_city__icontains=to_city.strip()
            )

        # ------------------------------------------
        # DEPARTURE DATE
        # ------------------------------------------

        if departure_date:
            try:
                from datetime import datetime

                parsed_date = datetime.strptime(
                    departure_date,
                    "%Y-%m-%d"
                ).date()

                queryset = queryset.filter(
                    departure_date=parsed_date
                )

            except ValueError:
                # Let the view return a clean validation error
                raise ValidationError(
                    {
                        "departure_date": [
                            "Invalid date format. Use YYYY-MM-DD."
                        ]
                    }
                )

        return queryset

    # ==========================================================
    # CREATE TRIP
    # ==========================================================

    @transaction.atomic
    def create(self, request, *args, **kwargs):

        serializer = self.get_serializer(
            data=request.data,
            context={"request": request},
        )

        try:
            serializer.is_valid(raise_exception=True)

            trip = serializer.save()

            run_trip_matching(trip)

            logger.info(
                f"Trip created successfully. "
                f"Trip={trip.id} "
                f"Traveler={request.user.id}"
            )

            return Response(
                {
                    "success": True,
                    "message": "Trip created successfully.",
                    "data": TripSerializer(
                        trip,
                        context={"request": request},
                    ).data,
                },
                status=status.HTTP_201_CREATED,
            )

        except ValidationError as e:

            logger.warning(
                f"Trip validation failed. "
                f"Traveler={request.user.id}"
            )

            return Response(
                {
                    "success": False,
                    "message": "Validation failed.",
                    "errors": e.detail,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception:

            logger.exception(
                f"Trip creation failed. "
                f"Traveler={request.user.id}"
            )

            return Response(
                {
                    "success": False,
                    "message": "Unable to create trip at this time.",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # ==========================================================
    # LIST
    # ==========================================================

    def list(self, request, *args, **kwargs):

        try:

            queryset = self.filter_queryset(
                self.get_queryset()
            )

            serializer = self.get_serializer(
                queryset,
                many=True,
            )

            return Response(
                {
                    "success": True,
                    "message": "Trips retrieved successfully.",
                    "count": queryset.count(),
                    "data": serializer.data,
                },
                status=status.HTTP_200_OK,
            )

        except ValidationError as e:

            return Response(
                {
                    "success": False,
                    "message": "Invalid search parameters.",
                    "errors": e.message_dict
                    if hasattr(e, "message_dict")
                    else e.messages,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception:

            logger.exception(
                "Failed to retrieve trips."
            )

            return Response(
                {
                    "success": False,
                    "message": "Unable to retrieve trips.",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )



class MyTripListView(generics.ListAPIView):

    serializer_class = TripSerializer
    permission_classes = [IsAuthenticated, IsUserAllowed]

    # ==========================================================
    # MY TRIPS
    # ==========================================================

    def get_queryset(self):

        return (
            Trip.objects
            .select_related("traveler")
            .filter(
                traveler=self.request.user,
                is_active=True,
            )
            .order_by("-created_at")
        )

    # ==========================================================
    # LIST
    # ==========================================================

    def list(self, request, *args, **kwargs):

        try:

            queryset = self.filter_queryset(
                self.get_queryset()
            )

            serializer = self.get_serializer(
                queryset,
                many=True,
            )

            return Response(
                {
                    "success": True,
                    "message": "Your trips retrieved successfully.",
                    "count": queryset.count(),
                    "data": serializer.data,
                },
                status=status.HTTP_200_OK,
            )

        except Exception:

            logger.exception(
                f"Failed to retrieve trips. "
                f"Traveler={request.user.id}"
            )

            return Response(
                {
                    "success": False,
                    "message": "Unable to retrieve your trips.",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# trip detaisl



class TripDetailView(generics.RetrieveAPIView):

    serializer_class = TripSerializer
    permission_classes = [IsAuthenticated, IsUserAllowed]
    lookup_field = "id"

    def get_queryset(self):

        return (
            Trip.objects
            .select_related("traveler")
            .filter(is_active=True)
        )

    def retrieve(self, request, *args, **kwargs):

        try:

            trip = self.get_queryset().filter(
                id=kwargs["id"]
            ).first()

            if not trip:

                return Response(
                    {
                        "success": False,
                        "message": "Trip not found.",
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Private trip
            if (
                not trip.is_public
                and trip.traveler != request.user
            ):

                return Response(
                    {
                        "success": False,
                        "message": "You do not have permission to view this trip.",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            serializer = self.get_serializer(trip)

            return Response(
                {
                    "success": True,
                    "message": "Trip retrieved successfully.",
                    "data": serializer.data,
                },
                status=status.HTTP_200_OK,
            )

        except Exception:

            logger.exception(
                f"Failed to retrieve trip. "
                f"Trip={kwargs.get('id')} "
                f"User={request.user.id}"
            )

            return Response(
                {
                    "success": False,
                    "message": "Unable to retrieve trip.",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )



# manage trip 
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAdminUser

from apps.trips.models import Trip

from .serializers import AdminTripListSerializer
from .filters import AdminTripFilter


class AdminTripListView(ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = AdminTripListSerializer

    queryset = (
        Trip.objects.select_related("traveler")
        .all()
        .order_by("-created_at")
    )

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    filterset_class = AdminTripFilter

    search_fields = [
        "title",
        "traveler__email",
        "from_city",
        "to_city",
        "from_country",
        "to_country",
    ]

    ordering_fields = [
        "created_at",
        "departure_date",
        "arrival_date",
        "status",
    ]

    ordering = [
        "-created_at",
    ]


class TripManageView(generics.RetrieveUpdateDestroyAPIView):

    serializer_class = TripSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "id"

    def get_queryset(self):

        return (
            Trip.objects
            .select_related("traveler")
            .filter(
                is_active=True,
            )
        )

    # ==========================================================
    # UPDATE (PUT/PATCH)
    # ==========================================================

    @transaction.atomic
    def update(self, request, *args, **kwargs):

        trip = self.get_queryset().filter(
            id=kwargs["id"],
        ).first()

        if not trip:

            return Response(
                {
                    "success": False,
                    "message": "Trip not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if trip.traveler != request.user:

            return Response(
                {
                    "success": False,
                    "message": "You do not have permission to update this trip.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        partial = kwargs.pop("partial", False)

        serializer = self.get_serializer(
            trip,
            data=request.data,
            partial=partial,
            context={"request": request},
        )

        try:

            serializer.is_valid(
                raise_exception=True,
            )

            serializer.save()

            logger.info(
                f"Trip updated successfully. "
                f"Trip={trip.id} "
                f"Traveler={request.user.id}"
            )

            return Response(
                {
                    "success": True,
                    "message": "Trip updated successfully.",
                    "data": serializer.data,
                },
                status=status.HTTP_200_OK,
            )

        except ValidationError as e:

            return Response(
                {
                    "success": False,
                    "message": "Validation failed.",
                    "errors": e.detail,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception:

            logger.exception(
                f"Trip update failed. "
                f"Trip={trip.id}"
            )

            return Response(
                {
                    "success": False,
                    "message": "Unable to update trip.",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # ==========================================================
    # DELETE (SOFT DELETE)
    # ==========================================================

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):

        trip = self.get_queryset().filter(
            id=kwargs["id"],
        ).first()

        if not trip:

            return Response(
                {
                    "success": False,
                    "message": "Trip not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if trip.traveler != request.user:

            return Response(
                {
                    "success": False,
                    "message": "You do not have permission to delete this trip.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        try:

            trip.is_active = False
            trip.save(
                update_fields=["is_active"],
            )

            logger.info(
                f"Trip deleted successfully. "
                f"Trip={trip.id}"
            )

            return Response(
                {
                    "success": True,
                    "message": "Trip deleted successfully.",
                },
                status=status.HTTP_200_OK,
            )

        except Exception:

            logger.exception(
                f"Trip deletion failed. "
                f"Trip={trip.id}"
            )

            return Response(
                {
                    "success": False,
                    "message": "Unable to delete trip.",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class AdminTripDetailView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, trip_id):

        trip = get_object_or_404(
            Trip.objects.select_related("traveler"),
            id=trip_id,
        )

        serializer = AdminTripSerializer(trip)

        return Response(
            {
                "message": "Trip fetched successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )



class AdminCancelTripView(APIView):
    permission_classes = [IsAdminUser]

    @transaction.atomic
    def patch(self, request, trip_id):

        trip = get_object_or_404(Trip, id=trip_id)

        reason = request.data.get(
            "reason",
            "Cancelled by administrator."
        )

        if trip.status == TripStatus.CANCELLED:
            return Response(
                {
                    "message": "Trip is already cancelled."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if trip.status == TripStatus.COMPLETED:
            return Response(
                {
                    "message": "Completed trips cannot be cancelled."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        active_booking_exists = Booking.objects.filter(
            trip=trip,
            status__in=[
                BookingStatus.CONFIRMED,
                BookingStatus.PICKED_UP,
                BookingStatus.IN_TRANSIT,
                BookingStatus.DELIVERED,
                BookingStatus.COMPLETED,
            ],
        ).exists()

        if active_booking_exists:
            return Response(
                {
                    "message": "This trip has active bookings. Cancel those bookings first."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        cancelled_booking_count = Booking.objects.filter(
            trip=trip,
            status__in=[
                BookingStatus.PENDING,
                BookingStatus.TRAVELER_ACCEPTED,
                BookingStatus.PAYMENT_PENDING,
            ],
        ).exclude(
            status=BookingStatus.CANCELLED,
        ).update(
            status=BookingStatus.CANCELLED,
            is_active=False,
            cancellation_reason=reason,
        )

        deactivated_matches = Match.objects.filter(
            trip=trip,
            is_active=True,
        ).update(
            is_active=False,
        )

        trip.status = TripStatus.CANCELLED
        trip.is_active = False
        trip.save(
            update_fields=[
                "status",
                "is_active",
                "updated_at",
            ]
        )

        return Response(
            {
                "message": "Trip cancelled successfully.",
                "data": {
                    "trip_id": str(trip.id),
                    "trip_status": trip.status,
                    "bookings_cancelled": cancelled_booking_count,
                    "matches_deactivated": deactivated_matches,
                },
            },
            status=status.HTTP_200_OK,
        )


from django.contrib.auth import get_user_model
from django.db.models import Avg, Count

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from apps.bookings.models import Booking, BookingStatus
from apps.disputes.models import Dispute
from apps.disputes.enums import (
    DisputeStatus,
    ResolutionType,
)
from apps.reviews.models import Review

from .serializers import TravelerProfileSerializer


User = get_user_model()


class TravelerProfileAPIView(APIView):
    """
    Retrieve a traveler's public profile and calculated statistics.

    Statistics are calculated from source-of-truth models:

        Booking  -> deliveries / trips
        Dispute  -> disputed deliveries / traveler fault
        Review   -> rating / reviews

    No statistics are permanently stored on User/Profile.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, traveler_id):

        # ======================================================
        # 1. GET TRAVELER
        # ======================================================

        traveler = (
            User.objects
            .select_related("profile")
            .filter(
                id=traveler_id,
                is_active=True,
            )
            .first()
        )

        if traveler is None:
            return Response(
                {
                    "success": False,
                    "message": "Traveler not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # ======================================================
        # 2. COMPLETED BOOKINGS
        #
        # One COMPLETED booking = one completed delivery.
        # ======================================================

        completed_bookings = Booking.objects.filter(
            traveler_id=traveler.id,
            status=BookingStatus.COMPLETED,
        )

        completed_deliveries = completed_bookings.count()

        # ======================================================
        # 3. COMPLETED TRIPS
        #
        # A traveler may carry multiple packages on the same
        # trip.
        #
        # Therefore:
        #
        # 10 bookings on 6 trips = 6 completed trips
        # ======================================================

        completed_trips = (
            completed_bookings
            .values("trip_id")
            .distinct()
            .count()
        )

        # ======================================================
        # 4. COMPLETED DELIVERIES HAVING A DISPUTE
        #
        # Dispute.booking is OneToOneField.
        #
        # Therefore one booking can have only one dispute.
        #
        # We count DISTINCT booking IDs because the metric is:
        #
        #     "How many deliveries were disputed?"
        #
        # NOT:
        #
        #     "How many dispute records exist?"
        # ======================================================

        completed_disputes = (
            Dispute.objects
            .filter(
                booking__traveler_id=traveler.id,
                booking__status=BookingStatus.COMPLETED,
            )
            .select_related("booking")
        )

        disputed_booking_ids = (
            completed_disputes
            .values_list(
                "booking_id",
                flat=True,
            )
            .distinct()
        )

        disputed_deliveries = len(
            set(disputed_booking_ids)
        )

        # ======================================================
        # 5. PENDING DISPUTES
        #
        # Pending disputes are NOT considered failures.
        #
        # OPEN
        # UNDER_REVIEW
        # WAITING_FOR_USER
        # ======================================================

        pending_disputes = (
            completed_disputes
            .filter(
                status__in=[
                    DisputeStatus.OPEN,
                    DisputeStatus.UNDER_REVIEW,
                    DisputeStatus.WAITING_FOR_USER,
                ]
            )
            .count()
        )

        # ======================================================
        # 6. TRAVELER-FAULT DISPUTES
        #
        # Your enums DO NOT contain:
        #
        #     DisputeResponsibleParty
        #
        # Therefore we do NOT use it.
        #
        # Existing business rule:
        #
        # Traveler is considered responsible only when:
        #
        #   1. dispute is against this traveler
        #   2. dispute has a final resolution
        #   3. resolution is FULL_REFUND or PARTIAL_REFUND
        #
        # REJECTED / NO_ACTION
        #     -> NOT traveler fault
        #
        # RELEASE_PAYMENT
        #     -> NOT traveler fault
        #
        # OPEN / UNDER_REVIEW / WAITING_FOR_USER
        #     -> NOT traveler fault
        # ======================================================

        traveler_fault_disputes = (
            completed_disputes
            .filter(
                against_user_id=traveler.id,
                status__in=[
                    DisputeStatus.RESOLVED,
                    DisputeStatus.CLOSED,
                ],
                resolution__in=[
                    ResolutionType.FULL_REFUND,
                    ResolutionType.PARTIAL_REFUND,
                ],
            )
            .count()
        )

        # ======================================================
        # 7. SUCCESSFUL DELIVERIES
        #
        # Only confirmed traveler-fault deliveries are removed.
        #
        # Example:
        #
        # completed deliveries = 10
        # traveler fault        = 2
        #
        # successful deliveries = 8
        # ======================================================

        successful_deliveries = max(
            completed_deliveries
            - traveler_fault_disputes,
            0,
        )

        # ======================================================
        # 8. SUCCESS RATE
        #
        # Pending disputes do NOT reduce success rate.
        #
        # Formula:
        #
        # successful deliveries
        # -------------------- × 100
        # completed deliveries
        # ======================================================

        if completed_deliveries > 0:
            success_rate = round(
                (
                    successful_deliveries
                    / completed_deliveries
                ) * 100,
                1,
            )
        else:
            success_rate = 0.0

        # ======================================================
        # 9. REVIEWS
        # ======================================================

        reviews = (
            Review.objects
            .filter(
                traveler_id=traveler.id
            )
            .select_related(
                "sender",
                "sender__profile",
            )
        )

        # ======================================================
        # 10. TOTAL REVIEWS
        # ======================================================

        total_reviews = reviews.count()

        # ======================================================
        # 11. AVERAGE RATING
        # ======================================================

        average_rating = (
            reviews.aggregate(
                average=Avg("rating")
            )["average"]
        )

        if average_rating is None:
            average_rating = 0.0
        else:
            average_rating = round(
                float(average_rating),
                1,
            )

        # ======================================================
        # 12. RATING DISTRIBUTION
        # ======================================================

        rating_distribution = {
            "5": 0,
            "4": 0,
            "3": 0,
            "2": 0,
            "1": 0,
        }

        rating_counts = (
            reviews
            .values("rating")
            .annotate(
                count=Count("id")
            )
        )

        for item in rating_counts:

            rating = str(item["rating"])

            if rating in rating_distribution:
                rating_distribution[rating] = (
                    item["count"]
                )

        # ======================================================
        # 13. RECENT REVIEWS
        # ======================================================

        recent_reviews = list(
            reviews
            .order_by("-created_at")[:5]
        )

        # ======================================================
        # 14. TEMPORARY SERIALIZER VALUES
        #
        # These are request-level calculated values.
        # Nothing is written to the database.
        # ======================================================

        traveler.average_rating_value = (
            average_rating
        )

        traveler.total_reviews_value = (
            total_reviews
        )

        traveler.completed_trips_value = (
            completed_trips
        )

        traveler.total_deliveries_value = (
            completed_deliveries
        )

        traveler.successful_deliveries_value = (
            successful_deliveries
        )

        traveler.disputed_deliveries_value = (
            disputed_deliveries
        )

        traveler.traveler_fault_disputes_value = (
            traveler_fault_disputes
        )

        traveler.pending_disputes_value = (
            pending_disputes
        )

        traveler.success_rate_value = (
            success_rate
        )

        traveler.rating_distribution_data = (
            rating_distribution
        )

        traveler.recent_reviews_data = (
            recent_reviews
        )

        # ======================================================
        # 15. SERIALIZE
        # ======================================================

        serializer = TravelerProfileSerializer(
            traveler,
            context={
                "request": request,
            },
        )

        # ======================================================
        # 16. RESPONSE
        # ======================================================

        return Response(
            {
                "success": True,
                "message": (
                    "Traveler profile retrieved "
                    "successfully."
                ),
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )