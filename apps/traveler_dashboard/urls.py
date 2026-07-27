from django.urls import path
from .views import TravelerDashboardStatsView,TravelerMonthlyEarningsChartView

urlpatterns = [
    path("traveler/stats/", TravelerDashboardStatsView.as_view(), name="traveler-dashboard-stats"),
    path("traveler/monthly-earnings/", TravelerMonthlyEarningsChartView.as_view(), name="traveler-monthly-earnings"),
]