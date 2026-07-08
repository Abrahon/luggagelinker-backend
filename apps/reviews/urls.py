from django.urls import path
from .views import ReviewListCreateAPIView,AdminReportListAPIView, ReviewRetrieveUpdateDestroyAPIView,ReportListCreateAPIView,ReportDetailAPIView,AdminReportDetailAPIView

urlpatterns = [
    path('reviews/', ReviewListCreateAPIView.as_view(), name='review-list-create'),
    path('reviews/<uuid:pk>/', ReviewRetrieveUpdateDestroyAPIView.as_view(), name='review-detail'),

    path("reports/", ReportListCreateAPIView.as_view()),
    path("reports/<uuid:pk>/", ReportDetailAPIView.as_view()),

    path("admin/reports/", AdminReportListAPIView.as_view()),
    path("admin/reports/<uuid:pk>/", AdminReportDetailAPIView.as_view()),
]