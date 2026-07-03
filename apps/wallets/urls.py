from django.urls import path
from .views import (
    WalletViewSet, 
    WalletTransactionListView, 
    WithdrawalRequestView
)

urlpatterns = [
    # GET /wallet/ — Get wallet balance directly (using the list action mapping)
    path("wallets/", WalletViewSet.as_view({"get": "list"}), name="wallet-detail"),
    
    # GET /wallet/transactions/ — Transaction history feed
    path("wallets/transactions/", WalletTransactionListView.as_view(), name="wallet-transactions"),
    
    # POST /wallet/withdraw/ — Request a new withdrawal payout pipeline
    path("wallets/withdraw/", WithdrawalRequestView.as_view(), name="wallet-withdraw-request"),
    
    # GET /wallet/withdrawals/ — Historically tracked list view of withdrawal states
    path("wallets/withdrawals/", WithdrawalRequestView.as_view(), name="wallet-withdrawals-list"),
]