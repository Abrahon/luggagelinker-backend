from django.shortcuts import render

# Create your views here.
from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils.decorators import method_decorator
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter
from decimal import Decimal
import logging
from rest_framework import generics, status
from rest_framework.response import Response
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter

from apps.wallets.models import WithdrawalRequest
from apps.wallets.serializers import WithdrawalRequestSerializer
from core.permissions import IsPlatformAdmin
from apps.wallets.services import AdminWithdrawalService

from .models import Wallet, WalletTransaction, WithdrawalRequest
from .serializers import (
    WalletSerializer, 
    WalletTransactionSerializer, 
    WithdrawalRequestSerializer
)
from .services import WalletService

logger = logging.getLogger(__name__)





class WalletViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint that allows users to view their wallet details and transaction ledger.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = WalletSerializer

    def get_queryset(self):
        # Scope execution precisely to the authenticated user profile instance
        return Wallet.objects.filter(user=self.request.user)

    def list(self, request, *args, **kwargs):
        """Override list to return a single wallet directly instead of an array."""
        try:
            wallet = Wallet.objects.get(user=request.user)
            serializer = self.get_serializer(wallet)
            return Response(serializer.data)
        except Wallet.DoesNotExist:
            return Response(
                {"detail": "Financial profile wallet instance missing."}, 
                status=status.HTTP_404_NOT_FOUND
            )


class WalletTransactionListView(generics.ListAPIView):
    """
    High-performance history feed optimized with index hits, filtering capabilities, and pagination boundaries.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = WalletTransactionSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ["type", "status", "booking"]
    ordering_fields = ["created_at", "amount"]
    ordering = ["-created_at"]  # Match composite database index sequence layout

    def get_queryset(self):
        return WalletTransaction.objects.filter(
            wallet__user=self.request.user
        ).select_related("booking")




# Inside apps/wallets/views.py - ensure it looks exactly like this:


# ✅ Clean concrete class replacement: handling both GET and POST natively
class WithdrawalRequestView(generics.ListCreateAPIView):
    """
    Handles initialization of payout pipelines (POST) and provides 
    historical processing visibility (GET).
    """
    permission_classes = [IsAuthenticated]
    serializer_class = WithdrawalRequestSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ["status"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return WithdrawalRequest.objects.filter(wallet__user=self.request.user)

    def create(self, request, *args, **kwargs):
        """Overrides the POST creation hooks to inject business service layer rules."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        amount = Decimal(str(serializer.validated_data["amount"]))
        bank_account_info = serializer.validated_data["bank_account_info"]

        try:
            withdrawal = WalletService.request_withdrawal(
                user=request.user,
                amount=amount,
                bank_account_info=bank_account_info
            )
            response_serializer = self.get_serializer(withdrawal)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
            
        except ValueError as exc:
            return Response(
                {"non_field_errors": [str(exc)]}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception:
            return Response(
                {"detail": "An error occurred while routing payment systems processing."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )



# admin service class for handling withdrawal approvals, rejections, and marking as paid


class AdminWithdrawalListView(generics.ListAPIView):
    """
    GET /api/admin/withdrawals/
    Provides platform administrators audit oversight logs over user cashouts.
    """
    permission_classes = [IsPlatformAdmin]
    serializer_class = WithdrawalRequestSerializer
    queryset = WithdrawalRequest.objects.all().select_related('wallet__user')
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ["status"]
    ordering = ["-created_at"]


class AdminWithdrawalDetailView(generics.RetrieveAPIView):
    """
    GET /api/admin/withdrawals/{id}/
    Granular isolated inspection hook for a specific withdrawal request.
    """
    permission_classes = [IsPlatformAdmin]
    serializer_class = WithdrawalRequestSerializer
    queryset = WithdrawalRequest.objects.all()


class AdminWithdrawalActionBaseView(generics.GenericAPIView):
    """
    Base structural generic view providing uniform validation parsing, log capture,
    and standardized API error responses.
    """
    permission_classes = [IsPlatformAdmin]
    serializer_class = WithdrawalRequestSerializer
    queryset = WithdrawalRequest.objects.all()

    def handle_action_execution(self, service_method, status_label, *args, **kwargs):
        try:
            # Route execution down to the atomic database service transaction layer
            withdrawal = service_method(*args, **kwargs)
            
            return Response(
                {
                    "success": True,
                    "message": f"Withdrawal pipeline successfully updated to state: {status_label}.",
                    "data": self.get_serializer(withdrawal).data
                },
                status=status.HTTP_200_OK
            )
            
        except (DjangoValidationError, DRFValidationError) as exc:
            # 🟢 Cleanly unpack and flatten complex validation messages into a clean array
            error_messages = []
            if hasattr(exc, 'message_dict'):
                for field, errors in exc.message_dict.items():
                    error_messages.extend(errors)
            elif hasattr(exc, 'messages'):
                error_messages = exc.messages
            elif hasattr(exc, 'detail'):
                if isinstance(exc.detail, dict):
                    for field, details in exc.detail.items():
                        error_messages.extend([str(d) for d in details])
                elif isinstance(exc.detail, list):
                    error_messages = [str(d) for d in exc.detail]
                else:
                    error_messages = [str(exc.detail)]
            else:
                error_messages = [str(exc)]

            return Response(
                {
                    "success": False,
                    "message": "Action validation failed.",
                    "errors": error_messages
                },
                status=status.HTTP_400_BAD_REQUEST
            )
            
        except Exception as e:
            logger.error(
                f"Critical framework crash processing admin operation on "
                f"Withdrawal ID {kwargs.get('withdrawal_id')}: {str(e)}", 
                exc_info=True
            )
            return Response(
                {
                    "success": False,
                    "message": "An internal processing system error occurred.",
                    "errors": [str(e)]
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AdminWithdrawalApproveView(AdminWithdrawalActionBaseView):
    """
    POST /api/admin/withdrawals/{id}/approve/
    Approves the withdrawal request without duplicating ledger deductions.
    """
    def post(self, request, pk, *args, **kwargs):
        return self.handle_action_execution(
            AdminWithdrawalService.approve_withdrawal,
            status_label="APPROVED",
            withdrawal_id=pk,
            admin_user=request.user
        )


class AdminWithdrawalRejectView(AdminWithdrawalActionBaseView):
    """
    POST /api/admin/withdrawals/{id}/reject/
    Rejects the request and automatically issues a refund to the traveler's liquid balance.
    """
    def post(self, request, pk, *args, **kwargs):
        reason = request.data.get("rejection_reason", "").strip()
        
        # Immediate validation for missing request parameters before calling core service layers
        if not reason:
            return Response(
                {
                    "success": False,
                    "message": "Action validation failed.",
                    "errors": ["A valid 'rejection_reason' string value is required to reject a request."]
                },
                status=status.HTTP_400_BAD_REQUEST
            )
            
        return self.handle_action_execution(
            AdminWithdrawalService.reject_withdrawal,
            status_label="REJECTED",
            withdrawal_id=pk,
            admin_user=request.user,
            rejection_reason=reason
        )


class AdminWithdrawalMarkPaidView(AdminWithdrawalActionBaseView):
    """
    POST /api/admin/withdrawals/{id}/mark-paid/
    Marks an approved administrative checkout request as completely settled via banking rails.
    """
    def post(self, request, pk, *args, **kwargs):
        return self.handle_action_execution(
            AdminWithdrawalService.mark_as_paid,
            status_label="PAID",
            withdrawal_id=pk,
            admin_user=request.user
        )