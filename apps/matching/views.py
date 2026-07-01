from django.shortcuts import render

# Create your views here.
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import generics
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

        return Match.objects.filter(
            is_active=True
        ).filter(
            package__sender=user
        ) | Match.objects.filter(
            trip__traveler=user
        )

    def list(self, request, *args, **kwargs):

        try:

            queryset = self.get_queryset().order_by("-created_at")

            serializer = self.get_serializer(queryset, many=True)

            return success_response(
                message="Matches retrieved successfully.",
                data=serializer.data,
                status_code=status.HTTP_200_OK
            )

        except Exception as e:

            return error_response(
                message="Failed to fetch matches.",
                status_code=500,
                errors=str(e)
            )



class PackageMatchListView(generics.ListAPIView):

    serializer_class = MatchSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):

        package_id = self.request.query_params.get("package_id")

        return Match.objects.filter(
            package_id=package_id,
            package__sender=self.request.user,
            is_active=True
        )

    def list(self, request, *args, **kwargs):

        try:

            queryset = self.get_queryset().order_by("-score")

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