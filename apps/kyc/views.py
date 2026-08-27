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
from rest_framework.exceptions import NotFound

from apps.kyc.models import KYC, KYCStatus
from rest_framework.exceptions import ValidationError
from apps.kyc.models import KYC
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser

from apps.kyc.models import KYC, KYCStatus
from apps.kyc.serializers import AdminKYCDetailSerializer, KYCRejectSerializer,KYCUpdateSerializer

from apps.notifications.services import (
    notify_kyc_rejected,
    notify_admins_kyc_submitted,
    notify_kyc_approved
)




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

        # Step 2: Notify Admins of the new submission
        notify_admins_kyc_submitted(traveler=self.request.user, kyc=kyc)

        # Step 3: Isolation protection wrapper for third party operations
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
    Retrieve or Update the KYC record for the logged-in user.
    Endpoint: /api/kyc/me/
    """
    serializer_class = KYCSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        try:
            return KYC.objects.get(user=self.request.user)
        except KYC.DoesNotExist:
            return None

    def get(self, request, *args, **kwargs):
        instance = self.get_object()
        if not instance:
            return Response(
                {"detail": "No KYC submission found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def get_serializer_class(self):
        if self.request.method in ["PUT", "PATCH"]:
            return KYCUpdateSerializer
        return KYCSerializer

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()

        if not instance:
            return Response(
                {"detail": "No KYC record exists to update. Please submit first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if instance.status == KYCStatus.APPROVED:
            return Response(
                {"detail": "Approved KYC cannot be modified."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        
        # When user updates a rejected or pending KYC, reset status back to PENDING
        serializer.save(status=KYCStatus.PENDING, rejection_reason=None)

        return Response(serializer.data, status=status.HTTP_200_OK)






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

        # Notify the user that their KYC was approved
        notify_kyc_approved(user=kyc.user, kyc=kyc)

        serializer = AdminKYCDetailSerializer(kyc)
        return Response({
            "message": "KYC application has been successfully approved.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)





class AdminKYCRejectView(APIView):
    """
    POST /admin/kyc/<id>/reject/

    Admin rejects a KYC application and provides
    a rejection reason.

    After successful rejection:
        - KYC status becomes REJECTED
        - rejection reason is stored
        - verified_by stores the admin
        - verified_at stores the rejection time
        - KYC owner receives a notification
    """

    permission_classes = [IsAdminUser]

    def post(self, request, id):

        # ======================================================
        # FIND KYC APPLICATION
        # ======================================================

        try:
            kyc = KYC.objects.select_related(
                "user"
            ).get(id=id)

        except KYC.DoesNotExist:
            return Response(
                {
                    "error": "KYC application not found."
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # ======================================================
        # PREVENT DUPLICATE REJECTION
        # ======================================================

        if kyc.status == KYCStatus.REJECTED:
            return Response(
                {
                    "error": (
                        "Action failed. This KYC application "
                        "is already marked as rejected."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ======================================================
        # VALIDATE REJECTION REASON
        # ======================================================

        serializer = KYCRejectSerializer(
            data=request.data
        )

        if not serializer.is_valid():
            return Response(
                {
                    "error": "Validation failed.",
                    "details": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ======================================================
        # REJECT KYC
        # ======================================================

        kyc.status = KYCStatus.REJECTED

        kyc.rejection_reason = (
            serializer.validated_data["rejection_reason"]
        )

        kyc.verified_at = timezone.now()

        kyc.verified_by = request.user

        kyc.save(
            update_fields=[
                "status",
                "rejection_reason",
                "verified_at",
                "verified_by",
                "updated_at",
            ]
        )

        # ======================================================
        # SEND NOTIFICATION TO KYC OWNER
        # ======================================================

        notify_kyc_rejected(
            user=kyc.user,
            kyc=kyc,
        )

        # ======================================================
        # RESPONSE
        # ======================================================

        response_serializer = AdminKYCDetailSerializer(
            kyc
        )

        return Response(
            {
                "message": (
                    "KYC application has been "
                    "successfully rejected."
                ),
                "data": response_serializer.data,
            },
            status=status.HTTP_200_OK,
        )
    

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



class MyKYCUpdateView(generics.UpdateAPIView):
    """
    Update KYC information for the authenticated user.

    PATCH /api/kyc/me/update/
    PUT   /api/kyc/me/update/

    Allowed:
        PENDING
        REJECTED

    Not allowed:
        UNDER_REVIEW
        APPROVED
    """

    serializer_class = KYCUpdateSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        try:
            return KYC.objects.get(user=self.request.user)
        except KYC.DoesNotExist:
            raise NotFound("No KYC record found.")

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        kyc = self.get_object()

        # APPROVED check
        if kyc.status == KYCStatus.APPROVED:
            return Response(
                {
                    "success": False,
                    "message": "Your KYC has already been approved and cannot be modified.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # UNDER REVIEW check
        if kyc.status == KYCStatus.UNDER_REVIEW:
            return Response(
                {
                    "success": False,
                    "message": "Your KYC is currently under review and cannot be modified.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(
            kyc,
            data=request.data,
            partial=partial,
        )

        serializer.is_valid(raise_exception=True)

        if kyc.status == KYCStatus.REJECTED:
            updated_kyc = serializer.save(
                status=KYCStatus.PENDING,
                rejection_reason=None,
                verified_at=None,
                verified_by=None,
            )
            message = (
                "KYC updated and resubmitted successfully. "
                "Your documents are waiting for admin review."
            )
        else:
            updated_kyc = serializer.save(
                status=KYCStatus.PENDING,
                rejection_reason=None,
            )
            message = "KYC updated successfully."

        # Notify Admins when a user updates/resubmits their KYC
        notify_admins_kyc_submitted(traveler=request.user, kyc=updated_kyc)

        return Response(
            {
                "success": True,
                "message": message,
                "data": KYCSerializer(updated_kyc).data,
            },
            status=status.HTTP_200_OK,
        )

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)