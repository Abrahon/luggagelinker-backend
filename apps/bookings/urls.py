from django.urls import path

from apps.adminpanel import views
from .views import (
    BookingCancellationView,
    BookingCreateView,
    BookingDeliveryVerificationView,
    BookingPickupVerificationView,
    MyBookingListView,
    BookingDetailView,
    BookingRespondView,
    BookingStartTransitView,
    TravelerPendingBookingsView,
    ActiveBookingListView,
    SenderCompletedDeliveryListView,
    TravelerCompletedDeliveryListView,
    CancelledBookingListView,
    SenderDashboardStatsView,
    SenderPaymentSummaryView,
    SenderActionRequiredView,
    SenderMyBookingListView,
    SenderBookingDetailView
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
    path(
        "bookings/traveler/pending/",
        TravelerPendingBookingsView.as_view(),
        name="traveler-pending-bookings",
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

    path(
        "bookings/active/",
        ActiveBookingListView.as_view(),
        name="traveler-active-bookings",
    ),
    path("bookings/<uuid:pk>/cancel/",BookingCancellationView.as_view(), name="booking-cancel"),
    path("booking/verify-pickup/", BookingPickupVerificationView.as_view(), name="verify-pickup"),
    path("booking/start-transit/", BookingStartTransitView.as_view(), name="start-transit"),
    path("booking/verify-delivery/", BookingDeliveryVerificationView.as_view(), name="verify-delivery"),
    # Sender Completed Deliveries
    path("sender/completed-deliveries/",SenderCompletedDeliveryListView.as_view(),name="sender-completed-deliveries",),

    # Traveler Completed Deliveries
    path("traveler/completed-deliveries/",TravelerCompletedDeliveryListView.as_view(),name="traveler-completed-deliveries"),

    path("bookings/cancelled/",CancelledBookingListView.as_view(),name="cancelled-bookings"),
    # apps/bookings/urls.py
    path(
        "sender/dashboard/stats/",
        SenderDashboardStatsView.as_view(),
        name="sender-dashboard-stats",
    ),

    path(
        "sender/payment-summary/",
        SenderPaymentSummaryView.as_view(),
        name="sender-payment-summary",
    ),
    path(
        "sender/action-required/",
        SenderActionRequiredView.as_view(),
        name="sender-action-required",
    ),
    path(
        "sender/my-bookings/",
        SenderMyBookingListView.as_view(),
        name="sender-my-bookings",
    ),
    path(
        "sender/bookings/<uuid:id>/",
        SenderBookingDetailView.as_view(),
        name="sender-booking-detail",
   ),



]