from django.urls import path
from .views import (
    KYCCreateView, 
    MyKYCView,
    AdminKYCListView,
    AdminKYCDetailView,
    AdminKYCApproveView,
    AdminKYCRejectView,
    AdminKYCRequestResubmissionView
)

urlpatterns = [
    # Traveler (Unchanged)
    path("kyc/", KYCCreateView.as_view(), name="kyc-create"),
    path("kyc/me/", MyKYCView.as_view(), name="my-kyc"),
    
    # Admin
    path(
        "admin/kyc/", 
        AdminKYCListView.as_view(), 
        name="admin-kyc-list"
    ),
    path(
        "admin/kyc/<uuid:id>/", 
        AdminKYCDetailView.as_view(), 
        name="admin-kyc-detail"
    ),
    path(
        "admin/kyc/<uuid:id>/approve/", 
        AdminKYCApproveView.as_view(), 
        name="admin-kyc-approve"
    ),
    path(
        "admin/kyc/<uuid:id>/reject/", 
        AdminKYCRejectView.as_view(), 
        name="admin-kyc-reject"
    ),
    path(
        "admin/kyc/<uuid:id>/request-resubmission/", 
        AdminKYCRequestResubmissionView.as_view(), 
        name="admin-kyc-request-resubmission"
    ),
]