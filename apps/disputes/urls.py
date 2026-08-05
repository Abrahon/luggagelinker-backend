from django.urls import path
from .views import (
    DisputeListCreateAPIView,
    DisputeRetrieveAPIView,
    DisputeAddMessageAPIView,
    DisputeAddEvidenceAPIView,
    AdminDisputeListAPIView,
    AdminDisputeRetrieveAPIView,
    AdminDisputeAssignAPIView,
    AdminDisputeRequestEvidenceAPIView,
    AdminDisputeResolveAPIView,
    DisputeWithdrawAPIView,
    AdminDisputeStatusAPIView,
    AdminDisputeNoteAPIView
)

urlpatterns = [
    # ─── Standard User Routes ───
    path("disputes/", DisputeListCreateAPIView.as_view(), name="dispute-list-create"),
    path("disputes/<uuid:id>/", DisputeRetrieveAPIView.as_view(), name="dispute-detail"),
    path("disputes/<uuid:id>/message/", DisputeAddMessageAPIView.as_view(), name="dispute-add-message"),
    path("disputes/<uuid:id>/evidence/", DisputeAddEvidenceAPIView.as_view(), name="dispute-add-evidence"),
    
    # ─── Admin Moderation Routes ───
    path("admin/disputes/", AdminDisputeListAPIView.as_view(), name="admin-dispute-list"),
    path("admin/disputes/<uuid:id>/", AdminDisputeRetrieveAPIView.as_view(), name="admin-dispute-detail"),
    path("admin/disputes/<uuid:id>/assign/", AdminDisputeAssignAPIView.as_view(), name="admin-dispute-assign"),
    path("admin/disputes/<uuid:id>/request-evidence/", AdminDisputeRequestEvidenceAPIView.as_view(), name="admin-dispute-request-evidence"),
    path("admin/disputes/<uuid:id>/resolve/", AdminDisputeResolveAPIView.as_view(), name="admin-dispute-resolve"),

    path(
        "disputes/<uuid:id>/withdraw/",
        DisputeWithdrawAPIView.as_view(),
        name="dispute-withdraw",
    ),

    # Admin
    path(
        "admin/disputes/<uuid:id>/status/",
        AdminDisputeStatusAPIView.as_view(),
        name="admin-dispute-status",
    ),

    path(
        "admin/disputes/<uuid:id>/notes/",
        AdminDisputeNoteAPIView.as_view(),
        name="admin-dispute-note",
    ),

]