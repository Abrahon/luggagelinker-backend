from django.shortcuts import render

# Create your views here.
from django.db import transaction

from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.exceptions import NotFound

from apps.subscriptions.models import Plan
from apps.subscriptions.serializers import PlanSerializer
from shared.permissions import IsAdmin
from datetime import timedelta
from django.utils import timezone

from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated


from apps.subscriptions.models import (
    Plan,
    Subscription,
    SubscriptionStatus,
)
from apps.subscriptions.serializers import SubscriptionSerializer



class PlanListView(generics.ListAPIView):

    serializer_class = PlanSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return (
            Plan.objects.filter(
                is_active=True,
                is_public=True,
            )
            .order_by("sort_order", "price")
        )

    def list(self, request, *args, **kwargs):

        queryset = self.get_queryset()

        serializer = self.get_serializer(queryset, many=True)

        return Response(
            {
                "detail": "Plans fetched successfully.",
                "count": queryset.count(),
                "results": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


# public plan
class PlanDetailView(generics.RetrieveAPIView):

    serializer_class = PlanSerializer
    permission_classes = [AllowAny]
    lookup_field = "slug"

    def get_queryset(self):
        return Plan.objects.filter(
            is_active=True,
            is_public=True,
        )

    def retrieve(self, request, *args, **kwargs):

        instance = self.get_queryset().filter(
            slug=kwargs["slug"]
        ).first()

        if not instance:
            raise NotFound("Plan not found.")

        serializer = self.get_serializer(instance)

        return Response(
            {
                "detail": "Plan fetched successfully.",
                "plan": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class PlanCreateView(generics.CreateAPIView):

    serializer_class = PlanSerializer
    permission_classes = [IsAdmin]

    @transaction.atomic
    def create(self, request, *args, **kwargs):

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        plan = serializer.save()

        return Response(
            {
                "detail": "Plan created successfully.",
                "plan": PlanSerializer(plan).data,
            },
            status=status.HTTP_201_CREATED,
        )


class PlanUpdateView(generics.UpdateAPIView):

    serializer_class = PlanSerializer
    permission_classes = [IsAdmin]
    queryset = Plan.objects.all()

    @transaction.atomic
    def update(self, request, *args, **kwargs):

        instance = self.get_object()

        serializer = self.get_serializer(
            instance,
            data=request.data,
            partial=True,
        )

        serializer.is_valid(raise_exception=True)

        plan = serializer.save()

        return Response(
            {
                "detail": "Plan updated successfully.",
                "plan": PlanSerializer(plan).data,
            },
            status=status.HTTP_200_OK,
        )

class PlanDeleteView(generics.DestroyAPIView):

    permission_classes = [IsAdmin]
    queryset = Plan.objects.all()

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):

        plan = self.get_object()

        if not plan.is_active:
            return Response(
                {"detail": "Plan is already inactive."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        plan.is_active = False
        plan.is_public = False   # 🔥 ADD THIS (important)
        plan.save(update_fields=["is_active", "is_public"])

        return Response(
            {"detail": "Plan deactivated successfully."},
            status=status.HTTP_200_OK,
        )






# ===========================================================
# CREATE SUBSCRIPTION
# ===========================================================

class CreateSubscriptionView(generics.CreateAPIView):

    serializer_class = SubscriptionSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        plan = serializer.validated_data["plan"]

        try:

            with transaction.atomic():

                active_subscription = Subscription.objects.filter(
                    user=request.user,
                    is_current=True,
                    status__in=[
                        SubscriptionStatus.ACTIVE,
                        SubscriptionStatus.TRIAL,
                    ],
                ).first()

                if active_subscription:
                    return Response(
                        {
                            "detail": "You already have an active subscription."
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                started_at = timezone.now()

                expires_at = started_at + timedelta(
                    days=plan.duration_days
                )

                subscription = Subscription.objects.create(
                    user=request.user,
                    plan=plan,
                    status=SubscriptionStatus.ACTIVE,
                    started_at=started_at,
                    expires_at=expires_at,
                    auto_renew=True,
                    is_current=True,
                )

                data = SubscriptionSerializer(subscription).data

                return Response(
                    {
                        "success": True,
                        "message": "Subscription created successfully.",
                        "data": data,
                    },
                    status=status.HTTP_201_CREATED,
                )

        except Exception as e:

            return Response(
                {
                    "success": False,
                    "message": "Failed to create subscription.",
                    "error": str(e),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# ===========================================================
# CURRENT SUBSCRIPTION
# ===========================================================

class CurrentSubscriptionView(generics.RetrieveAPIView):

    serializer_class = SubscriptionSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):

        subscription = Subscription.objects.filter(
            user=request.user,
            is_current=True,
        ).select_related("plan").first()

        if not subscription:

            return Response(
                {
                    "success": False,
                    "message": "No active subscription found."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                "success": True,
                "message": "Subscription fetched successfully.",
                "data": SubscriptionSerializer(subscription).data,
            }
        )


# ===========================================================
# SUBSCRIPTION HISTORY
# ===========================================================

class SubscriptionHistoryView(generics.ListAPIView):

    serializer_class = SubscriptionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):

        return (
            Subscription.objects
            .filter(user=self.request.user)
            .select_related("plan")
            .order_by("-created_at")
        )

    def list(self, request, *args, **kwargs):

        queryset = self.get_queryset()

        serializer = self.get_serializer(
            queryset,
            many=True
        )

        return Response(
            {
                "success": True,
                "message": "Subscription history fetched successfully.",
                "count": queryset.count(),
                "data": serializer.data,
            }
        )


# ===========================================================
# CANCEL SUBSCRIPTION
# ===========================================================

class CancelSubscriptionView(generics.UpdateAPIView):

    permission_classes = [IsAuthenticated]

    def patch(self, request, *args, **kwargs):

        subscription = Subscription.objects.filter(
            user=request.user,
            is_current=True,
            status=SubscriptionStatus.ACTIVE,
        ).first()

        if not subscription:

            return Response(
                {
                    "success": False,
                    "message": "No active subscription found."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        subscription.status = SubscriptionStatus.CANCELLED
        subscription.cancelled_at = timezone.now()
        subscription.auto_renew = False
        subscription.is_current = False

        subscription.save()

        return Response(
            {
                "success": True,
                "message": "Subscription cancelled successfully."
            },
            status=status.HTTP_200_OK,
        )

