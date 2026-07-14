from django.urls import path

from .views import (
    ActiveTrackerRetrieveView,
    ActiveTrackerCreateView,
    LocationHistoryListView,
)

urlpatterns = [
    path(
        "start/",
        ActiveTrackerCreateView.as_view(),
        name="tracking-start",
    ),

    path(
        "<uuid:room_id>/",
        ActiveTrackerRetrieveView.as_view(),
        name="tracking-detail",
    ),

    path(
        "<uuid:tracker_id>/history/",
        LocationHistoryListView.as_view(),
        name="tracking-history",
    ),
]