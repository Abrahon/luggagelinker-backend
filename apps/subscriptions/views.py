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
                {
                    "detail": "Plan is already inactive."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        plan.is_active = False
        plan.save(update_fields=["is_active"])

        return Response(
            {
                "detail": "Plan deleted successfully."
            },
            status=status.HTTP_200_OK,
        )