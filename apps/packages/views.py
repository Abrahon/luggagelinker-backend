from django.shortcuts import render

# Create your views here.
import logging

from django.db import transaction

from rest_framework import generics, status
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
        return (
            Package.objects.filter(
                sender=self.request.user,
                is_active=True,
            )
            .order_by("-created_at")
        )

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




class PackageManageView(generics.RetrieveUpdateDestroyAPIView):

    serializer_class = PackageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):

        return Package.objects.filter(
            sender=self.request.user,
            is_active=True,
        )

    # ==========================================
    # UPDATE
    # ==========================================

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

            logger.info(
                f"Package updated successfully. "
                f"Package={package.id}"
            )

            return Response(
                {
                    "success": True,
                    "message": "Package updated successfully.",
                    "data": PackageSerializer(package).data,
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

    # ==========================================
    # DELETE (Soft Delete)
    # ==========================================

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):

        package = self.get_object()

        try:

            package.is_active = False
            package.save(update_fields=["is_active"])

            logger.info(
                f"Package deleted successfully. "
                f"Package={package.id}"
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



# uplaod image

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

# class TravelerHandshakeView(generics.UpdateAPIView):
#     """
#     PATCH /package/<uuid:pk>/handshake/
#     Executed strictly by the assigned Traveler at the physical pick-up point.
#     """
#     queryset = Package.objects.all()
#     permission_classes = [IsAuthenticated]
#     serializer_class = PackageSerializer

#     def patch(self, request, *args, **kwargs):
#         package = self.get_object()
#         user = request.user

#         # 1. Traveler Authorization check (Protects endpoint access)
#         has_active_booking = package.bookings.filter(traveler=user, is_active=True).exists()
#         if not has_active_booking:
#             raise PermissionDenied("You are not authorized to perform the physical handshake verification for this package.")

#         # 2. Schema Validation (Handles cross-field validation rules internally)
#         input_serializer = TravelerHandshakeSerializer(data=request.data)
#         if not input_serializer.is_valid():
#             return Response({
#                 "success": False,
#                 "message": "Validation failed.",
#                 "errors": input_serializer.errors
#             }, status=status.HTTP_400_BAD_REQUEST)

#         matches_listing = input_serializer.validated_data["traveler_matches_listing"]
#         refusal_reason = input_serializer.validated_data.get("traveler_refusal_reason", "").strip()

#         package.traveler_matches_listing = matches_listing

#         # 3. Route Lifecycle States cleanly
#         if matches_listing:
#             package.status = PackageStatus.IN_TRANSIT
#             package.traveler_refusal_reason = None
#             update_fields = ["traveler_matches_listing", "status", "traveler_refusal_reason"]
#             msg = "Handshake clear. Package status updated to In Transit."
#         else:
#             package.status = PackageStatus.CANCELLED
#             package.verification_status = VerificationStatus.REJECTED
#             package.traveler_refusal_reason = refusal_reason
#             update_fields = ["traveler_matches_listing", "status", "verification_status", "traveler_refusal_reason"]
#             msg = "Traveler refused package handoff. Listing has been cancelled and flagged for fraud check."

#         # 4. Atomic field updates
#         package.save(update_fields=update_fields)
        
#         return Response({
#             "success": True,
#             "message": msg,
#             "data": PackageSerializer(package).data
#         }, status=status.HTTP_200_OK)
    