from django.shortcuts import render

# Create your views here.
import logging

from django.db import transaction
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.matching.services.trip_matching import run_trip_matching
from apps.matching.services.trip_matching import run_trip_matching
from .models import Trip
from .serializers import TripSerializer

logger = logging.getLogger(__name__)


class CreateTripListView(generics.ListCreateAPIView):

    serializer_class = TripSerializer
    permission_classes = [IsAuthenticated]

    # ==========================================================
    # LIST PUBLIC TRIPS
    # ==========================================================

    def get_queryset(self):

        return (
            Trip.objects
            .select_related("traveler")
            .filter(
                is_active=True,
                is_public=True,
            )
            .order_by("-created_at")
        )

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
    # LIST PUBLIC TRIPS
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
    permission_classes = [IsAuthenticated]

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
    permission_classes = [IsAuthenticated]
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