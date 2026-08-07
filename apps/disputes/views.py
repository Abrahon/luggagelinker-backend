import logging
from django.db.migrations import serializer
from django.db.models import Q
from django.core.exceptions import ValidationError as DjangoValidationError

from rest_framework import generics, request, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.parsers import MultiPartParser, FormParser

from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from apps.disputes.models import (
    Dispute,
    DisputeHistory,
)
from apps.disputes.enums import (
    DisputeStatus,
    DisputeHistoryAction,
)
from .models import Dispute
from .services import DisputeService
from .admin_services import AdminDisputeService
from .serializers import (
    AdminRequestEvidenceSerializer,
    AdminResolveDisputeSerializer,
    DisputeSerializer,
    CreateDisputeSerializer,
    DisputeMessageSerializer,
    DisputeEvidenceSerializer,
    AdminDisputeSerializer,
    AdminDisputeAssignSerializer

)
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from rest_framework import generics, status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

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
    POST: Initialize a brand-new dispute filing with optional multipart form-data evidence files.
    """
    permission_classes = [IsAuthenticated]
    
    # Enable Form-Data and File Upload Support alongside standard JSON
    parser_classes = [MultiPartParser, FormParser, JSONParser]

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

        # Retrieve optional uploaded files (handles both 'evidence_files' and 'evidence' keys)
        evidence_files = request.FILES.getlist('evidence_files') or request.FILES.getlist('evidence')

        try:
            dispute = DisputeService.create_dispute(
                booking_id=serializer.validated_data["booking_id"],
                user=request.user,
                reason=serializer.validated_data["reason"],
                description=serializer.validated_data["description"],
                disputed_amount=serializer.validated_data["disputed_amount"],
                evidence_files=serializer.validated_data.get("evidence_files", []),
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

class AdminDisputeAssignAPIView(
    DisputeErrorFormatMixin,
    generics.CreateAPIView,
):
    permission_classes = [IsAdminUser]

    serializer_class = AdminDisputeAssignSerializer

    lookup_field = "id"

    def get_queryset(self):
        return Dispute.objects.select_related(
            "assigned_admin",
        )

    def create(self, request, *args, **kwargs):

        dispute = self.get_object()

        try:

            updated_dispute = AdminDisputeService.assign_admin(
                dispute_id=dispute.id,
                admin_user=request.user,
            )

            serializer = self.get_serializer(
                updated_dispute
            )

            return Response(
                {
                    "success": True,
                    "message": "Dispute assigned successfully.",
                    "data": serializer.data,
                },
                status=status.HTTP_200_OK,
            )

        except DjangoValidationError as e:

            return Response(
                self._format_error(e),
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception:

            logger.exception(
                "Unexpected exception triggered during admin assignment trace for dispute %s",
                dispute.id,
            )

            return Response(
                {
                    "success": False,
                    "message": "Internal server error.",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

class AdminDisputeRequestEvidenceAPIView(
    DisputeErrorFormatMixin,
    generics.CreateAPIView,
):
    """
    Request additional evidence from the sender/traveler.
    """

    permission_classes = [IsAdminUser]

    serializer_class = AdminRequestEvidenceSerializer

    lookup_field = "id"

    def get_queryset(self):
        return Dispute.objects.select_related(
            "booking",
            "opened_by",
            "against_user",
            "assigned_admin",
        )

    def create(self, request, *args, **kwargs):

        dispute = self.get_object()

        serializer = self.get_serializer(
            data=request.data
        )

        serializer.is_valid(raise_exception=True)

        try:

            updated_dispute = (
                AdminDisputeService.request_more_evidence(
                    dispute_id=dispute.id,
                    admin_user=request.user,
                    message_text=serializer.validated_data[
                        "request_message"
                    ],
                )
            )

            return Response(
                {
                    "success": True,
                    "message": "Evidence request sent successfully.",
                    "data": {
                        "id": updated_dispute.id,
                        "status": updated_dispute.status,
                        "status_display": updated_dispute.get_status_display(),
                        "requested_evidence": serializer.validated_data[
                            "request_message"
                        ],
                        "updated_at": updated_dispute.updated_at,
                    },
                },
                status=status.HTTP_200_OK,
            )

        except DjangoValidationError as e:

            return Response(
                self._format_error(e),
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception:

            logger.exception(
                "Unexpected error while requesting evidence for dispute %s",
                dispute.id,
            )

            return Response(
                {
                    "success": False,
                    "message": "Failed to request additional evidence.",
                    "errors": {
                        "detail": "Internal server error.",
                    },
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        



class AdminDisputeResolveAPIView(
    DisputeErrorFormatMixin,
    generics.GenericAPIView
):
    permission_classes = [IsAdminUser]
    serializer_class = AdminResolveDisputeSerializer
    queryset = Dispute.objects.all()
    lookup_field = "id"

    def post(self, request, *args, **kwargs):
        dispute = self.get_object()

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        resolution = serializer.validated_data["resolution_type"]
        refund_ratio = serializer.validated_data["refund_ratio"]
        admin_notes = serializer.validated_data["admin_notes"]

        try:

            updated_dispute = AdminDisputeService.resolve(
                dispute_id=dispute.id,
                admin_user=request.user,
                resolution_type=resolution,
                refund_ratio=refund_ratio,
                admin_notes=admin_notes,
            )

            total_amount = updated_dispute.disputed_amount

            sender_refund = (
                total_amount * refund_ratio
            ).quantize(Decimal("0.01"))

            traveler_payout = (
                total_amount - sender_refund
            ).quantize(Decimal("0.01"))

            return Response(
                {
                    "success": True,
                    "message": "Dispute resolved successfully.",

                    "data": {
                        "id": str(updated_dispute.id),

                        "status": updated_dispute.status,
                        "status_display": updated_dispute.get_status_display(),

                        "resolution": updated_dispute.resolution,
                        "resolution_display": updated_dispute.get_resolution_display(),

                        "refund_ratio": str(refund_ratio),

                        "total_amount": str(total_amount),

                        "sender_refund": str(sender_refund),

                        "traveler_payout": str(traveler_payout),

                        "resolved_at": updated_dispute.resolved_at,

                        "resolved_by": {
                            "id": str(request.user.id),
                            "email": request.user.email,
                            "full_name": request.user.get_full_name(),
                        },

                        "booking": {
                            "id": str(updated_dispute.booking.id),
                            "tracking_number": updated_dispute.booking.tracking_number,
                            "status": updated_dispute.booking.status,
                            "payment_status": updated_dispute.booking.payment_status,
                        },
                    }
                },
                status=status.HTTP_200_OK,
            )

        except DjangoValidationError as e:
            logger.warning(
                "Dispute resolution rejected: %s",
                e
            )
            return Response(
                self._format_error(e),
                status=status.HTTP_400_BAD_REQUEST
            )

        except Exception:
            logger.exception(
                "Unexpected dispute resolution failure."
            )
            return Response(
                {
                    "detail": "Internal server error."
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class DisputeWithdrawAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, id):

        try:
            dispute = Dispute.objects.get(id=id)

        except Dispute.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Dispute not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if dispute.opened_by != request.user:
            return Response(
                {
                    "success": False,
                    "message": "Only the dispute creator can withdraw this dispute.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if dispute.status not in [
            DisputeStatus.OPEN,
            DisputeStatus.UNDER_REVIEW,
        ]:
            return Response(
                {
                    "success": False,
                    "message": "Only active disputes can be withdrawn.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        previous = dispute.status

        dispute.status = DisputeStatus.REJECTED
        dispute.resolved_at = timezone.now()
        dispute.last_updated_by = request.user
        dispute.save()

        DisputeHistory.objects.create(
            dispute=dispute,
            actor=request.user,
            action=DisputeHistoryAction.WITHDRAWN,
            status_from=previous,
            status_to=DisputeStatus.REJECTED,
            notes="Dispute withdrawn by creator.",
        )

        return Response(
            {
                "success": True,
                "message": "Dispute withdrawn successfully.",
            }
        )



from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView


class AdminDisputeStatusAPIView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, id):
        try:
            dispute = Dispute.objects.get(id=id)
        except Dispute.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Dispute not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        new_status = request.data.get("status")

        if not new_status:
            return Response(
                {
                    "success": False,
                    "message": "Status is required.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if new_status not in DisputeStatus.values:
            return Response(
                {
                    "success": False,
                    "message": "Invalid status.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        previous_status = dispute.status

        if previous_status == new_status:
            return Response(
                {
                    "success": False,
                    "message": "Dispute is already in this status.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        dispute.status = new_status
        dispute.last_updated_by = request.user

        if new_status in (
            DisputeStatus.RESOLVED,
            DisputeStatus.REJECTED,
            DisputeStatus.CLOSED,
        ):
            dispute.resolved_at = timezone.now()

        dispute.save(
            update_fields=[
                "status",
                "last_updated_by",
                "resolved_at",
                "updated_at",
            ]
        )

        history_action = self._get_history_action(new_status)

        DisputeHistory.objects.create(
            dispute=dispute,
            actor=request.user,
            action=history_action,
            status_from=previous_status,
            status_to=new_status,
            notes=f"Status changed from '{previous_status}' to '{new_status}'.",
        )

        return Response(
            {
                "success": True,
                "message": "Dispute status updated successfully.",
                "data": {
                    "id": str(dispute.id),
                    "previous_status": previous_status,
                    "current_status": dispute.status,
                },
            },
            status=status.HTTP_200_OK,
        )

    @staticmethod
    def _get_history_action(status_value):
        """
        Maps dispute status to audit history action.
        """

        mapping = {
            DisputeStatus.OPEN: DisputeHistoryAction.OPENED,
            DisputeStatus.UNDER_REVIEW: DisputeHistoryAction.ASSIGNED,
            DisputeStatus.WAITING_FOR_USER: DisputeHistoryAction.EVIDENCE_REQUESTED,
            DisputeStatus.RESOLVED: DisputeHistoryAction.RESOLVED_RELEASE,
            DisputeStatus.REJECTED: DisputeHistoryAction.REJECTED,
            DisputeStatus.CLOSED: DisputeHistoryAction.CLOSED,
        }

        return mapping[status_value]


class AdminDisputeNoteAPIView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, id):

        try:
            dispute = Dispute.objects.get(id=id)

        except Dispute.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Dispute not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        note = request.data.get("admin_notes")

        if not note:
            return Response(
                {
                    "success": False,
                    "message": "Admin note is required.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        dispute.admin_notes += f"\n\n{note}"
        dispute.last_updated_by = request.user
        dispute.save()

        DisputeHistory.objects.create(
            dispute=dispute,
            actor=request.user,
            action=DisputeHistoryAction.ADMIN_NOTE,
            status_from=dispute.status,
            status_to=dispute.status,
            notes=note,
        )

        return Response(
            {
                "success": True,
                "message": "Admin note added successfully.",
            }
        )