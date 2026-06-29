from django.urls import path
from .views import KYCCreateView, MyKYCView

urlpatterns = [
    path("kyc/", KYCCreateView.as_view(), name="kyc-create"),
    path("kyc/me/", MyKYCView.as_view(), name="my-kyc"),
]