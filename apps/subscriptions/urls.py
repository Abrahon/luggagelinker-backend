from django.urls import path

from .views import (
    PlanListView,
    PlanDetailView,
    PlanCreateView,
    PlanUpdateView,
    PlanDeleteView,
)

urlpatterns = [

    path(
        "plans/",
        PlanListView.as_view(),
        name="plan-list",
    ),

    path(
        "plans/<slug:slug>/",
        PlanDetailView.as_view(),
        name="plan-detail",
    ),

    path(
        "admin/plans/create/",
        PlanCreateView.as_view(),
        name="plan-create",
    ),

    path(
        "admin/plans/<uuid:pk>/update/",
        PlanUpdateView.as_view(),
        name="plan-update",
    ),

    path(
        "admin/plans/<uuid:pk>/delete/",
        PlanDeleteView.as_view(),
        name="plan-delete",
    ),
]