from django.urls import path

from .views import (
    NotificationListView,
    NotificationReadAllView,
)

urlpatterns = [

    # ==========================================================
    # NOTIFICATIONS
    # ==========================================================

    path(
        "notifications/",
        NotificationListView.as_view(),
        name="notification-list",
    ),

    path(
        "notifications/read-all/",
        NotificationReadAllView.as_view(),
        name="notification-read-all",
    ),

]