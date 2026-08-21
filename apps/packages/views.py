from django.shortcuts import render

# Create your views here.
import logging

from django.db import transaction

from rest_framework import generics, request, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from .models import Package
from .serializers import PackageSerializer
from django.db.models import F

from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.exceptions import NotFound
import cloudinary.uploader

from django.db import transaction

from rest_framework import generics
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db import models
from rest_framework import generics, status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from django.db.models import Count
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from apps.packages.models import Package, PackageStatus
from apps.packages.serializers import PackageDashboardStatsSerializer
from .models import PackageImage
from .models import Package
from .serializers import PackageSerializer
logger = logging.getLogger(__name__)
import logging
from cloudinary.uploader import upload
from django.db import transaction
from rest_framework import generics, status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from apps.packages.serializers import PackageSerializer,AdminReviewSerializer
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from apps.packages.services import PackageService  
from .models import Package, PackageImage
from .serializers import PackageImageSerializer
from apps.matching.services.package_matching import run_package_matching

from .models import Package, PackageImage,PackageStatus, VerificationStatus
from .serializers import (
    PackageImageSerializer,
    PackageImageUploadSerializer,
)


class CreatePackageView(generics.CreateAPIView):
    serializer_class = PackageSerializer
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def create(self, request, *args, **kwargs):

        serializer = self.get_serializer(
            data=request.data,
            context={"request": request},
        )

        try:
            serializer.is_valid(raise_exception=True)

            # ----------------------------------------------------
            # 1. Create Package
            # ----------------------------------------------------
            package = serializer.save()

            # ----------------------------------------------------
            # 2. Run Risk Analysis
            # ----------------------------------------------------
            PackageService.process_and_evaluate_risk(package)

            # ----------------------------------------------------
            # 3. Keep package hidden until admin approves
            # ----------------------------------------------------
            package.status = PackageStatus.DRAFT
            package.is_active = False
            package.is_public = False

            package.save(
                update_fields=[
                    "status",
                    "is_active",
                    "is_public",
                ]
            )

            logger.info(
                f"Package submitted for review | "
                f"Package={package.id} | "
                f"Risk={package.risk_score} | "
                f"Verification={package.verification_status} | "
                f"User={request.user.id}"
            )

            return Response(
                {
                    "success": True,
                    "message": (
                        "Package submitted successfully. "
                        "Your package is awaiting admin review."
                    ),
                    "data": PackageSerializer(package).data,
                },
                status=status.HTTP_201_CREATED,
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

        except Exception as e:
            logger.exception(
                f"Package creation failed | User={request.user.id}"
            )

            return Response(
                {
                    "success": False,
                    "message": "Unable to create package at this time.",
                    "error": str(e),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        

class MyPackageListView(generics.ListAPIView):
    serializer_class = PackageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = (
            Package.objects.filter(
                sender=self.request.user,
            )
            .prefetch_related("images")
            .order_by("-created_at")
        )

        status_param = self.request.query_params.get("status")

        if status_param:
            queryset = queryset.filter(status=status_param)

        return queryset

    def list(self, request, *args, **kwargs):
        try:
            queryset = self.get_queryset()

            serializer = self.get_serializer(
                queryset,
                many=True,
            )

            return Response(
                {
                    "success": True,
                    "message": "Packages fetched successfully.",
                    "count": queryset.count(),
                    "data": serializer.data,
                },
                status=status.HTTP_200_OK,
            )

        except Exception:
            logger.exception(
                f"Failed to fetch packages. User={request.user.id}"
            )

            return Response(
                {
                    "success": False,
                    "message": "Unable to fetch packages.",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class TravelerPackageListView(generics.ListAPIView):
    """
    Traveler Package Marketplace

    Returns only packages that have been approved
    and published by the admin.
    """

    serializer_class = PackageSerializer
    permission_classes = [IsAuthenticated]

    pagination_class = None  # Use your pagination if you have one

    def get_queryset(self):
        return (
            Package.objects.filter(
                status=PackageStatus.PUBLISHED,
                is_active=True,
                is_public=True,
            )
            .select_related("sender")
            .prefetch_related("images")
            .order_by("-created_at")
        )

    def list(self, request, *args, **kwargs):

        queryset = self.get_queryset()

        serializer = self.get_serializer(
            queryset,
            many=True,
        )

        return Response(
            {
                "success": True,
                "message": "Published packages retrieved successfully.",
                "count": queryset.count(),
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


class PackageDetailView(generics.RetrieveAPIView):
    serializer_class = PackageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        # If user is logged in, show active packages OR their own pending/draft packages
        if user.is_authenticated:
            return Package.objects.filter(
                models.Q(is_active=True) | models.Q(sender=user)
            )

        # Unauthenticated public users can only view active packages
        return Package.objects.filter(is_active=True)

    def retrieve(self, request, *args, **kwargs):
        package = self.get_queryset().filter(pk=kwargs["pk"]).first()

        if not package:
            raise NotFound("Package not found.")

        serializer = self.get_serializer(package)

        return Response(
            {
                "success": True,
                "message": "Package fetched successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


from django.db import transaction
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from apps.packages.models import Package, PackageStatus
from apps.packages.serializers import PackageSerializer

import logging

logger = logging.getLogger(__name__)


class PackageManageView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PackageSerializer
    permission_classes = [IsAuthenticated]

    # DO NOT set lookup_field = "id"

    def get_queryset(self):
        return (
            Package.objects.filter(
                sender=self.request.user
            ).prefetch_related("images")
        )

    # ==========================================================
    # GET
    # ==========================================================

    def retrieve(self, request, *args, **kwargs):
        package = self.get_object()

        serializer = self.get_serializer(
            package,
            context={"request": request},
        )

        return Response(
            {
                "success": True,
                "message": "Package fetched successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    # ==========================================================
    # PATCH / PUT
    # ==========================================================

    @transaction.atomic
    def update(self, request, *args, **kwargs):

        package = self.get_object()

        serializer = self.get_serializer(
            package,
            data=request.data,
            partial=True,
            context={"request": request},
        )

        try:
            serializer.is_valid(raise_exception=True)

            package = serializer.save()

            package.refresh_from_db()

            logger.info(
                f"Package updated successfully. Package={package.id}"
            )

            return Response(
                {
                    "success": True,
                    "message": "Package updated successfully.",
                    "data": PackageSerializer(
                        package,
                        context={"request": request},
                    ).data,
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
                f"Package update failed. Package={package.id}"
            )

            return Response(
                {
                    "success": False,
                    "message": "Unable to update package.",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # ==========================================================
    # DELETE (Soft Delete)
    # ==========================================================

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):

        package = self.get_object()

        try:
            package.status = PackageStatus.CANCELLED
            package.is_active = False
            package.is_public = False

            package.save(
                update_fields=[
                    "status",
                    "is_active",
                    "is_public",
                ]
            )

            logger.info(
                f"Package deleted successfully. Package={package.id}"
            )

            return Response(
                {
                    "success": True,
                    "message": "Package deleted successfully.",
                },
                status=status.HTTP_200_OK,
            )

        except Exception:
            logger.exception(
                f"Package delete failed. Package={package.id}"
            )

            return Response(
                {
                    "success": False,
                    "message": "Unable to delete package.",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
# =========================
# UPLOAD IMAGE
# =========================
class UploadPackageImageView(generics.CreateAPIView):
    serializer_class = PackageImageUploadSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = (
        MultiPartParser,
        FormParser,
    )
    MAX_IMAGES = 5

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        # REMOVED is_active=True so owners can upload images while package is under review/inactive
        package = Package.objects.filter(
            id=kwargs["package_id"],
            sender=request.user,
        ).first()

        if not package:
            return Response(
                {
                    "success": False,
                    "message": "Package not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if package.images.count() >= self.MAX_IMAGES:
            return Response(
                {
                    "success": False,
                    "message": f"You can upload a maximum of {self.MAX_IMAGES} images.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        image = serializer.validated_data["image"]

        try:
            result = upload(
                image,
                folder="packages",
            )
        except Exception:
            return Response(
                {
                    "success": False,
                    "message": "Failed to upload image to Cloudinary.",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        package_image = PackageImage.objects.create(
            package=package,
            image=result["secure_url"],
            is_primary=package.images.count() == 0,
        )

        return Response(
            {
                "success": True,
                "message": "Image uploaded successfully.",
                "data": PackageImageSerializer(package_image).data,
            },
            status=status.HTTP_201_CREATED,
        )


# =========================
# LIST PACKAGE IMAGES
# =========================
class PackageImageListView(generics.ListAPIView):
    serializer_class = PackageImageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        package = Package.objects.filter(
            id=self.kwargs["package_id"],
            sender=self.request.user,
        ).first()
        if not package:
            return PackageImage.objects.none()
        return PackageImage.objects.filter(
            package=package
        ).order_by("-is_primary", "-created_at")

    def list(self, request, *args, **kwargs):
        package = Package.objects.filter(
            id=kwargs["package_id"],
            sender=request.user,
        ).first()
        if not package:
            return Response(
                {
                    "success": False,
                    "message": "Package not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        queryset = self.get_queryset()
        serializer = self.get_serializer(
            queryset,
            many=True,
        )
        return Response(
            {
                "success": True,
                "message": "Package images fetched successfully.",
                "count": queryset.count(),
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


# =========================
# DELETE / UPDATE PACKAGE IMAGE
# =========================
class DeleteUpdatePackageImageView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PackageImageSerializer
    lookup_field = "id"

    def get_queryset(self):
        # REMOVED package__is_active=True
        return PackageImage.objects.select_related("package").filter(
            package__sender=self.request.user
        )

    # ... rest of your methods (destroy, partial_update) remain unchanged

from django.db.models import Q

from rest_framework import generics
from rest_framework.permissions import IsAdminUser

from apps.packages.models import Package
from .serializers import AdminPackageSerializer


class AdminPackageListView(generics.ListAPIView):

    serializer_class = AdminPackageSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):

        queryset = Package.objects.select_related(
            "sender",
            "sender__profile",
        ).prefetch_related(
            "images",
        )

        status = self.request.query_params.get("status")
        verification = self.request.query_params.get("verification")
        category = self.request.query_params.get("category")
        search = self.request.query_params.get("search")

        if status:
            queryset = queryset.filter(status=status)

        if verification:
            queryset = queryset.filter(
                verification_status=verification
            )

        if category:
            queryset = queryset.filter(category=category)

        if search:
            queryset = queryset.filter(
                Q(title__icontains=search)
                | Q(sender__email__icontains=search)
                | Q(pickup_city__icontains=search)
                | Q(destination_city__icontains=search)
            )

        return queryset.order_by("-created_at")



class AdminPackageDetailView(generics.RetrieveAPIView):

    serializer_class = AdminPackageSerializer
    permission_classes = [IsAdminUser]

    queryset = Package.objects.select_related(
        "sender",
        "sender__profile",
    ).prefetch_related(
        "images",
    )



# admin 
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
import traceback

class AdminPackageReviewView(APIView):
    """
    PATCH /api/package/<uuid:pk>/admin-review/

    Body:
    {
        "approve": true
    }

    approve=true  -> VERIFIED + PUBLISHED
    approve=false -> REJECTED + CANCELLED
    """

    permission_classes = [IsAuthenticated, IsAdminUser]

    def patch(self, request, pk):

        package = get_object_or_404(Package, pk=pk)

        serializer = AdminReviewSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "message": "Validation failed.",
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        approve = serializer.validated_data["approve"]

        try:

            # DEBUG (remove later)
            print("Package:", package.id)
            print("Verification:", package.verification_status)
            print("Approve:", approve)

            updated_package = PackageService.review_package(
                package=package,
                approve=approve,
            )

            action = (
                "verified and published"
                if approve
                else "rejected and cancelled"
            )

            return Response(
                {
                    "success": True,
                    "message": f"Package has been {action}.",
                    "data": PackageSerializer(updated_package).data,
                },
                status=status.HTTP_200_OK,
            )

        except ValueError as e:

            return Response(
                {
                    "success": False,
                    "message": str(e),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception as e:

            traceback.print_exc()

            return Response(
                {
                    "success": False,
                    "message": str(e),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from apps.packages.models import Package, PackageStatus
from apps.matching.models import Match, MatchStatus
from apps.bookings.models import Booking, BookingStatus


class PackageDashboardStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        user = request.user

        packages = Package.objects.filter(sender=user)

        bookings = Booking.objects.filter(sender=user)

        matched = Match.objects.filter(
            package__sender=user,
            status=MatchStatus.AVAILABLE,
            is_active=True,
        ).values("package").distinct().count()

        data = {
            "total": packages.count(),

            "draft": packages.filter(
                status=PackageStatus.DRAFT
            ).count(),

            "published": packages.filter(
                status=PackageStatus.PUBLISHED
            ).count(),

            "matched": matched,

            "booked": bookings.filter(
                status__in=[
                    BookingStatus.CONFIRMED,
                    BookingStatus.PICKED_UP,
                    BookingStatus.IN_TRANSIT,
                    BookingStatus.DELIVERED,
                    BookingStatus.COMPLETED,
                ]
            ).count(),

            "delivered": bookings.filter(
                status=BookingStatus.COMPLETED
            ).count(),
        }

        return Response(
            {
                "success": True,
                "message": "Package dashboard statistics retrieved successfully.",
                "data": data,
            },
            status=status.HTTP_200_OK,
        )

# apps/trips/views.py
# apps/trips/views.py
from django.contrib.auth import get_user_model

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from apps.bookings.models import Booking, BookingStatus

from .serializers import SenderProfileSerializer


User = get_user_model()


class SenderProfileAPIView(APIView):
    """
    Public sender profile endpoint.

    Shows:
    - Basic profile information
    - Contact information
    - Email verification status
    - Sending statistics
    - Success rate
    - Account creation date
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, sender_id):

        # ======================================================
        # 1. GET SENDER
        # ======================================================

        sender = (
            User.objects
            .select_related("profile")
            .filter(
                id=sender_id,
                is_active=True,
            )
            .first()
        )

        if sender is None:
            return Response(
                {
                    "success": False,
                    "message": "Sender not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # ======================================================
        # 2. ALL SENDER BOOKINGS
        # ======================================================

        sender_bookings = Booking.objects.filter(
            sender_id=sender.id
        )

        # ======================================================
        # 3. SUCCESSFUL / COMPLETED DELIVERIES
        # ======================================================

        successful_deliveries = (
            sender_bookings
            .filter(
                status=BookingStatus.COMPLETED
            )
            .count()
        )

        # ======================================================
        # 4. CANCELLED DELIVERIES
        # ======================================================

        cancelled_deliveries = (
            sender_bookings
            .filter(
                status=BookingStatus.CANCELLED
            )
            .count()
        )

        # ======================================================
        # 5. TOTAL FINALIZED PACKAGES
        #
        # Pending / active bookings are not included.
        #
        # Total =
        # completed + cancelled
        # ======================================================

        total_packages = (
            successful_deliveries
            + cancelled_deliveries
        )

        # ======================================================
        # 6. SUCCESS RATE
        # ======================================================

        if total_packages > 0:

            success_rate = round(
                (
                    successful_deliveries
                    / total_packages
                ) * 100,
                1,
            )

        else:

            success_rate = 0.0

        # ======================================================
        # 7. TEMPORARY SERIALIZER VALUES
        # ======================================================

        sender.total_packages_value = (
            total_packages
        )

        sender.successful_deliveries_value = (
            successful_deliveries
        )

        sender.cancelled_deliveries_value = (
            cancelled_deliveries
        )

        sender.success_rate_value = (
            success_rate
        )

        # ======================================================
        # 8. EMAIL VERIFICATION
        #
        # User.is_verified comes from your User model.
        #
        # is_verified = True
        #     -> email verified
        #
        # is_verified = False
        #     -> email not verified
        # ======================================================

        sender.is_email_verified_value = bool(
            sender.is_verified
        )

        # ======================================================
        # 9. SERIALIZER
        # ======================================================

        serializer = SenderProfileSerializer(
            sender,
            context={
                "request": request,
            },
        )

        # ======================================================
        # 10. RESPONSE
        # ======================================================

        return Response(
            {
                "success": True,
                "message": (
                    "Sender profile retrieved "
                    "successfully."
                ),
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )