from rest_framework import serializers


class TravelerDashboardStatsSerializer(serializers.Serializer):
    available_balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    active_deliveries = serializers.IntegerField()
    active_trips = serializers.IntegerField()
    pending_requests = serializers.IntegerField()
    rating = serializers.DecimalField(max_digits=3, decimal_places=2)
    completed_deliveries = serializers.IntegerField()
    pending_earnings = serializers.DecimalField(max_digits=12, decimal_places=2)
    lifetime_earnings = serializers.DecimalField(max_digits=12, decimal_places=2)