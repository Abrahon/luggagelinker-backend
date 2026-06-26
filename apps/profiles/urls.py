from django.urls import path

from .views import (
    CreateProfileView,
    ProfileView,
)

urlpatterns = [

    path(
        "profile/create/",
        CreateProfileView.as_view(),
        name="create-profile",
    ),

    path(
        "profile/",
        ProfileView.as_view(),
        name="profile",
    ),

]