from django.urls import path

from .views import (
    BookingPaymentHistoryListView,
    BookingPaymentInitiateView,
    BookingPaymentReleaseView,
    CreateCheckoutSessionView,
    # StripeWebhookView,
    PaymentHistoryView,
    PaymentDetailView,
    stripe_connect_refresh_view,
    stripe_connect_success_view,
    stripe_webhook,
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
    # path(
    #     "payments/stripe/webhook/",
    #     StripeWebhookView.as_view(),
    #     name="stripe-webhook",
    # ),
    path(
        "payments/stripe/webhook/",
        stripe_webhook,
        name="stripe-webhook",
    ),

    # =========================================
    # PAYMENT HISTORY subscription
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

    path("booking/initiate/", BookingPaymentInitiateView.as_view(), name="payment-initiate"),
    # path("stripe/webhook/", StripeWebhookView.as_view(), name="stripe-webhook"),
    path("admin/booking/<uuid:booking_id>/release/", BookingPaymentReleaseView.as_view(), name="admin-payment-release"),
    path("payments/bookings/history/", BookingPaymentHistoryListView.as_view(), name="booking-payment-history"),
    path("connect/success/", stripe_connect_success_view, name="stripe-connect-success"),
    path("connect/refresh/", stripe_connect_refresh_view, name="stripe-connect-refresh"),
  
]