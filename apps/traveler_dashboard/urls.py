from django.urls import path
from .views import TravelerDashboardStatsView

urlpatterns = [
    path("traveler/stats/", TravelerDashboardStatsView.as_view(), name="traveler-dashboard-stats"),
]