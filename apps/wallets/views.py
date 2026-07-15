import logging
import traceback
from decimal import Decimal

import stripe
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.payment.providers.stripe_connect import StripeConnectProvider
from core.permissions import IsPlatformAdmin

from .models import (
    StripeConnectedAccount,
    Wallet,
    WalletTransaction,
    WithdrawalMethod,
    WithdrawalRequest,
)
from .serializers import (
    StripeConnectSerializer,
    WalletRecentActivitySerializer,
    WalletSerializer,
    WalletTransactionSerializer,
    WithdrawalMethodSerializer,
    WithdrawalRequestSerializer,
)
from .services import AdminWithdrawalService, WalletService

logger = logging.getLogger(__name__)


def format_validation_error(exc):
    """
    Utility helper to extract messages from DRF validation exceptions, 
    Django validations, or database model level validation issues.
    Unpacks dictionaries, nested lists, and outputs a simple list of flat string errors.
    """
    error_messages = []
    if hasattr(exc, 'message_dict'):
        for field, errors in exc.message_dict.items():
            if isinstance(errors, list):
                error_messages.extend([f"{field}: {e}" for e in errors])
            else:
                error_messages.append(f"{field}: {errors}")
    elif hasattr(exc, 'messages'):
        error_messages = exc.messages
    elif hasattr(exc, 'detail'):
        if isinstance(exc.detail, dict):
            for field, details in exc.detail.items():
                if isinstance(details, list):
                    error_messages.extend([f"{field}: {str(d)}" for d in details])
                else:
                    error_messages.append(f"{field}: {str(details)}")
        elif isinstance(exc.detail, list):
            error_messages = [str(d) for d in exc.detail]
        else:
            error_messages = [str(exc.detail)]
    else:
        error_messages = [str(exc)]
    return error_messages


class WalletViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint that allows users to view their wallet details and transaction ledger.
    GET /wallets/
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
    GET /wallets/transactions/
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




