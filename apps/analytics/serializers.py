from rest_framework import serializers


class AdminRecentActivitySerializer(serializers.Serializer):
    type = serializers.CharField()
    title = serializers.CharField()
    description = serializers.CharField()
    time = serializers.CharField()
    created_at = serializers.DateTimeField()





class AdminDashboardStatsSerializer(serializers.Serializer):
    total_users = serializers.IntegerField()
    total_packages = serializers.IntegerField()
    total_bookings = serializers.IntegerField()

    platform_revenue = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    active_deliveries = serializers.IntegerField()
    completed_deliveries = serializers.IntegerField()

    pending_kyc = serializers.IntegerField()
    open_disputes = serializers.IntegerField()