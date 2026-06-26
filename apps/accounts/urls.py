from django.urls import path
from .views import SignupView,VerifyOTPView,LoginView

urlpatterns = [
    path("signup/", SignupView.as_view(), name="signup"),
    path("login/", LoginView.as_view()),
    path("verify-email/", VerifyOTPView.as_view()),


]