from django.urls import path

from .views import (
    CreateCheckoutSessionView,
    StripeWebhookView,
    PaymentHistoryView,
    PaymentDetailView,
)

urlpatterns = [

    # =========================================
    # CREATE STRIPE CHECKOUT SESSION
    # =========================================
    path(
        "create-checkout-session/",
        CreateCheckoutSessionView.as_view(),
        name="create-checkout-session",
    ),

    # =========================================
    # STRIPE WEBHOOK
    # =========================================
    path(
        "payments/stripe/webhook/",
        StripeWebhookView.as_view(),
        name="stripe-webhook",
    ),

    # =========================================
    # PAYMENT HISTORY
    # =========================================
    path(
        "payment/history/",
        PaymentHistoryView.as_view(),
        name="payment-history",
    ),

    # =========================================
    # PAYMENT DETAIL
    # =========================================
    path(
        "<uuid:id>/",
        PaymentDetailView.as_view(),
        name="payment-detail",
    ),
]