from django.contrib import admin

from .models import KYC


@admin.register(KYC)
class KYCAdmin(admin.ModelAdmin):
    ordering = ("-created_at",)

    list_display = (
        "user",
        "id_type",
        "id_number",
        "status",
        "verified_by",
        "verified_at",
        "created_at",
    )

    list_filter = (
        "status",
        "id_type",
        "created_at",
        "verified_at",
    )

    search_fields = (
        "user__email",
        "id_number",
    )

    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
    )

    autocomplete_fields = (
        "user",
        "verified_by",
    )

    fieldsets = (
        (
            "User",
            {
                "fields": (
                    "user",
                )
            },
        ),
        (
            "Identity Information",
            {
                "fields": (
                    "id_type",
                    "id_number",
                )
            },
        ),
        (
            "Documents",
            {
                "fields": (
                    "document_front",
                    "document_back",
                    "selfie",
                )
            },
        ),
        (
            "Verification",
            {
                "fields": (
                    "status",
                    "rejection_reason",
                    "verified_by",
                    "verified_at",
                )
            },
        ),
        (
            "Audit Information",
            {
                "fields": (
                    "id",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    actions = [
        "approve_kyc",
        "reject_kyc",
    ]

    @admin.action(description="Approve selected KYC")
    def approve_kyc(self, request, queryset):
        queryset.update(
            status="approved",
            verified_by=request.user,
        )

    @admin.action(description="Reject selected KYC")
    def reject_kyc(self, request, queryset):
        queryset.update(
            status="rejected",
            verified_by=request.user,
        )