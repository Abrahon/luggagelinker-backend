from django.urls import path

from .views import (
    WalletViewSet,
    WalletTransactionListView,

    WithdrawalRequestView,
    UserCancelWithdrawalView,

    WithdrawalMethodListCreateView,
    WithdrawalMethodRetrieveUpdateDestroyView,
    SetDefaultWithdrawalMethodView,

    CreateStripeConnectAccount,
    StripeConnectStatusView,

    AdminWithdrawalListView,
    AdminWithdrawalDetailView,
    AdminWithdrawalApproveView,
    AdminWithdrawalRejectView,
    AdminWithdrawalMarkPaidView,

    AdminAdjustBalanceView,
)

urlpatterns = [

    # =====================================================
    # Wallet
    # =====================================================

    path(
        "wallets/",
        WalletViewSet.as_view({"get": "list"}),
        name="wallet-detail",
    ),

    path(
        "wallets/transactions/",
        WalletTransactionListView.as_view(),
        name="wallet-transactions",
    ),

    # =====================================================
    # Withdrawal Methods
    # =====================================================

    path(
        "wallets/withdraw-methods/",
        WithdrawalMethodListCreateView.as_view(),
        name="withdraw-method-list-create",
    ),

    path(
        "wallets/withdraw-methods/<uuid:pk>/",
        WithdrawalMethodRetrieveUpdateDestroyView.as_view(),
        name="withdraw-method-detail",
    ),

    path(
        "wallets/withdraw-methods/<uuid:pk>/set-default/",
        SetDefaultWithdrawalMethodView.as_view(),
        name="withdraw-method-set-default",
    ),

    # =====================================================
    # Withdrawals
    # =====================================================

    path(
        "wallets/withdraw/",
        WithdrawalRequestView.as_view(),
        name="wallet-withdraw",
    ),

    path(
        "wallets/withdrawals/",
        WithdrawalRequestView.as_view(),
        name="wallet-withdrawals",
    ),

    path(
        "wallets/withdrawals/<uuid:pk>/cancel/",
        UserCancelWithdrawalView.as_view(),
        name="wallet-withdraw-cancel",
    ),

    # =====================================================
    # Stripe Connect
    # =====================================================

    path(
        "wallets/connect/",
        CreateStripeConnectAccount.as_view(),
        name="stripe-connect",
    ),

    path(
        "wallets/connect/status/",
        StripeConnectStatusView.as_view(),
        name="stripe-connect-status",
    ),

    # =====================================================
    # Admin Withdrawals
    # =====================================================

    path(
        "admin/withdrawals/",
        AdminWithdrawalListView.as_view(),
        name="admin-withdrawals",
    ),

    path(
        "admin/withdrawals/<uuid:pk>/",
        AdminWithdrawalDetailView.as_view(),
        name="admin-withdrawal-detail",
    ),

    path(
        "admin/withdrawals/<uuid:pk>/approve/",
        AdminWithdrawalApproveView.as_view(),
        name="admin-withdrawal-approve",
    ),

    path(
        "admin/withdrawals/<uuid:pk>/reject/",
        AdminWithdrawalRejectView.as_view(),
        name="admin-withdrawal-reject",
    ),

    path(
        "admin/withdrawals/<uuid:pk>/mark-paid/",
        AdminWithdrawalMarkPaidView.as_view(),
        name="admin-withdrawal-mark-paid",
    ),

    # =====================================================
    # Admin Wallet
    # =====================================================

    path(
        "admin/wallets/<uuid:wallet_id>/adjust/",
        AdminAdjustBalanceView.as_view(),
        name="admin-wallet-adjust",
    ),
]