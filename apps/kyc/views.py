from django.shortcuts import render

# Create your views here.
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError
from django.utils import timezone
from apps.kyc.models import KYC
from apps.kyc.serializers import KYCSerializer
from rest_framework import generics
from shared.utils.ocr import extract_text_from_url
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError

from apps.kyc.models import KYC, KYCStatus
from rest_framework.exceptions import ValidationError
from apps.kyc.models import KYC
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser

from apps.kyc.models import KYC, KYCStatus
from apps.kyc.serializers import AdminKYCDetailSerializer, KYCRejectSerializer



class KYCCreateView(generics.CreateAPIView):
    """
    Submit KYC Initial payload
    POST /api/kyc/
    """
    serializer_class = KYCSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        if KYC.objects.filter(user=self.request.user).exists():
            raise ValidationError({"detail": "You have already submitted your KYC."})

        # Step 1: Write safely to database once
        kyc = serializer.save()

        # Step 2: Isolation protection wrapper for third party operations
        if kyc.document_front:
            try:
                text = extract_text_from_url(kyc.document_front.url)
                # Production roadmap recommendation: 
                # Fire an async Celery task instead of locking the HTTP thread here!
                print("\n========== OCR RESULT ==========")
                print(text)
                print("================================\n")
            except Exception as e:
                # Log error telemetry here safely without crashing user experience
                print(f"OCR Processing failed gracefully: {str(e)}")





class MyKYCView(generics.RetrieveUpdateAPIView):
    """
    Manage user context KYC asset instances
    GET /api/kyc/me/
    PATCH /api/kyc/me/
    """
    serializer_class = KYCSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        # Clean execution flow instead of an unhandled HTTP 500 error
        return get_object_or_404(KYC, user=self.request.user)

    def perform_update(self, serializer):
        kyc = self.get_object()
        if kyc.status == KYCStatus.APPROVED:
            raise ValidationError({"detail": "Approved KYC records cannot be modified."})
        serializer.save()






# admin views from django.utils import timezone
class AdminKYCListView(generics.ListAPIView):
    """
    GET /admin/kyc/
    """
    queryset = KYC.objects.select_related("user", "user__profile", "verified_by").all()
    serializer_class = AdminKYCDetailSerializer
    permission_classes = [IsAdminUser]


class AdminKYCDetailView(generics.RetrieveAPIView):
    """
    GET /admin/kyc/<id>/
    """
    queryset = KYC.objects.select_related("user", "user__profile", "verified_by").all()
    serializer_class = AdminKYCDetailSerializer
    permission_classes = [IsAdminUser]
    lookup_field = "id"


class AdminKYCApproveView(APIView):
    """
    POST /admin/kyc/<id>/approve/
    """
    permission_classes = [IsAdminUser]

    def post(self, request, id):
        try:
            kyc = KYC.objects.get(id=id)
        except KYC.DoesNotExist:
            return Response(
                {"error": "KYC application not found."}, 
                status=status.HTTP_404_NOT_FOUND
            )

        if kyc.status == KYCStatus.APPROVED:
            return Response(
                {"error": "Action failed. This KYC application is already approved."},
                status=status.HTTP_400_BAD_REQUEST
            )

        kyc.status = KYCStatus.APPROVED
        kyc.rejection_reason = None
        kyc.verified_at = timezone.now()
        kyc.verified_by = request.user
        kyc.save()

        serializer = AdminKYCDetailSerializer(kyc)
        return Response({
            "message": "KYC application has been successfully approved.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)


class AdminKYCRejectView(APIView):
    """
    POST /admin/kyc/<id>/reject/
    """
    permission_classes = [IsAdminUser]

    def post(self, request, id):
        try:
            kyc = KYC.objects.get(id=id)
        except KYC.DoesNotExist:
            return Response(
                {"error": "KYC application not found."}, 
                status=status.HTTP_404_NOT_FOUND
            )

        if kyc.status == KYCStatus.REJECTED:
            return Response(
                {"error": "Action failed. This KYC application is already marked as rejected."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Triggers dynamic validation for rejection_reason structure
        serializer = KYCRejectSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                "error": "Validation failed.",
                "details": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        kyc.status = KYCStatus.REJECTED
        kyc.rejection_reason = serializer.validated_data["rejection_reason"]
        kyc.verified_at = timezone.now()
        kyc.verified_by = request.user
        kyc.save()

        response_serializer = AdminKYCDetailSerializer(kyc)
        return Response({
            "message": "KYC application has been successfully rejected.",
            "data": response_serializer.data
        }, status=status.HTTP_200_OK)


class AdminKYCRequestResubmissionView(APIView):
    """
    POST /admin/kyc/<id>/request-resubmission/
    """
    permission_classes = [IsAdminUser]

    def post(self, request, id):
        try:
            kyc = KYC.objects.get(id=id)
        except KYC.DoesNotExist:
            return Response(
                {"error": "KYC application not found."}, 
                status=status.HTTP_404_NOT_FOUND
            )

        if kyc.status == KYCStatus.APPROVED:
            return Response(
                {"error": "Action failed. Cannot request resubmission for an already approved KYC verification."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Triggers dynamic validation for rejection_reason structure
        serializer = KYCRejectSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                "error": "Validation failed.",
                "details": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        # Revert status to pending so your traveler user can edit it again
        kyc.status = KYCStatus.PENDING
        kyc.rejection_reason = serializer.validated_data["rejection_reason"]
        kyc.verified_at = None
        kyc.verified_by = request.user
        kyc.save()

        response_serializer = AdminKYCDetailSerializer(kyc)
        return Response({
            "message": "Resubmission request sent successfully. Status reverted to pending.",
            "data": response_serializer.data
        }, status=status.HTTP_200_OK)