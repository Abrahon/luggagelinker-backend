from django.urls import path
from .views import (
    BookingCreateView,
    MyBookingListView,
    BookingDetailView,
    BookingRespondView,
    # PaymentWebhookView,
)

app_name = "bookings"

urlpatterns = [
    # -------------------------------------------------------------------------
    # Core Query & Dashboard Endpoints
    # -------------------------------------------------------------------------
    path(
        "my-bookings/", 
        MyBookingListView.as_view(), 
        name="booking-list"
    ),
    path(
        "bookings/<uuid:id>/", 
        BookingDetailView.as_view(), 
        name="booking-detail"
    ),

    # -------------------------------------------------------------------------
    # Transactional & Action Workflow Endpoints
    # -------------------------------------------------------------------------
    path(
        "bookings/create/", 
        BookingCreateView.as_view(), 
        name="booking-create"
    ),
    path(
        "bookings/<uuid:id>/respond/", 
        BookingRespondView.as_view(), 
        name="booking-respond"
    ),

    # -------------------------------------------------------------------------
    # Asynchronous Payment Gateways Callback Endpoints (Public)
    # -------------------------------------------------------------------------
    # path(
    #     "webhook/payment/", 
    #     PaymentWebhookView.as_view(), 
    #     name="payment-webhook"
    # ),
]