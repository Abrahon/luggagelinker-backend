import logging
from django.db.models import Q
from django.core.exceptions import ValidationError as DjangoValidationError

from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.parsers import MultiPartParser, FormParser

from .models import Dispute
from .services import DisputeService
from .admin_services import AdminDisputeService
from .serializers import (
    DisputeSerializer,
    CreateDisputeSerializer,
    DisputeMessageSerializer,
    DisputeEvidenceSerializer,
    AdminDisputeSerializer
)

logger = logging.getLogger(__name__)


class DisputeErrorFormatMixin:
    """Reusable translation matrix formatting engine errors into clean JSON blocks."""
    def _format_error(self, error):
        if hasattr(error, 'message_dict'):
            return error.message_dict
        if hasattr(error, 'messages'):
            return {"detail": error.messages[0] if len(error.messages) == 1 else error.messages}
        return {"detail": str(error)}


# ==============================================================================
# 👤 STANDARD USER ENDPOINTS (Senders & Travelers)
# ==============================================================================

class DisputeListCreateAPIView(DisputeErrorFormatMixin, generics.ListCreateAPIView):
    """
    GET: List all disputes the current user is involved in.
    POST: Initialize a brand-new dispute filing.
    """
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Dispute.objects.filter(
            Q(opened_by=user) | Q(against_user=user)
        ).select_related(
            "booking", "opened_by", "against_user", "assigned_admin"
        ).prefetch_related(
            "messages__sender",
            "evidence__uploaded_by"
        ).order_by("-created_at")

    def get_serializer_class(self):
        if self.request.method == "POST":
            return CreateDisputeSerializer
        return DisputeSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            dispute = DisputeService.create_dispute(
                booking_id=serializer.validated_data["booking"].id,
                user=request.user,
                reason=serializer.validated_data["reason"],
                description=serializer.validated_data.get("description", ""),
                disputed_amount=serializer.validated_data["disputed_amount"]
            )
            
            output_serializer = DisputeSerializer(dispute, context=self.get_serializer_context())
            return Response({
                "message": "Dispute case file opened successfully and escrow protections activated.",
                "dispute": output_serializer.data
            }, status=status.HTTP_201_CREATED)

        except DjangoValidationError as e:
            logger.warning("Dispute creation rejected for user %s: %s", request.user.id, e)
            return Response(self._format_error(e), status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("Unexpected exception during dispute creation runtime for user %s", request.user.id)
            return Response({"detail": "Internal server error."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DisputeRetrieveAPIView(generics.RetrieveAPIView):
    """Retrieves full view tracking parameters for a specific dispute case file."""
    permission_classes = [IsAuthenticated]
    serializer_class = DisputeSerializer
    lookup_field = "id"

    def get_queryset(self):
        user = self.request.user
        return Dispute.objects.filter(
            Q(opened_by=user) | Q(against_user=user)
        ).select_related(
            "booking", "opened_by", "against_user", "assigned_admin"
        ).prefetch_related(
            "messages__sender",
            "evidence__uploaded_by"
        )


class DisputeAddMessageAPIView(DisputeErrorFormatMixin, generics.CreateAPIView):
    """Appends a new conversation comment thread item to an active user dispute claim."""
    permission_classes = [IsAuthenticated]
    serializer_class = DisputeMessageSerializer
    lookup_field = "id"

    def get_queryset(self):
        user = self.request.user
        return Dispute.objects.filter(Q(opened_by=user) | Q(against_user=user))

    def create(self, request, *args, **kwargs):
        dispute = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            message = DisputeService.add_message(
                dispute_id=dispute.id,
                sender=request.user,
                message_text=serializer.validated_data["message_text"]
            )
            output_serializer = DisputeMessageSerializer(message)
            return Response({
                "message": "Comment successfully attached to the dispute thread.",
                "message_detail": output_serializer.data
            }, status=status.HTTP_201_CREATED)

        except DjangoValidationError as e:
            return Response(self._format_error(e), status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("Unexpected exception inside append message path for dispute %s", dispute.id)
            return Response({"detail": "Internal server error."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from rest_framework import generics, status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

class DisputeAddEvidenceAPIView(DisputeErrorFormatMixin, generics.CreateAPIView):
    """
    Upload evidence for an existing dispute.
    """
    serializer_class = DisputeEvidenceSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    lookup_field = "id"

    def get_queryset(self):
        user = self.request.user
        return Dispute.objects.filter(
            Q(opened_by=user) | Q(against_user=user)
        )

    def create(self, request, *args, **kwargs):
        dispute = self.get_object()

        serializer = self.get_serializer(
            data=request.data,
            context={"dispute": dispute},
        )
        serializer.is_valid(raise_exception=True)

        try:
            evidence = DisputeService.add_evidence(
                dispute_id=dispute.id,
                uploaded_by=request.user,
                file_object=serializer.validated_data["file_attachment"],
                evidence_type=serializer.validated_data["evidence_type"],
                description=serializer.validated_data.get("description", ""),
            )

            return Response(
                {
                    "message": "Evidence uploaded successfully.",
                    "evidence_detail": DisputeEvidenceSerializer(evidence).data,
                },
                status=status.HTTP_201_CREATED,
            )

        except DjangoValidationError as exc:
            return Response(
                self._format_error(exc),
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception:
            logger.exception(
                "Unexpected error uploading evidence for dispute %s",
                dispute.id,
            )
            return Response(
                {"detail": "Internal server error."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
# ==============================================================================
# 🛡️ ADMINISTRATIVE MANAGEMENT ENDPOINTS (Staff / Superusers Only)
# ==============================================================================

class AdminDisputeListAPIView(generics.ListAPIView):
    """Returns a master overview list of all registered dispute files for auditing."""
    permission_classes = [IsAdminUser]
    serializer_class = AdminDisputeSerializer

    def get_queryset(self):
        return Dispute.objects.select_related(
            "booking", "opened_by", "against_user", "assigned_admin"
        ).prefetch_related(
            "messages__sender",
            "evidence__uploaded_by",
            "history__actor"
        ).order_by("-created_at")


class AdminDisputeRetrieveAPIView(generics.RetrieveAPIView):
    """Provides full, deep visibility into a specific dispute file for management staff."""
    permission_classes = [IsAdminUser]
    serializer_class = AdminDisputeSerializer
    lookup_field = "id"

    def get_queryset(self):
        return Dispute.objects.select_related(
            "booking", "opened_by", "against_user", "assigned_admin"
        ).prefetch_related(
            "messages__sender",
            "evidence__uploaded_by",
            "history__actor"
        )


class AdminDisputeAssignAPIView(DisputeErrorFormatMixin, generics.CreateAPIView):
    """Assigns the target dispute file directly to the authenticated moderator agent."""
    permission_classes = [IsAdminUser]
    serializer_class = AdminDisputeSerializer
    lookup_field = "id"

    def get_queryset(self):
        return Dispute.objects.all()

    def create(self, request, *args, **kwargs):
        dispute = self.get_object()
        try:
            updated_dispute = AdminDisputeService.assign_admin(
                dispute_id=dispute.id,
                admin_user=request.user
            )
            output = AdminDisputeSerializer(updated_dispute, context=self.get_serializer_context())
            return Response({
                "message": "Dispute file successfully assigned to your administrator account.",
                "dispute": output.data
            }, status=status.HTTP_200_OK)

        except DjangoValidationError as e:
            return Response(self._format_error(e), status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("Unexpected exception triggered during admin assignment trace for dispute %s", dispute.id)
            return Response({"detail": "Internal server error."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminDisputeRequestEvidenceAPIView(DisputeErrorFormatMixin, generics.CreateAPIView):
    """Dispatches a formal demand for additional supporting documentation to the users."""
    permission_classes = [IsAdminUser]
    serializer_class = AdminDisputeSerializer
    lookup_field = "id"

    def get_queryset(self):
        return Dispute.objects.all()

    def create(self, request, *args, **kwargs):
        dispute = self.get_object()
        message_text = request.data.get("message_text")

        if not message_text or not str(message_text).strip():
            return Response({"message_text": ["This payload content field cannot be left blank."]}, status=status.HTTP_400_BAD_REQUEST)

        try:
            updated_dispute = AdminDisputeService.request_more_evidence(
                dispute_id=dispute.id,
                admin_user=request.user,
                message_text=message_text
            )
            output = AdminDisputeSerializer(updated_dispute, context=self.get_serializer_context())
            return Response({
                "message": "Evidence request dispatched successfully. Target user tracking updated.",
                "dispute": output.data
            }, status=status.HTTP_200_OK)

        except DjangoValidationError as e:
            return Response(self._format_error(e), status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("Unexpected error encountered during evidence request execution on dispute %s", dispute.id)
            return Response({"detail": "Internal server error."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AdminDisputeResolveAPIView(DisputeErrorFormatMixin, generics.CreateAPIView):
    """Applies the final arbitration verdict and updates billing/booking states."""
    permission_classes = [IsAdminUser]
    serializer_class = AdminDisputeSerializer
    lookup_field = "id"

    def get_queryset(self):
        return Dispute.objects.all()

    def create(self, request, *args, **kwargs):
        dispute = self.get_object()
        resolution_type = request.data.get("resolution_type")
        admin_notes = request.data.get("admin_notes", "")
        refund_ratio = request.data.get("refund_ratio", "1.00")

        if not resolution_type:
            return Response({"resolution_type": ["This parameter field selection string is required."]}, status=status.HTTP_400_BAD_REQUEST)

        try:
            updated_dispute = AdminDisputeService.resolve(
                dispute_id=dispute.id,
                admin_user=request.user,
                resolution_type=resolution_type,
                admin_notes=admin_notes,
                refund_ratio=refund_ratio
            )
            output = AdminDisputeSerializer(updated_dispute, context=self.get_serializer_context())
            return Response({
                "message": f"Arbitration completed successfully. Verdict execution choice applied: {resolution_type}.",
                "dispute": output.data
            }, status=status.HTTP_200_OK)

        except DjangoValidationError as e:
            return Response(self._format_error(e), status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("Unexpected crash inside system settlement execution framework path for dispute %s", dispute.id)
            return Response({"detail": "Internal server error."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)