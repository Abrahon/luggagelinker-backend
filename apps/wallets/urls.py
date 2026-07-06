from django.urls import path
from rest_framework import views
from .views import (
    AdminAdjustBalanceView,
    AdminWithdrawalListView,
    CreateStripeConnectAccount,
    StripeConnectStatusView,
    UserCancelWithdrawalView,
    WalletViewSet, 
    WalletTransactionListView, 
    WithdrawalRequestView,
   AdminWithdrawalDetailView,
   AdminWithdrawalApproveView,
   AdminWithdrawalRejectView,
   AdminWithdrawalMarkPaidView,
)

urlpatterns = [
    # GET /wallet/ — Get wallet balance directly (using the list action mapping)
    path("wallets/", WalletViewSet.as_view({"get": "list"}), name="wallet-detail"),
    path("wallet/connect/",CreateStripeConnectAccount.as_view(), name="wallet-connect"),
    
    # GET /wallet/transactions/ — Transaction history feed
    path("wallets/transactions/", WalletTransactionListView.as_view(), name="wallet-transactions"),
    
    # POST /wallet/withdraw/ — Request a new withdrawal payout pipeline
    path("wallets/withdraw/", WithdrawalRequestView.as_view(), name="wallet-withdraw-request"),
    
    # GET /wallet/withdrawals/ — Historically tracked list view of withdrawal states
    path("wallets/withdrawals/", WithdrawalRequestView.as_view(), name="wallet-withdrawals-list"),
    # admin

    # Platform Admin Payout Paths
    path("admin/withdrawals/",AdminWithdrawalListView.as_view(), name="admin-withdrawal-list"),
    path("admin/withdrawals/<uuid:pk>/",AdminWithdrawalDetailView.as_view(), name="admin-withdrawal-detail"),
    path("admin/withdrawals/<uuid:pk>/approve/",AdminWithdrawalApproveView.as_view(), name="admin-withdrawal-approve"),
    path("admin/withdrawals/<uuid:pk>/reject/",AdminWithdrawalRejectView.as_view(), name="admin-withdrawal-reject"),
    path("admin/withdrawals/<uuid:pk>/mark-paid/",AdminWithdrawalMarkPaidView.as_view(), name="admin-withdrawal-mark-paid"),

    # ... your existing routes ...

    # User cancel entrypoint
    path("wallets/withdrawals/<uuid:pk>/cancel/", UserCancelWithdrawalView.as_view(), name="user-withdrawal-cancel"),
    
    # Admin adjustment entrypoint
    path("admin/wallets/<uuid:wallet_id>/adjust/", AdminAdjustBalanceView.as_view(), name="admin-wallet-adjust"),
    path(
        "wallets/connect/status/", 
        StripeConnectStatusView.as_view(), 
        name="stripe-connect-status"
    ),

]