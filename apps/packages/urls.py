from django.urls import path

from .views import (
    CreatePackageView,
    MyPackageListView,
    PackageDetailView,
    PackageManageView,
    UploadPackageImageView,
    # ImageManageView,
    PackageImageListView,
    DeleteUpdatePackageImageView
)

urlpatterns = [

    # Create Package
    path(
        "create/package/",
        CreatePackageView.as_view(),
        name="package-create",
    ),

    # Logged-in user's packages
    path(
        "my/package/",
        MyPackageListView.as_view(),
        name="my-packages",
    ),

    # Public package details
    path(
        "package/<uuid:pk>/",
        PackageDetailView.as_view(),
        name="package-detail",
    ),

    # Update & Soft Delete (Owner only)
    path(
        "package/<uuid:pk>/manage/",
        PackageManageView.as_view(),
        name="package-manage",
    ),
    path(
         "package/<uuid:package_id>/images/",
         UploadPackageImageView.as_view(),
         name="upload-package-image",
    ),
    path(
        "package/<uuid:package_id>/images/list/",
        PackageImageListView.as_view(),
        name="package-image-list",
    ),
    path(
        "package/images/<uuid:id>/",
        DeleteUpdatePackageImageView.as_view(),
        name="delete-package-image",
    ),
    # path(
    #     "images/<uuid:id>/",
    #     ImageManageView.as_view(),
    #     name="package-image-manage",)

]