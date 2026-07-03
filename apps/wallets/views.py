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

from .models import Wallet, WalletTransaction, WithdrawalRequest
from .serializers import (
    WalletSerializer, 
    WalletTransactionSerializer, 
    WithdrawalRequestSerializer
)
from .services import WalletService


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