from django.urls import path

from .views import TopRoutesAPIView

urlpatterns = [
    path(
        "admin/dashboard/top-routes/",
        TopRoutesAPIView.as_view(),
        name="admin-top-routes",
    ),
]