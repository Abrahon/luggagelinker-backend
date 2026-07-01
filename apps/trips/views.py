from django.shortcuts import render

# Create your views here.
import logging

from django.db import transaction
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

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