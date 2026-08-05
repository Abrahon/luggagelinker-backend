
from django.urls import path

from .views import (
    ReviewListCreateAPIView,
    ReviewRetrieveUpdateDestroyAPIView,
    ReportListCreateAPIView,
    ReportDetailAPIView,
    AdminReportListAPIView,
    AdminReportDetailAPIView,
    AdminResolveReportAPIView,
)

urlpatterns = [
    path('reviews/', ReviewListCreateAPIView.as_view(), name='review-list-create'),
    path('reviews/<uuid:pk>/', ReviewRetrieveUpdateDestroyAPIView.as_view(), name='review-detail'),

    path(
        "reports/",
        ReportListCreateAPIView.as_view(),
        name="report-list",
    ),

    path(
        "reports/<uuid:id>/",
        ReportDetailAPIView.as_view(),
        name="report-detail",
    ),

    path(
        "admin/reports/",
        AdminReportListAPIView.as_view(),
        name="admin-report-list",
    ),

    path(
        "admin/reports/<uuid:id>/",
        AdminReportDetailAPIView.as_view(),
        name="admin-report-detail",
    ),

    path(
        "admin/reports/<uuid:id>/resolve/",
        AdminResolveReportAPIView.as_view(),
        name="admin-report-resolve",
    ),
]