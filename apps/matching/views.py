from django.shortcuts import render

# Create your views here.
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import generics
from .models import Match
from .serializers import MatchSerializer
from .models import Match
from .serializers import MatchSerializer
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from django.db import models  # 👈 ADD THIS IMPORT
from django.db.models import Q #
from rest_framework.response import Response
from .models import Match
from .serializers import MatchSerializer
import uuid
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from django.db import models
from .models import Match
from .serializers import MatchSerializer
from collections import OrderedDict
from apps.packages.models import PackageStatus

# from .utils import success_response, error_response



def success_response(message, data=None, status_code=200):
    return Response(
        {
            "success": True,
            "message": message,
            "data": data,
        },
        status=status_code,
    )


def error_response(message, status_code=400, errors=None):
    return Response(
        {
            "success": False,
            "message": message,
            "errors": errors,
        },
        status=status_code,
    )




class MyMatchListView(generics.ListAPIView):
    serializer_class = MatchSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        return (
            Match.objects
            .filter(
                # ------------------------------------------
                # MATCH MUST BE ACTIVE
                # ------------------------------------------
                is_active=True,

                # ------------------------------------------
                # PACKAGE MUST CURRENTLY BE PUBLISHED
                # ------------------------------------------
                package__status=PackageStatus.PUBLISHED,
                package__is_active=True,
                package__is_public=True,

                # ------------------------------------------
                # TRIP MUST CURRENTLY BE ACTIVE/PUBLIC
                # ------------------------------------------
                trip__is_active=True,
                trip__is_public=True,
            )
            .filter(
                # ------------------------------------------
                # USER MUST BE EITHER:
                # 1. PACKAGE SENDER
                # 2. TRIP TRAVELER
                # ------------------------------------------
                models.Q(package__sender=user)
                | models.Q(trip__traveler=user)
            )
            .select_related(
                "package",
                "package__sender",
                "trip",
                "trip__traveler",
            )
            .order_by("-created_at")
        )

    def list(self, request, *args, **kwargs):

        queryset = self.get_queryset()

        # --------------------------------------------------
        # NO MATCHES
        # --------------------------------------------------

        if not queryset.exists():
            return Response(
                {
                    "success": False,
                    "message": "No matches found.",
                    "data": [],
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # --------------------------------------------------
        # PAGINATION
        # --------------------------------------------------

        page = self.paginate_queryset(queryset)

        if page is not None:

            serializer = self.get_serializer(
                page,
                many=True,
            )

            response = self.get_paginated_response(
                serializer.data
            )

            response.data = OrderedDict([
                (
                    "success",
                    True,
                ),
                (
                    "message",
                    "Matches retrieved successfully.",
                ),
                (
                    "count",
                    response.data["count"],
                ),
                (
                    "next",
                    response.data["next"],
                ),
                (
                    "previous",
                    response.data["previous"],
                ),
                (
                    "data",
                    response.data["results"],
                ),
            ])

            return response

        # --------------------------------------------------
        # NON-PAGINATED RESPONSE
        # --------------------------------------------------

        serializer = self.get_serializer(
            queryset,
            many=True,
        )

        return Response(
            {
                "success": True,
                "message": "Matches retrieved successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    
class PackageMatchListView(generics.ListAPIView):

    serializer_class = MatchSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        package_id = self.request.query_params.get("package_id", "").strip()

        # Base filter: Only show active matches belonging to the logged-in sender's packages
        queryset = Match.objects.filter(
            package__sender=user,
            is_active=True
        )

        # OPTIONAL FILTER: If a valid package_id is passed, filter down further.
        # If an invalid package_id or empty string is passed, we safely ignore it.
        if package_id:
            try:
                uuid.UUID(str(package_id))
                queryset = queryset.filter(package_id=package_id)
            except ValueError:
                # If they passed trash data in the query param, return an empty set 
                # instead of crashing the database.
                return Match.objects.none()

        # PRODUCTION OPTIMIZATION: Pull all nested data structures in 1 single join query
        return queryset.select_related(
            "package",
            "package__sender", 
            "trip",
            "trip__traveler"
        ).order_by("-score", "-created_at")

    def list(self, request, *args, **kwargs):
        try:
            queryset = self.get_queryset()

            if not queryset.exists():
                return success_response(
                    message="No matches found for your packages.",
                    data=[],
                )

            serializer = self.get_serializer(queryset, many=True)

            return success_response(
                message="Package matches retrieved successfully.",
                data=serializer.data
            )

        except Exception as e:
            return error_response(
                message="Unable to fetch package matches.",
                status_code=500,
                errors=str(e)
            )   


class TripMatchListView(generics.ListAPIView):

    serializer_class = MatchSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):

        trip_id = self.request.query_params.get("trip_id")

        return Match.objects.filter(
            trip_id=trip_id,
            trip__traveler=self.request.user,
            is_active=True
        )
    def list(self, request, *args, **kwargs):

        try:

            queryset = self.get_queryset().order_by("-score")

            if not queryset.exists():

                return success_response(
                    message="No matches found for this trip.",
                    data=[],
                )

            serializer = self.get_serializer(queryset, many=True)

            return success_response(
                message="Trip matches retrieved successfully.",
                data=serializer.data
            )

        except Exception as e:

            return error_response(
                message="Unable to fetch trip matches.",
                status_code=500,
                errors=str(e)
            )


class MatchDetailView(generics.RetrieveAPIView):

    serializer_class = MatchSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "id"

    def get_queryset(self):

        user = self.request.user

        return Match.objects.filter(
            is_active=True
        ).filter(
            package__sender=user
        ) | Match.objects.filter(
            trip__traveler=user
        )

    def retrieve(self, request, *args, **kwargs):

        try:

            instance = self.get_object()

            serializer = self.get_serializer(instance)

            return success_response(
                message="Match details retrieved successfully.",
                data=serializer.data
            )

        except Exception as e:

            return error_response(
                message="Match not found.",
                status_code=404,
                errors=str(e)
            )


from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from apps.trips.models import Trip
from apps.packages.services import PackageService
from apps.packages.serializers import PackageSerializer


class MyTripMatchingPackagesView(APIView):
    """
    Return only the authenticated sender's packages
    that match a specific trip.

    Used when sender clicks:
        Booking Request
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, trip_id):

        # ==========================================================
        # 1. GET PUBLIC TRIP
        # ==========================================================

        try:
            trip = Trip.objects.get(
                id=trip_id,
                is_public=True,
                is_active=True,
            )
        except Trip.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": (
                        "The selected public trip "
                        "does not exist or is no longer available."
                    ),
                    "data": [],
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # ==========================================================
        # 2. FIND MATCHING PACKAGES
        # ==========================================================

        packages = PackageService.find_packages_for_trip(
            trip=trip,
            sender=request.user,
        )

        # ==========================================================
        # 3. SERIALIZE
        # ==========================================================

        serializer = PackageSerializer(
            packages,
            many=True,
            context={
                "request": request,
            },
        )

        # ==========================================================
        # 4. RESPONSE
        # ==========================================================

        return Response(
            {
                "success": True,
                "message": (
                    "Matching packages retrieved successfully."
                ),
                "trip_id": str(trip.id),
                "count": packages.count(),
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )