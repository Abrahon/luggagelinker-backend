from django.shortcuts import render

# Create your views here.
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from django.db.models import Q
from .models import Review
from .serializers import ReviewSerializer
from django.db import transaction

from apps.reviews.services import update_traveler_rating
from apps.notifications.services import notify_review_received


class ReviewListCreateAPIView(generics.ListCreateAPIView):
    """
    API view to list reviews and create a new review.
    
    * Senders can only see reviews they have submitted.
    * Automatically handles injecting the request user into the creation cycle.
    """
    serializer_class = ReviewSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        Optimized queryset ensuring users only view relevant reviews.
        Uses select_related to minimize DB hits on related booking fields.
        """
        user = self.request.user
        
        # Senders see what they wrote; Travelers see reviews about them.
        # If you want Senders to ONLY see their submitted reviews, keep it as:
        # return Review.objects.filter(sender=user).select_related('booking', 'sender', 'traveler')
        return Review.objects.filter(
            Q(sender=user) | Q(traveler=user)
        ).select_related('booking', 'sender', 'traveler')

    def perform_create(self, serializer):
        """
        Save the review, then update traveler rating and
        send a notification after the transaction commits.
        """

        review = serializer.save()

        transaction.on_commit(
            lambda: update_traveler_rating(
                traveler=review.traveler,
                rating=review.rating,
            )
        )

        transaction.on_commit(
            lambda: notify_review_received(
                traveler=review.traveler,
                sender=review.sender,
                review=review,
            )
        )


class ReviewRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    """
    API view to retrieve, update, or delete a specific review instance.
    
    * Only the original sender can update or delete their review.
    * Both sender and traveler can view (retrieve) it.
    """
    serializer_class = ReviewSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        Optimizes database retrieval.
        """
        user = self.request.user
        return Review.objects.filter(
            Q(sender=user) | Q(traveler=user)
        ).select_related('booking', 'sender', 'traveler')

    def perform_update(self, serializer):
        """
        Object-level permission guard to ensure only the original author 
        (sender) can modify the review content.
        """
        review = self.get_object()
        if review.sender != self.request.user:
            raise PermissionDenied("You do not have permission to edit this review.")
        serializer.save()

    def perform_destroy(self, instance):
        """
        Object-level permission guard to ensure only the original author
        (sender) can delete the review.
        """
        if instance.sender != self.request.user:
            raise PermissionDenied("You do not have permission to delete this review.")
        instance.delete()



import logging

from django.core.exceptions import ValidationError as DjangoValidationError

from rest_framework import generics, permissions, status
from rest_framework.response import Response

from .models import Report
from .serializers import ReportSerializer, CreateReportSerializer

logger = logging.getLogger(__name__)


class ReportListCreateAPIView(generics.ListCreateAPIView):

    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            Report.objects.filter(
                reporter=self.request.user
            )
            .select_related(
                "reporter",
                "reported_user",
                "booking",
                "assigned_admin",
            )
            .order_by("-created_at")
        )

    def get_serializer_class(self):
        if self.request.method == "POST":
            return CreateReportSerializer
        return ReportSerializer

    def list(self, request, *args, **kwargs):

        queryset = self.get_queryset()

        serializer = self.get_serializer(queryset, many=True)

        return Response(
            {
                "success": True,
                "message": "Reports retrieved successfully.",
                "count": queryset.count(),
                "results": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def create(self, request, *args, **kwargs):

        serializer = self.get_serializer(
            data=request.data,
            context={"request": request},
        )

        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "message": "Validation failed.",
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            report = serializer.save()

            return Response(
                {
                    "success": True,
                    "message": "Report submitted successfully.",
                    "data": ReportSerializer(report).data,
                },
                status=status.HTTP_201_CREATED,
            )

        except DjangoValidationError as e:

            return Response(
                {
                    "success": False,
                    "message": "Unable to submit report.",
                    "errors": e.message_dict if hasattr(e, "message_dict") else e.messages,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception as e:

            logger.exception(e)

            return Response(
                {
                    "success": False,
                    "message": "Something went wrong.",
                    "errors": {
                        "detail": str(e)
                    },
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ReportDetailAPIView(generics.RetrieveAPIView):

    serializer_class = ReportSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            Report.objects.filter(
                reporter=self.request.user
            )
            .select_related(
                "reporter",
                "reported_user",
                "booking",
                "assigned_admin",
            )
        )

    def retrieve(self, request, *args, **kwargs):

        try:

            report = self.get_object()

            serializer = self.get_serializer(report)

            return Response(
                {
                    "success": True,
                    "message": "Report retrieved successfully.",
                    "data": serializer.data,
                },
                status=status.HTTP_200_OK,
            )

        except Report.DoesNotExist:

            return Response(
                {
                    "success": False,
                    "message": "Report not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        except Exception as e:

            logger.exception(e)

            return Response(
                {
                    "success": False,
                    "message": "Something went wrong.",
                    "errors": {
                        "detail": str(e)
                    },
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# admin report list
import logging

from rest_framework import generics, status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from .models import Report
from .serializers import ReportSerializer

logger = logging.getLogger(__name__)


class AdminReportListAPIView(generics.ListAPIView):

    serializer_class = ReportSerializer
    permission_classes = [IsAdminUser]

    queryset = (
        Report.objects.select_related(
            "reporter",
            "reported_user",
            "booking",
            "assigned_admin",
        )
        .order_by("-created_at")
    )

    def list(self, request, *args, **kwargs):

        try:
            queryset = self.get_queryset()

            serializer = self.get_serializer(queryset, many=True)

            return Response(
                {
                    "success": True,
                    "message": "Reports retrieved successfully.",
                    "count": queryset.count(),
                    "results": serializer.data,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:

            logger.exception(e)

            return Response(
                {
                    "success": False,
                    "message": "Failed to retrieve reports.",
                    "errors": {
                        "detail": str(e)
                    },
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class AdminReportDetailAPIView(generics.RetrieveAPIView):

    serializer_class = ReportSerializer
    permission_classes = [IsAdminUser]

    queryset = (
        Report.objects.select_related(
            "reporter",
            "reported_user",
            "booking",
            "assigned_admin",
        )
    )

    def retrieve(self, request, *args, **kwargs):

        try:
            report = self.get_object()

            serializer = self.get_serializer(report)

            return Response(
                {
                    "success": True,
                    "message": "Report retrieved successfully.",
                    "data": serializer.data,
                },
                status=status.HTTP_200_OK,
            )

        except Report.DoesNotExist:

            return Response(
                {
                    "success": False,
                    "message": "Report not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        except Exception as e:

            logger.exception(e)

            return Response(
                {
                    "success": False,
                    "message": "Failed to retrieve report.",
                    "errors": {
                        "detail": str(e)
                    },
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )