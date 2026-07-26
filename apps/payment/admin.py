from django.contrib import admin

# Register your models here.
from django.contrib import admin

from .models import PlatformSetting


@admin.register(PlatformSetting)
class PlatformSettingAdmin(admin.ModelAdmin):

    list_display = (
        "platform_fee_percentage",
        "is_active",
        "updated_at",
    )