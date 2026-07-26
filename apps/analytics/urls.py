from django.urls import path

from .views import TopRoutesAPIView,AdminRecentActivityView

urlpatterns = [
    path(
        "admin/dashboard/top-routes/",
        TopRoutesAPIView.as_view(),
        name="admin-top-routes",
    ),
    path(
        "admin/dashboard/recent-activities/",
        AdminRecentActivityView.as_view(),
        name="admin-dashboard-recent-activities",    
),
]