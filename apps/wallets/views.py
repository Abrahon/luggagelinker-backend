import logging
import traceback
from decimal import Decimal

import stripe
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, request, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.filters import OrderingFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Sum, Count
from django.db.models.functions import TruncMonth
from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework import status
from rest_framework import generics, permissions, status
from rest_framework.response import Response

from apps.accounts.permissions import IsUserAllowed
from .serializers import MonthlyWithdrawalSerializer, SenderWalletTransactionSerializer
from apps.bookings.models import Booking, BookingStatus, PaymentStatus
from apps.wallets.services import WalletService
from .serializers import RecentCompletedBookingSerializer
from .serializers import TravelerEarningDashboardSerializer
from .serializers import PendingReleaseSerializer
from apps.bookings.models import Booking, BookingStatus
from .serializers import MonthlyEarningsSerializer

from rest_framework import generics, permissions, status
from rest_framework.response import Response

from apps.wallets.models import Wallet, WalletTransaction

from .serializers import WalletLedgerSerializer

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
    AdminWithdrawalListSerializer,
    WithdrawalHistorySerializer,
    AdminWithdrawalStatsSerializer
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
    pagination_class = None 

    def get_queryset(self):
        return (
            WithdrawalMethod.objects.filter(
                user=self.request.user,
                is_active=True,
            )
            .order_by(
                "account_number",
                "-created_at",
            )
            .distinct("account_number")
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

    permission_classes = [IsAuthenticated, IsUserAllowed]
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

        serializer = WithdrawalHistorySerializer(
            queryset,
            many=True,
            context={"request": request},
        )

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
    permission_classes = [IsPlatformAdmin]
    serializer_class = AdminWithdrawalListSerializer

    queryset = (
        WithdrawalRequest.objects.select_related(
            "wallet__user",
            "wallet__user__profile",
            "withdrawal_method",
            "processed_by",
        )
        .order_by("-created_at")
    )

    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ["status"]


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


# Import your serializers, models, and provider helper
from .models import StripeConnectedAccount
from .serializers import StripeConnectSerializer


logger = logging.getLogger(__name__)


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
                # Use logger.exception to output full traceback in server logs
                logger.exception("Unexpected error linking database properties to Stripe configuration")
                return Response(
                    {"success": False, "error": str(e)},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        # Retrieve connection links with required `user` argument
        try:
            onboarding_url = StripeConnectProvider.create_account_link(
                stripe_account_id=stripe_account_id,
                user=user,
            )
        except stripe.error.StripeError as e:
            return Response(
                {
                    "success": False,
                    "error": e.user_message or "Failed to generate Stripe onboarding link.",
                },
                status=status.HTTP_424_FAILED_DEPENDENCY,
            )
        except Exception as e:
            logger.exception("Unexpected error during Stripe account link generation")
            return Response(
                {
                    "success": False,
                    "error": str(e),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
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

# apps/wallets/views.py
from decimal import Decimal
from decimal import Decimal
from django.db.models import Count, Sum, Q
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

# Adjust imports to match your project structure
from .models import WithdrawalRequest
from .serializers import AdminWithdrawalStatsSerializer

from django.db.models import Sum

class AdminWithdrawalStatsView(APIView):
    permission_classes = [IsPlatformAdmin]

    def get(self, request):
        stats = WithdrawalRequest.objects.aggregate(
            total_travelers_requested=Count("wallet", distinct=True),
            pending_requests=Count("id", filter=Q(status="PENDING")),
            completed_requests=Count("id", filter=Q(status="COMPLETED")),
            total_pending_balance=Sum("amount", filter=Q(status="PENDING")),
        )

        # Handle null sum fallback when no pending requests exist
        data = {
            "total_travelers_requested": stats["total_travelers_requested"] or 0,
            "total_pending_balance": stats["total_pending_balance"] or Decimal("0.00"),
            "pending_requests": stats["pending_requests"] or 0,
            "completed_requests": stats["completed_requests"] or 0,
        }

        serializer = AdminWithdrawalStatsSerializer(data)

        return Response(
            {
                "success": True,
                "message": "Withdrawal statistics retrieved successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )

class MonthlyEarningsView(generics.GenericAPIView):
    """
    Returns monthly earnings + completed delivery count
    for the authenticated traveler.
    """

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MonthlyEarningsSerializer

    def get(self, request):

        queryset = (
            Booking.objects.filter(
                traveler=request.user,
                status=BookingStatus.COMPLETED,
            )
            .annotate(
                month=TruncMonth("completed_at")
            )
            .values("month")
            .annotate(
                earnings=Sum("agreed_reward"),
                deliveries=Count("id"),
            )
            .order_by("month")
        )

        data = [
            {
                "month": item["month"].strftime("%b %Y"),
                "earnings": item["earnings"],
                "deliveries": item["deliveries"],
            }
            for item in queryset
        ]

        serializer = self.get_serializer(data, many=True)

        return Response(
            {
                "success": True,
                "message": "Monthly earnings retrieved successfully.",
                "count": len(serializer.data),
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )




class PendingReleaseListView(generics.GenericAPIView):

    serializer_class = PendingReleaseSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):

        bookings = (
            Booking.objects.select_related(
                "package",
                "trip",
            )
            .filter(
                traveler=request.user,
                payment_status=PaymentStatus.PAID,
                status__in=[
                    BookingStatus.CONFIRMED,
                    BookingStatus.PICKED_UP,
                    BookingStatus.IN_TRANSIT,
                ],
            )
            .order_by("-created_at")
        )

        data = []

        for booking in bookings:

            escrow_status = WalletService.get_escrow_status(booking)

            if escrow_status != "HELD":
                continue

            data.append(
                {
                    "id": booking.id,
                    "tracking_number": booking.tracking_number,
                    "package": booking.package.title,
                    "reward": booking.agreed_reward,
                    "currency": booking.currency,
                    "expected_release": booking.trip.arrival_date,
                    "escrow_status": escrow_status,
                    "status": booking.status,
                }
            )

        serializer = self.get_serializer(data, many=True)

        return Response(
            {
                "success": True,
                "message": "Pending releases retrieved successfully.",
                "count": len(serializer.data),
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )



class WalletLedgerView(generics.GenericAPIView):
    """
    Returns wallet transaction history for the authenticated user.
    """

    serializer_class = WalletLedgerSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):

        wallet = Wallet.objects.filter(
            user=request.user
        ).first()

        if not wallet:
            return Response(
                {
                    "success": True,
                    "message": "No wallet found.",
                    "count": 0,
                    "data": [],
                },
                status=status.HTTP_200_OK,
            )

        queryset = (
            WalletTransaction.objects.filter(
                wallet=wallet,
                status=WalletTransaction.TransactionStatus.COMPLETED,
            )
            .select_related("booking")
            .order_by("-created_at")
        )

        serializer = self.get_serializer(queryset, many=True)

        return Response(
            {
                "success": True,
                "message": "Wallet ledger retrieved successfully.",
                "count": queryset.count(),
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )




class MonthlyWithdrawalView(generics.GenericAPIView):
    """
    Monthly withdrawal summary for dashboard charts.
    """

    serializer_class = MonthlyWithdrawalSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get(self, request):

        wallet = Wallet.objects.filter(user=request.user).first()

        if not wallet:
            return Response(
                {
                    "success": True,
                    "message": "No wallet found.",
                    "data": [],
                },
                status=status.HTTP_200_OK,
            )

        queryset = (
            WalletTransaction.objects.filter(
                wallet=wallet,
                type=WalletTransaction.TransactionType.WITHDRAWAL,
                status=WalletTransaction.TransactionStatus.COMPLETED,
            )
            .annotate(month=TruncMonth("created_at"))
            .values("month")
            .annotate(
                withdrawn=Sum("amount"),
                withdrawals=Count("id"),
            )
            .order_by("month")
        )

        data = [
            {
                "month": row["month"].strftime("%b %Y"),
                "withdrawn": abs(row["withdrawn"]),
                "withdrawals": row["withdrawals"],
            }
            for row in queryset
        ]

        serializer = self.get_serializer(data, many=True)

        return Response(
            {
                "success": True,
                "message": "Monthly withdrawals retrieved successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )





class TravelerEarningDashboardView(generics.GenericAPIView):
    """
    Dashboard cards for Traveler Earnings page.
    """

    serializer_class = TravelerEarningDashboardSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get(self, request):

        user = request.user

        wallet, _ = Wallet.objects.get_or_create(user=user)

        # -----------------------------
        # Total Earned
        # -----------------------------
        total_earned = wallet.total_earned or Decimal("0.00")

        # -----------------------------
        # Available Balance
        # -----------------------------
        available_balance = wallet.available_balance or Decimal("0.00")

        # -----------------------------
        # Pending Releases
        # Money still locked in escrow
        # -----------------------------
        pending_releases = (
            Booking.objects.filter(
                traveler=user,
                status__in=[
                    BookingStatus.CONFIRMED,
                    BookingStatus.PICKED_UP,
                    BookingStatus.IN_TRANSIT,
                ],
                payment_status="PAID",
            ).aggregate(
                total=Sum("agreed_reward")
            )["total"]
            or Decimal("0.00")
        )

        # -----------------------------
        # Completed Deliveries
        # -----------------------------
        completed_deliveries = Booking.objects.filter(
            traveler=user,
            status=BookingStatus.COMPLETED,
        ).count()

        data = {
            "total_earned": total_earned,
            "available_balance": available_balance,
            "pending_releases": pending_releases,
            "completed_deliveries": completed_deliveries,
        }

        serializer = self.get_serializer(data)

        return Response(
            {
                "success": True,
                "message": "Traveler earnings dashboard retrieved successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )






class RecentCompletedBookingView(generics.GenericAPIView):
    """
    Returns recent completed deliveries for the logged-in traveler.
    """

    serializer_class = RecentCompletedBookingSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get(self, request):

        queryset = (
            Booking.objects.filter(
                traveler=request.user,
                status=BookingStatus.COMPLETED,
            )
            .only(
                "id",
                "tracking_number",
                "agreed_reward",
                "currency",
                "delivered_at",
            )
            .order_by("-delivered_at")[:5]
        )

        serializer = self.get_serializer(queryset, many=True)

        return Response(
            {
                "success": True,
                "message": "Recent completed deliveries retrieved successfully.",
                "count": queryset.count(),
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )






from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from apps.wallets.models import Wallet
from apps.wallets.serializers import TravelerWalletCardSerializer


class TravelerWalletCardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        wallet, _ = Wallet.objects.select_related(
            "user",
            "user__profile",
        ).get_or_create(
            user=request.user,
            defaults={
                "currency": "USD",
            },
        )

        serializer = TravelerWalletCardSerializer(wallet)

        return Response(
            {
                "success": True,
                "message": "Traveler wallet card retrieved successfully.",
                "data": serializer.data,
            },
            status=status.HTTP_200_OK,
        )


# sender
# apps/wallets/views.py

from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from .models import Wallet
from .serializers import SenderWalletDashboardSerializer,WalletTopupSerializer


class SenderWalletDashboardAPIView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SenderWalletDashboardSerializer

    def get_object(self):
        wallet, _ = Wallet.objects.get_or_create(user=self.request.user)
        return wallet



# apps/wallets/views.py

from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from .models import WalletTransaction
from .serializers import SenderWalletTransactionSerializer,SenderWalletTransactionDetailSerializer


class SenderWalletTransactionAPIView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SenderWalletTransactionSerializer

    def get_queryset(self):
        wallet = self.request.user.wallet

        queryset = WalletTransaction.objects.filter(
            wallet=wallet
        ).select_related(
            "booking"
        ).order_by("-created_at")

        transaction_type = self.request.query_params.get("type")
        status = self.request.query_params.get("status")

        if transaction_type:
            queryset = queryset.filter(type=transaction_type)

        if status:
            queryset = queryset.filter(status=status)

        return queryset



class SenderWalletTransactionDetailAPIView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SenderWalletTransactionDetailSerializer
    lookup_field = "id"

    def get_queryset(self):
        return (
            WalletTransaction.objects
            .filter(wallet__user=self.request.user)
            .select_related("booking", "wallet")
        )
# apps/wallets/views.py




import logging
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.core.exceptions import ValidationError as DjangoValidationError

from .serializers import WalletTopupSerializer
from .services import WalletPaymentService

logger = logging.getLogger(__name__)


class SenderWalletTopupAPIView(APIView):
    """
    API endpoint to initiate a Stripe Checkout Session for topping up user wallet.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = WalletTopupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            checkout = WalletPaymentService.create_topup_checkout(
                user=request.user,
                amount=serializer.validated_data["amount"],
            )

            return Response(
                {
                    "success": True,
                    "message": "Wallet top-up session created successfully.",
                    "data": {
                        "checkout_url": checkout.url,
                        "session_id": checkout.id,
                    },
                },
                status=status.HTTP_201_CREATED,
            )

        except DjangoValidationError as e:
            logger.warning(
                "Wallet top-up validation failed for user %s: %s",
                request.user.id,
                str(e),
            )
            return Response(
                {
                    "success": False,
                    "message": str(e),
                    "code": "TOPUP_VALIDATION_FAILED",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception:
            logger.exception(
                "Wallet top-up session creation failed for user %s",
                request.user.id,
            )
            return Response(
                {
                    "success": False,
                    "message": "Unable to create wallet top-up session. Please try again later.",
                    "code": "TOPUP_SESSION_FAILED",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )