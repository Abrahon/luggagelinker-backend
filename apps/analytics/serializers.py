from rest_framework import serializers


class AdminRecentActivitySerializer(serializers.Serializer):
    type = serializers.CharField()
    title = serializers.CharField()
    description = serializers.CharField()
    time = serializers.CharField()
    created_at = serializers.DateTimeField()