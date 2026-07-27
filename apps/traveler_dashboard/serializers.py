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




class MonthlyEarningItemSerializer(serializers.Serializer):
    month = serializers.CharField(help_text="Month abbreviation, e.g. 'Jan'")
    month_number = serializers.IntegerField(help_text="Month number from 1 to 12")
    year = serializers.IntegerField()
    earnings = serializers.DecimalField(max_digits=12, decimal_places=2)


class MonthlyEarningsChartSerializer(serializers.Serializer):
    year = serializers.IntegerField()
    total_year_earnings = serializers.DecimalField(max_digits=12, decimal_places=2)
    chart_data = MonthlyEarningItemSerializer(many=True)






class CompactActivitySerializer(serializers.Serializer):
    type = serializers.CharField()
    title = serializers.CharField()
    message = serializers.CharField()
    created_at = serializers.DateTimeField()
    time_ago = serializers.CharField(
        help_text="Human readable real-time string e.g. '5 hours ago', 'Just now'"
    )