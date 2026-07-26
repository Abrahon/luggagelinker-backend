from django.urls import path
from .views import SignupView,AdminUserRoleDistributionView,VerifyOTPView,AdminUserGrowthView,AdminUserListView,AdminUserStatusToggleView,LoginView,ResendOTPView,ForgotPasswordOTPView,VerifyForgotOTPView,ResetPasswordView

urlpatterns = [
    path("signup/", SignupView.as_view(), name="signup"),
    path("login/", LoginView.as_view()),
    path("verify-email/", VerifyOTPView.as_view()),

    path("resend-otp/", ResendOTPView.as_view()),

    path("forgot-password/", ForgotPasswordOTPView.as_view()),
    path("verify-forgot-otp/", VerifyForgotOTPView.as_view()),
    path("reset-password/", ResetPasswordView.as_view()),

    # path('check/token/', CheckTokenView.as_view(), name='check-token'),
    # path('refresh/token/', CustomTokenRefreshView.as_view(), name='refresh-token'),

    path("admin/users/", AdminUserListView.as_view(), name="admin-user-list"),

    path(
        "admin/users/<uuid:user_id>/<str:action>/",
        AdminUserStatusToggleView.as_view(),
        name="admin-user-toggle-status",
    ),
    path("admin/users/growth/", AdminUserGrowthView.as_view(), name="admin-user-growth"),
    path(
        "admin/users/role-distribution/",
        AdminUserRoleDistributionView.as_view(),
        name="admin-user-role-distribution",
    ),

]


