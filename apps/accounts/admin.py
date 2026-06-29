from django.contrib import admin

# Register your models here.
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User, OTP


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("-date_joined",)

    list_display = (
        "email",
        "role",
        "is_verified",
        "is_active",
        "is_staff",
        "date_joined",
    )

    list_filter = (
        "role",
        "is_verified",
        "is_active",
        "is_staff",
        "date_joined",
    )

    search_fields = ("email",)

    readonly_fields = (
        "id",
        "date_joined",
        "updated_at",
        "last_login",
    )

    fieldsets = (
        ("User Information", {
            "fields": (
                "id",
                "email",
                "password",
                "role",
            )
        }),
        ("Permissions", {
            "fields": (
                "is_active",
                "is_staff",
                "is_verified",
                "is_superuser",
                "groups",
                "user_permissions",
            )
        }),
        ("Important Dates", {
            "fields": (
                "last_login",
                "date_joined",
                "updated_at",
            )
        }),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "role",
                    "password1",
                    "password2",
                    "is_active",
                    "is_staff",
                    "is_verified",
                ),
            },
        ),
    )


@admin.register(OTP)
class OTPAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "user",
        "email",
        "created_at",
        "expired",
    )

    search_fields = (
        "code",
        "email",
        "user__email",
    )

    list_filter = (
        "created_at",
    )

    readonly_fields = (
        "id",
        "created_at",
    )

    ordering = ("-created_at",)

    def expired(self, obj):
        return obj.is_expired()

    expired.boolean = True
    expired.short_description = "Expired"