class WithdrawalMethodListCreateView(generics.ListCreateAPIView):
    serializer_class = WithdrawalMethodSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            WithdrawalMethod.objects.filter(
                user=self.request.user,
                is_active=True,
            )
            .order_by("-is_default", "-created_at")
        )

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)

        return Response(
            {
                "success": True,
                "message": "Withdrawal methods retrieved successfully.",
                "count": queryset.count(),
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "message": "Validation failed.",
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer.save(user=request.user)

        return Response(
            {
                "success": True,
                "message": "Withdrawal method created successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )


class WithdrawalMethodRetrieveUpdateDestroyView(
    generics.RetrieveUpdateDestroyAPIView
):
    serializer_class = WithdrawalMethodSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return WithdrawalMethod.objects.filter(
            user=self.request.user
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()

        return Response(
            {
                "success": True,
                "message": "Withdrawal method retrieved successfully.",
                "data": self.get_serializer(instance).data,
            },
            status=status.HTTP_200_OK,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)

        instance = self.get_object()

        serializer = self.get_serializer(
            instance,
            data=request.data,
            partial=partial,
        )

        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "message": "Validation failed.",
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer.save()

        return Response(
            {
                "success": True,
                "message": "Withdrawal method updated successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()

        instance.is_active = False
        instance.save(update_fields=["is_active"])

        return Response(
            {
                "success": True,
                "message": "Withdrawal method deleted successfully.",
            },
            status=status.HTTP_200_OK,
        )


class WithdrawalRequestView(generics.ListCreateAPIView):
    """
    GET  /wallets/withdrawals/
    POST /wallets/withdraw/
    """

    permission_classes = [IsAuthenticated]
    serializer_class = WithdrawalRequestSerializer

    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ["status"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return (
            WithdrawalRequest.objects.filter(
                wallet__user=self.request.user
            )
            .select_related(
                "wallet",
                "wallet__user",
                "withdrawal_method",
            )
        )

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        serializer = self.get_serializer(queryset, many=True)

        return Response(
            {
                "success": True,
                "message": "Withdrawal requests retrieved successfully.",
                "count": queryset.count(),
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    def create(self, request, *args, **kwargs):

        serializer = self.get_serializer(
            data=request.data,
            context={"request": request},
        )

        if not serializer.is_valid():
            return Response(
                {
                    "success": False,
                    "message": "Validation failed.",
                    "errors": serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        amount = serializer.validated_data["amount"]

        withdrawal_method = serializer.validated_data["withdrawal_method"]

        try:

            withdrawal = WalletService.withdraw(
                user=request.user,
                amount=amount,
                withdrawal_method=withdrawal_method,
            )

            response_serializer = self.get_serializer(withdrawal)

            return Response(
                {
                    "success": True,
                    "message": "Withdrawal request submitted successfully.",
                    "data": response_serializer.data,
                },
                status=status.HTTP_201_CREATED,
            )

        except (
            ValueError,
            DjangoValidationError,
            DRFValidationError,
        ) as exc:

            return Response(
                {
                    "success": False,
                    "message": "Withdrawal request failed.",
                    "errors": format_validation_error(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception:

            logger.exception("Withdrawal creation failed.")

            return Response(
                {
                    "success": False,
                    "message": "Internal server error.",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

class SetDefaultWithdrawalMethodView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):

        try:
            method = WithdrawalMethod.objects.get(
                pk=pk,
                user=request.user,
                is_active=True,
            )
        except WithdrawalMethod.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "message": "Withdrawal method not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        WithdrawalMethod.objects.filter(
            user=request.user,
            is_default=True,
        ).update(is_default=False)

        method.is_default = True
        method.save(update_fields=["is_default"])

        return Response(
            {
                "success": True,
                "message": "Default withdrawal method updated successfully.",
                "data": WithdrawalMethodSerializer(method).data,
            },
            status=status.HTTP_200_OK,
        )

class AdminWithdrawalListView(generics.ListAPIView):
    """
    Oversight monitor feed for admin managers to query platform-wide cashout queues.
    GET /admin/withdrawals/
    """
    permission_classes = [IsPlatformAdmin]
    serializer_class = WithdrawalRequestSerializer
    queryset = WithdrawalRequest.objects.all().select_related('wallet__user')
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ["status"]
    ordering = ["-created_at"]


class AdminWithdrawalDetailView(generics.RetrieveAPIView):
    """
    Granular information profile for reviewing a specific checkout queue request.
    GET /admin/withdrawals/{id}/
    """
    permission_classes = [IsPlatformAdmin]
    serializer_class = WithdrawalRequestSerializer
    queryset = WithdrawalRequest.objects.all()


class AdminWithdrawalActionBaseView(generics.GenericAPIView):
    """
    Base generic utility structure mapping errors from services 
    and returning dynamic responses.
    """
    permission_classes = [IsPlatformAdmin]
    serializer_class = WithdrawalRequestSerializer
    queryset = WithdrawalRequest.objects.all()

    def handle_action_execution(self, service_method, status_label, *args, **kwargs):
        try:
            # Route processing to administrative service layer
            withdrawal = service_method(*args, **kwargs)
            
            return Response(
                {
                    "success": True,
                    "message": f"Withdrawal request status updated to: {status_label}.",
                    "data": self.get_serializer(withdrawal).data
                },
                status=status.HTTP_200_OK
            )
            
        except (DjangoValidationError, DRFValidationError) as exc:
            return Response(
                {
                    "success": False,
                    "message": "Action validation failed.",
                    "errors": format_validation_error(exc)
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(
                f"Framework failure tracking operational logic on "
                f"Withdrawal ID {kwargs.get('withdrawal_id')}: {str(e)}", 
                exc_info=True
            )
            return Response(
                {
                    "success": False,
                    "message": "An internal error occurred during request settlement.",
                    "errors": [str(e)]
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AdminWithdrawalApproveView(AdminWithdrawalActionBaseView):
    """
    Approve withdrawal requests after reviewing matching documentation.
    POST /admin/withdrawals/{id}/approve/
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
    Rejects the request and immediately processes systemic refunds back to the target wallet.
    POST /admin/withdrawals/{id}/reject/
    """
    def post(self, request, pk, *args, **kwargs):
        reason = request.data.get("rejection_reason", "").strip()
        
        if not reason:
            return Response(
                {
                    "success": False,
                    "message": "Action validation failed.",
                    "errors": ["A clear rejection reason is required for administrative tracking purposes."]
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
    Signals that an approved cashout request has successfully processed via wire or localized rails.
    POST /admin/withdrawals/{id}/mark-paid/
    """
    def post(self, request, pk, *args, **kwargs):
        return self.handle_action_execution(
            AdminWithdrawalService.mark_as_paid,
            status_label="PAID",
            withdrawal_id=pk,
            admin_user=request.user
        )


class UserCancelWithdrawalView(generics.GenericAPIView):
    """
    Enables user cancellations for requests in PENDING status.
    POST /wallets/withdrawals/{id}/cancel/
    """
    permission_classes = [IsAuthenticated]
    serializer_class = WithdrawalRequestSerializer

    def post(self, request, pk, *args, **kwargs):
        try:
            withdrawal = WalletService.cancel_withdrawal(withdrawal_id=pk, user=request.user)
            
            return Response(
                {
                    "success": True,
                    "message": "Withdrawal request cancelled successfully. Funds have been returned to your wallet.",
                    "data": self.get_serializer(withdrawal).data
                },
                status=status.HTTP_200_OK
            )
        except (DjangoValidationError, DRFValidationError) as exc:
            return Response(
                {
                    "success": False, 
                    "errors": format_validation_error(exc)
                }, 
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Error canceling user withdrawal: {str(e)}")
            return Response(
                {
                    "success": False,
                    "errors": [str(e)]
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AdminAdjustBalanceView(generics.GenericAPIView):
    """
    Administrative manual configuration tool to fix error layouts, manually settle issues, 
    or run updates with proper logging.
    
    POST /admin/wallets/{wallet_id}/adjust/
    """
    permission_classes = [IsPlatformAdmin]

    def post(self, request, wallet_id, *args, **kwargs):
        delta_amount = request.data.get("delta_amount")
        reason = request.data.get("reason", "").strip()

        if not delta_amount:
            return Response({"success": False, "errors": ["'delta_amount' must be a valid, non-zero decimal string."]}, status=status.HTTP_400_BAD_REQUEST)
        if not reason:
            return Response({"success": False, "errors": ["A clear auditable tracking reason is required for balance adjustment history logs."]}, status=status.HTTP_400_BAD_REQUEST)

        try:
            delta_decimal = Decimal(str(delta_amount))
            
            WalletService.adjust_balance(
                wallet_id=wallet_id,
                delta_amount=delta_decimal,
                admin_user=request.user,
                reason=reason
            )
            
            return Response(
                {
                    "success": True,
                    "message": f"User wallet updated successfully by amount change delta of ${delta_decimal}."
                },
                status=status.HTTP_200_OK
            )
        except (DjangoValidationError, DRFValidationError) as exc:
            return Response(
                {
                    "success": False, 
                    "errors": format_validation_error(exc)
                }, 
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {
                    "success": False, 
                    "errors": [str(e)]
                }, 
                status=status.HTTP_400_BAD_REQUEST
            )


class CreateStripeConnectAccount(APIView):
    """
    Initializes Stripe express connected registration endpoints to tie accounts onto payout infrastructure.
    POST /wallet/connect/
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user

        # Run serializers validation
        serializer = StripeConnectSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        stripe_account_id = None
        try:
            existing_account = StripeConnectedAccount.objects.get(user=user)
            stripe_account_id = existing_account.stripe_account_id
        except StripeConnectedAccount.DoesNotExist:
            existing_account = None

        # Build Stripe mapping outside database lock threads to avoid connection pool exhaustion
        if not stripe_account_id:
            try:
                stripe_account = StripeConnectProvider.create_connected_account(user.email)
                stripe_account_id = stripe_account.id
                
                with transaction.atomic():
                    existing_account, created = StripeConnectedAccount.objects.get_or_create(
                        user=user,
                        defaults={"stripe_account_id": stripe_account_id}
                    )
                    if not created:
                        stripe_account_id = existing_account.stripe_account_id
                        
            except stripe.error.StripeError as e:
                return Response(
                    {"success": False, "error": e.user_message or "External payment partner connection failure."},
                    status=status.HTTP_424_FAILED_DEPENDENCY
                )
            except Exception as e:
                logger.error(f"Unexpected error linking database properties to Stripe configuration: {str(e)}")
                return Response(
                    {"success": False, "error": "Internal ledger sync failure."},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        # Retrieve connection links
        try:
            onboarding_url = StripeConnectProvider.create_account_link(stripe_account_id)
        except stripe.error.StripeError as e:
            return Response(
                {"success": False, "error": e.user_message or "Failed to secure onboarding linked sessions from provider."},
                status=status.HTTP_424_FAILED_DEPENDENCY
            )

        return Response(
            {
                "success": True, 
                "onboarding_url": onboarding_url
            }, 
            status=status.HTTP_201_CREATED if not existing_account else status.HTTP_200_OK
        )


class StripeConnectStatusView(APIView):
    """
    Checks realtime connected status attributes from the Stripe Connect network API and syncs details locally.
    GET /wallets/connect/status/
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        try:
            stripe_account = StripeConnectedAccount.objects.get(user=user)
        except StripeConnectedAccount.DoesNotExist:
            return Response({
                "connected": False,
                "charges_enabled": False,
                "payouts_enabled": False,
                "details_submitted": False
            }, status=status.HTTP_200_OK)

        try:
            # Query status
            live_account_data = StripeConnectProvider.retrieve_account_status(
                stripe_account.stripe_account_id
            )

            # Settle details atomically inside database transaction
            with transaction.atomic():
                stripe_account = StripeConnectedAccount.objects.select_for_update().get(id=stripe_account.id)
                stripe_account.payouts_enabled = live_account_data.payouts_enabled
                stripe_account.charges_enabled = live_account_data.charges_enabled
                stripe_account.details_submitted = live_account_data.details_submitted
                stripe_account.save()

        except stripe.error.StripeError as e:
            logger.error(f"Stripe sync failed safely for User {user.id}: {str(e)}")
            # Fail silently to retain prior cached values if stripe partner APIs timing out
            pass

        return Response({
            "connected": True,
            "charges_enabled": stripe_account.charges_enabled,
            "payouts_enabled": stripe_account.payouts_enabled,
            "details_submitted": stripe_account.details_submitted
        }, status=status.HTTP_200_OK)









class WalletRecentActivityView(generics.ListAPIView):
    serializer_class = WalletRecentActivitySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            WalletTransaction.objects.filter(
                wallet__user=self.request.user
            )
            .select_related("booking")
            .order_by("-created_at")[:10]
        )

    def list(self, request, *args, **kwargs):
        try:
            queryset = self.get_queryset()
            serializer = self.get_serializer(queryset, many=True)

            return Response(
                {
                    "success": True,
                    "message": "Recent wallet activities fetched successfully.",
                    "count": len(serializer.data),
                    "data": serializer.data,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            logger.exception("Failed to fetch wallet activities.")

            return Response(
                {
                    "success": False,
                    "message": "Failed to fetch wallet activities.",
                    "errors": [str(e)],
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )