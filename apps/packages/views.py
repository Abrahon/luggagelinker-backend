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
from apps.packages.serializers import PackageSerializer
from apps.packages.services import PackageService  # 🧠 Import our service layer
from .models import Package, PackageImage
from .serializers import PackageImageSerializer
from apps.matching.services.package_matching import run_package_matching

from .models import Package, PackageImage
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
            
            # 1. Save the basic package instance as a draft safely
            package = serializer.save()

            # 2. Run the decoupled safety engine to compute the risk score & verification_status
            PackageService.process_and_evaluate_risk(package)

            # 3. Try publishing via the business policy routing rule block
            is_published = PackageService.publish_package(package)

            # 4. SAFETY CHECK: Only match if it bypassed review barriers and went public!
            if is_published:
                run_package_matching(package)
                user_message = "Package created and published successfully."
            else:
                user_message = "Package submitted successfully and is currently under administrative review."

            logger.info(
                f"Package processed | Package={package.id} | "
                f"Status={package.status} | Verification={package.verification_status} | User={request.user.id}"
            )

            return Response(
                {
                    "success": True,
                    "message": user_message,
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




class PackageDetailView(generics.RetrieveAPIView):

    serializer_class = PackageSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):

        return Package.objects.filter(
            is_active=True,
        )

    def retrieve(self, request, *args, **kwargs):

        package = self.get_queryset().filter(
            pk=kwargs["pk"]
        ).first()

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

        package = Package.objects.filter(
            id=kwargs["package_id"],
            sender=request.user,
            is_active=True,
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





class PackageImageListView(generics.ListAPIView):

    serializer_class = PackageImageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):

        package = Package.objects.filter(
            id=self.kwargs["package_id"],
            sender=self.request.user,
            is_active=True,
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
            is_active=True,
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






class DeleteUpdatePackageImageView(generics.RetrieveUpdateDestroyAPIView):

    permission_classes = [IsAuthenticated]
    serializer_class = PackageImageSerializer

    lookup_field = "id"

    def get_queryset(self):
        return PackageImage.objects.select_related("package").filter(
            package__sender=self.request.user,
            package__is_active=True
        )

    # =========================
    # DELETE
    # =========================

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):

        image = self.get_object()

        try:
            if getattr(image, "public_id", None):
                cloudinary.uploader.destroy(image.public_id)
        except Exception:
            pass

        image.delete()

        return Response(
            {
                "success": True,
                "message": "Image deleted successfully.",
            },
            status=status.HTTP_200_OK,
        )

    # =========================
    # UPDATE (PATCH)
    # =========================

    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):

        image = self.get_object()

        is_primary = request.data.get("is_primary")

        if is_primary is not None:

            PackageImage.objects.filter(
                package=image.package
            ).update(is_primary=False)

            image.is_primary = bool(is_primary)
            image.save(update_fields=["is_primary"])

        return Response(
            {
                "success": True,
                "message": "Image updated successfully.",
                "data": PackageImageSerializer(image).data,
            },
            status=status.HTTP_200_OK,
        )