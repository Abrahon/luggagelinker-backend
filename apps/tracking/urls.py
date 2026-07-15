from django.urls import path

from .views import (
    ActiveTrackerRetrieveView,
    ActiveTrackerCreateView,
    LocationHistoryListView,
)

urlpatterns = [
    path(
        "start/tracking",
        ActiveTrackerCreateView.as_view(),
        name="tracking-start",
    ),

    path(
        "tracking/<uuid:room_id>/",
        ActiveTrackerRetrieveView.as_view(),
        name="tracking-detail",
    ),

    path(
        "tracking/<uuid:tracker_id>/history/",
        LocationHistoryListView.as_view(),
        name="tracking-history",
    ),
]