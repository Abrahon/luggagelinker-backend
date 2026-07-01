from django.urls import path

from .views import (
    CreateTripListView,
    MyTripListView,
    TripDetailView,
    TripManageView,
)

urlpatterns = [

    path(
        "trip/",
        CreateTripListView.as_view(),
        name="trip-list-create",
    ),

    path(
        "my-trip/",
        MyTripListView.as_view(),
        name="my-trips",
    ),

    path(
        "trip/<uuid:id>/",
        TripDetailView.as_view(),
        name="trip-detail",
    ),

    path(
        "trip/<uuid:id>/manage/",
        TripManageView.as_view(),
        name="trip-manage",
    ),
]