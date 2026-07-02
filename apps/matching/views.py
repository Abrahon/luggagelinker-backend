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
        # High performance optimization: fetch relationships upfront in single join
        return Match.objects.filter(is_active=True).select_related(
            "package__sender", "trip__traveler"
        ).filter(
            models.Q(package__sender=user) | models.Q(trip__traveler=user)
        ).order_by("-created_at")

    def list(self, request, *args, **kwargs):
        try:
            queryset = self.get_queryset()
            if not queryset.exists():
                return Response({"success": False, "message": "No matches found.", "data": []}, status=404)
            
            serializer = self.get_serializer(queryset, many=True)
            return Response({"success": True, "message": "Matches retrieved successfully.", "data": serializer.data}, status=200)
        except Exception as e:
            return Response({"success": False, "message": "Failed to fetch matches.", "errors": str(e)}, status=500)
        



class PackageMatchListView(generics.ListAPIView):

    serializer_class = MatchSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # 🟢 CHANGE 1: Defensive Programming Validation
        # If a client sends an empty/missing 'package_id', filtering down by None 
        # is slow or can cause unexpected results. We default to a blank string or safely handle it.
        package_id = self.request.query_params.get("package_id", "")

        # 🟢 CHANGE 2: Added select_related() database optimization
        # Your serializer relies on reading properties like 'package.title' and 'trip.traveler.email'.
        # By adding select_related, Django joins these tables on the SQL layer instantly.
        # This reduces database queries from N+1 down to exactly 1 query.
        return Match.objects.filter(
            package_id=package_id,
            package__sender=self.request.user,
            is_active=True
        ).select_related(
            "package__sender", 
            "trip__traveler"
        ).order_by("-score") # 🟢 CHANGE 3: Moved order_by directly into the base queryset definition.

    def list(self, request, *args, **kwargs):
        try:
            # 🟢 CHANGE 4: Cleaned up dual query evaluations.
            # Your old code split the database execution by calling .order_by() inside list() 
            # after getting the queryset, triggering unnecessary compilation steps.
            queryset = self.get_queryset()

            # Note: .exists() is fast, but if the records are present, it still costs 
            # an evaluation call. For small to mid-sized result sets, streaming directly 
            # into the serializer is efficient.
            if not queryset.exists():
                return success_response(
                    message="No matches found for this package.",
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