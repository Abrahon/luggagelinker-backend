from django.shortcuts import render

# Create your views here.
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from django.db.models import Q
from .models import Review
from .serializers import ReviewSerializer
from django.db import transaction

from datetime import timedelta
import logging

from django.db import transaction
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response

from apps.notifications.services import (
    notify_admin_new_report,
    notify_report_resolved,
    notify_user_warning,
    notify_user_suspended,
    notify_user_banned,
)
from .models import ActionTaken, Report, ReportStatus, UserModerationProfile


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





# ==========================================
# USER REPORT VIEWS
# ==========================================



class ReportListCreateAPIView(generics.ListCreateAPIView):
    """
    GET  /api/reports/            -> List reports submitted by current user
    POST /api/reports/            -> Submit a new report and notify admins
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            Report.objects.filter(reporter=self.request.user)
            .select_related(
                "reporter__profile",
                "reported_user__profile",
                "assigned_admin",
                "booking",
            )
            .prefetch_related("evidence_files")
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
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        report = serializer.save()

        # Trigger bulk admin notification (DB entry + WebSockets)
        try:
            notify_admin_new_report(report)
        except Exception as e:
            logger.error(f"Failed to send admin notification for report {report.id}: {str(e)}")

        return Response(
            {
                "success": True,
                "message": "Report submitted successfully.",
                "data": ReportDetailSerializer(report, context={"request": request}).data,
            },
            status=status.HTTP_201_CREATED,
        )


class ReportDetailAPIView(generics.RetrieveAPIView):
    """
    GET /api/reports/<uuid:id>/ -> Fetch details of a report submitted by current user
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ReportDetailSerializer
    lookup_field = "id"

    def get_queryset(self):
        return (
            Report.objects.filter(reporter=self.request.user)
            .select_related(
                "reporter__profile",
                "reported_user__profile",
                "assigned_admin",
                "booking",
            )
            .prefetch_related("evidence_files")
        )


# ==========================================
# ADMIN REPORT VIEWS
# ==========================================

class AdminReportListAPIView(generics.ListAPIView):
    """
    GET /api/admin/reports/ -> List all reports
    """
    permission_classes = [permissions.IsAdminUser]
    serializer_class = ReportSerializer

    def get_queryset(self):
        return (
            Report.objects.select_related(
                "reporter__profile",
                "reported_user__profile",
                "assigned_admin",
                "booking",
            )
            .prefetch_related("evidence_files")
            .order_by("-created_at")
        )

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(
            {
                "success": True,
                "message": "Reports retrieved successfully.",
                "count": queryset.count(),
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class AdminReportDetailAPIView(generics.RetrieveAPIView):
    """
    GET /api/admin/reports/<uuid:id>/ -> Fetch report details for admins
    """
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
        .prefetch_related("evidence_files")
    )


class AdminResolveReportAPIView(generics.GenericAPIView):
    """
    PATCH /api/admin/reports/<uuid:id>/resolve/
    Resolves/rejects report, applies moderation actions, and triggers notification alerts.
    """
    permission_classes = [permissions.IsAdminUser]
    serializer_class = AdminResolveReportSerializer
    lookup_field = "id"

    def get_queryset(self):
        return Report.objects.select_related("reported_user", "reporter")

    @transaction.atomic
    def patch(self, request, *args, **kwargs):
        report = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        moderation, _ = UserModerationProfile.objects.select_for_update().get_or_create(
            user=report.reported_user
        )

        # 1. Update report state
        report.status = data["status"]
        report.is_valid = data["is_valid"]
        report.action_taken = data["action_taken"]
        report.admin_notes = data.get("admin_notes", "")
        report.assigned_admin = request.user

        if report.status in [ReportStatus.RESOLVED, ReportStatus.REJECTED]:
            report.resolved_at = timezone.now()

        suspension_days = None

        # 2. Update target user moderation metrics if report is valid
        if report.is_valid:
            moderation.valid_reports += 1

            if "trust_score" in data:
                moderation.trust_score = data["trust_score"]

            action = data["action_taken"]

            if action == ActionTaken.WARNING:
                moderation.warning_count += 1

            elif action == ActionTaken.SUSPEND:
                suspension_days = data.get("suspension_days", 7)
                moderation.is_suspended = True
                moderation.suspended_until = timezone.now() + timedelta(days=suspension_days)

            elif action == ActionTaken.PERMANENT_BAN:
                moderation.is_banned = True
                moderation.banned_at = timezone.now()
                moderation.ban_reason = data.get("ban_reason", "")

                # Revoke user access immediately
                report.reported_user.is_active = False
                report.reported_user.save(update_fields=["is_active"])

        moderation.save()
        report.save()

        # 3. Dispatch Notifications
        try:
            # Notify reporter of review decision
            if report.status in [ReportStatus.RESOLVED, ReportStatus.REJECTED]:
                notify_report_resolved(report)

            # Notify reported user based on action taken
            if report.is_valid:
                action = report.action_taken

                if action == ActionTaken.WARNING:
                    notify_user_warning(report)

                elif action == ActionTaken.SUSPEND:
                    notify_user_suspended(report, days=suspension_days or 7)

                elif action == ActionTaken.PERMANENT_BAN:
                    notify_user_banned(report)

        except Exception as e:
            logger.error(f"Error dispatching notifications for report {report.id}: {str(e)}")

        return Response(
            {
                "success": True,
                "message": "Report updated successfully.",
                "data": ReportDetailSerializer(report, context={"request": request}).data,
            },
            status=status.HTTP_200_OK,
        )