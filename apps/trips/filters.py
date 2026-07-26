import django_filters

from apps.trips.models import Trip


class AdminTripFilter(django_filters.FilterSet):

    status = django_filters.CharFilter(field_name="status")

    class Meta:
        model = Trip
        fields = [
            "status",
        ]