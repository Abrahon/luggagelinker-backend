from django.shortcuts import render

# Create your views here.
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from django.db.models import Q
from .models import Review
from .serializers import ReviewSerializer
from django.db import transaction

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from rest_framework import generics
from rest_framework import permissions
from rest_framework import status
from rest_framework.response import Response

from .models import (
    Report,
    UserModerationProfile,
    ReportStatus,
    ActionTaken,
)

from .serializers import (
    CreateReportSerializer,
    ReportSerializer,
    ReportDetailSerializer,
    AdminResolveReportSerializer,
)

logger = logging.getLogger(__name__)


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
                user=review.traveler,
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




class ReportListCreateAPIView(generics.ListCreateAPIView):

    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):

        return (
            Report.objects.filter(
                reporter=self.request.user,
            )
            .select_related(
                "reporter__profile",
                "reported_user__profile",
                "assigned_admin",
                "booking",
            )
            .prefetch_related(
                "evidence_files",
            )
            .order_by("-created_at")
        )

    def get_serializer_class(self):

        if self.request.method == "POST":
            return CreateReportSerializer

        return ReportSerializer

    def list(self, request, *args, **kwargs):

        serializer = self.get_serializer(
            self.get_queryset(),
            many=True,
        )

        return Response(
            {
                "success": True,
                "message": "Reports retrieved successfully.",
                "count": self.get_queryset().count(),
                "data": serializer.data,
            }
        )

    def create(self, request, *args, **kwargs):

        serializer = self.get_serializer(
            data=request.data,
            context={
                "request": request,
            },
        )

        serializer.is_valid(
            raise_exception=True,
        )

        report = serializer.save()

        return Response(
            {
                "success": True,
                "message": "Report submitted successfully.",
                "data": ReportDetailSerializer(report).data,
            },
            status=status.HTTP_201_CREATED,
        )

class ReportDetailAPIView(generics.RetrieveAPIView):

    permission_classes = [permissions.IsAuthenticated]

    serializer_class = ReportDetailSerializer

    lookup_field = "id"

    def get_queryset(self):

        return (
            Report.objects.filter(
                reporter=self.request.user,
            )
            .select_related(
                "reporter__profile",
                "reported_user__profile",
                "assigned_admin",
                "booking",
            )
            .prefetch_related(
                "evidence_files",
            )
        )

class AdminReportListAPIView(generics.ListAPIView):

    permission_classes = [permissions.IsAdminUser]

    serializer_class = ReportSerializer

    queryset = (
        Report.objects.select_related(
            "reporter__profile",
            "reported_user__profile",
            "assigned_admin",
            "booking",
        )
        .prefetch_related(
            "evidence_files",
        )
        .order_by("-created_at")
    )

    def list(self, request, *args, **kwargs):

        serializer = self.get_serializer(
            self.get_queryset(),
            many=True,
        )

        return Response(
            {
                "success": True,
                "message": "Reports retrieved successfully.",
                "count": self.get_queryset().count(),
                "data": serializer.data,
            }
        )

class AdminReportDetailAPIView(generics.RetrieveAPIView):

    permission_classes = [permissions.IsAdminUser]

    serializer_class = ReportDetailSerializer

    lookup_field = "id"

    queryset = (
        Report.objects.select_related(
            "reporter__profile",
            "reported_user__profile",
            "assigned_admin",
            "booking",
        )
        .prefetch_related(
            "evidence_files",
        )
    )

class AdminResolveReportAPIView(generics.GenericAPIView):

    permission_classes = [permissions.IsAdminUser]

    serializer_class = AdminResolveReportSerializer

    queryset = Report.objects.select_related(
        "reported_user",
    )

    lookup_field = "id"

    @transaction.atomic
    def patch(self, request, *args, **kwargs):

        report = self.get_object()

        serializer = self.get_serializer(
            data=request.data,
        )

        serializer.is_valid(
            raise_exception=True,
        )

        data = serializer.validated_data

        moderation, _ = UserModerationProfile.objects.get_or_create(
            user=report.reported_user,
        )

        report.status = data["status"]

        report.is_valid = data["is_valid"]

        report.action_taken = data["action_taken"]

        report.admin_notes = data.get(
            "admin_notes",
            "",
        )

        report.assigned_admin = request.user

        if report.status in [
            ReportStatus.RESOLVED,
            ReportStatus.REJECTED,
        ]:
            report.resolved_at = timezone.now()

        if report.is_valid:

            moderation.valid_reports += 1

            moderation.trust_score = data.get(
                "trust_score",
                moderation.trust_score,
            )

            action = data["action_taken"]

            if action == ActionTaken.WARNING:

                moderation.warning_count += 1

            elif action == ActionTaken.SUSPEND:

                days = data.get(
                    "suspension_days",
                    7,
                )

                moderation.is_suspended = True

                moderation.suspended_until = (
                    timezone.now() +
                    timedelta(days=days)
                )

            elif action == ActionTaken.PERMANENT_BAN:

                moderation.is_banned = True

                moderation.banned_at = timezone.now()

                moderation.ban_reason = data.get(
                    "ban_reason",
                    "",
                )

        moderation.save()

        report.save()

        return Response(
            {
                "success": True,
                "message": "Report updated successfully.",
                "data": ReportDetailSerializer(report).data,
            }
        )