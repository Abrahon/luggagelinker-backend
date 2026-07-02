from django.urls import path
from .views import (
    BookingCreateView,
    BookingDeliveryVerificationView,
    BookingPickupVerificationView,
    MyBookingListView,
    BookingDetailView,
    BookingRespondView,
    BookingStartTransitView,
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

    path("booking/verify-pickup/", BookingPickupVerificationView.as_view(), name="verify-pickup"),
    path("booking/start-transit/", BookingStartTransitView.as_view(), name="start-transit"),
    path("booking/verify-delivery/", BookingDeliveryVerificationView.as_view(), name="verify-delivery"), 

]