from django.contrib import admin

# Register your models here.
from django.contrib import admin
from .models import Booking

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    # 1. Columns visible in the main list view table
    list_display = (
        "tracking_number",
        "sender",
        "traveler",
        "status",
        "payment_status",
        "agreed_reward",
        "currency",
        "agreed_weight_kg",
        "created_at",
    )

    # 2. Sidebar filter options for quick analytical breakdown
    list_filter = (
        "status",
        "payment_status",
        "currency",
        "is_active",
        "created_at",
    )

    # 3. Enable intelligent text-based search indexing across keys and foreign lookups
    search_fields = (
        "id",
        "tracking_number",
        "sender__email",
        "sender__username",
        "traveler__email",
        "traveler__username",
        "pickup_verification_pin",
        "delivery_verification_pin",
    )

    # 4. Enforce strict database read-only visibility for security/integrity values
    readonly_fields = (
        "id",
        "tracking_number",
        "pickup_verification_pin",
        "delivery_verification_pin",
        "created_at",
        "updated_at",
    )

    # 5. Clean visual fieldsets to avoid a single unorganized vertical wall of text
    fieldsets = (
        ("Core Identifiers", {
            "fields": ("id", "tracking_number", "match", "package", "trip")
        }),
        ("Contract Parties", {
            "fields": ("sender", "traveler")
        }),
        ("Financials & Scope", {
            "fields": ("status", "payment_status", "agreed_reward", "currency", "agreed_weight_kg")
        }),
        ("Security Handoff Tokens", {
            "classes": ("collapse",),  # Keeps them hidden until clicked for added privacy
            "fields": ("pickup_verification_pin", "delivery_verification_pin")
        }),
        ("Lifecycle State Machine Timestamps", {
            "fields": (
                "expires_at",
                "traveler_accepted_at",
                "payment_received_at",
                "confirmed_at",
                "picked_up_at",
                "in_transit_at",
                "delivered_at",
                "completed_at",
            )
        }),
        ("Cancellation Parameters", {
            "fields": ("cancelled_by", "cancellation_reason", "is_active")
        }),
    )

    # 6. Optimized raw ID fields for heavy foreign relation lookups to optimize database memory
    raw_id_fields = ("match", "package", "trip", "sender", "traveler", "cancelled_by")