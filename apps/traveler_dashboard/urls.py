from django.urls import path
from .views import TravelerDashboardStatsView,TravelerMonthlyEarningsChartView,TravelerRecentActivitiesView

urlpatterns = [
    path("traveler/stats/", TravelerDashboardStatsView.as_view(), name="traveler-dashboard-stats"),
    path("traveler/monthly-earnings/", TravelerMonthlyEarningsChartView.as_view(), name="traveler-monthly-earnings"),
    path("traveler/recent-activities/",TravelerRecentActivitiesView.as_view(),name="traveler-recent-activities", ),
]