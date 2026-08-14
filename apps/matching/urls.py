from django.urls import path

from .views import (
    MyMatchListView,
    PackageMatchListView,
    TripMatchListView,
    MatchDetailView,
    MyTripMatchingPackagesView
)

urlpatterns = [

    # ==========================================================
    # MY MATCHES (sender + traveler)
    # ==========================================================
    path(
        "my-matches/",
        MyMatchListView.as_view(),
        name="my-matches",
    ),

    # ==========================================================
    # PACKAGE MATCHES
    # ==========================================================
    path(
        "matches/package/",
        PackageMatchListView.as_view(),
        name="package-matches",
    ),

    # ==========================================================
    # TRIP MATCHES
    # ==========================================================
    path(
        "matches/trip/",
        TripMatchListView.as_view(),
        name="trip-matches",
    ),

    # ==========================================================
    # MATCH DETAIL
    # ==========================================================
    path(
        "matches/<uuid:id>/",
        MatchDetailView.as_view(),
        name="match-detail",
    ),
    path(
        "my/package/matching-trip/<uuid:trip_id>/",
        MyTripMatchingPackagesView.as_view(),
        name="my-trip-matching-packages",
    ),
]