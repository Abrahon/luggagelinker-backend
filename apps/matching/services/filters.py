"""
==========================================================
MATCH FILTERS
==========================================================

This module filters Packages and Trips before scoring.

Purpose
-------
Remove impossible matches to improve performance.
"""

from apps.packages.models import Package
from apps.trips.models import Trip


# ==========================================================
# FILTER TRIPS FOR A PACKAGE
# ==========================================================

def filter_trips(package):
    """
    Return eligible trips for a package.
    """

    return (
        Trip.objects.filter(
            is_active=True,
            is_public=True,
            status="PLANNED",
            from_country__iexact=package.pickup_country,
            to_country__iexact=package.destination_country,
            available_weight_kg__gte=package.weight,
            departure_date__gte=package.pickup_date,
            arrival_date__lte=package.latest_delivery_date,
        )
        .exclude(
            traveler=package.sender,
        )
    )


# ==========================================================
# FILTER PACKAGES FOR A TRIP
# ==========================================================

def filter_packages(trip):
    """
    Return eligible packages for a trip.
    """

    return (
        Package.objects.filter(
            is_active=True,
            is_public=True,
            status="PENDING",
            pickup_country__iexact=trip.from_country,
            destination_country__iexact=trip.to_country,
            weight__lte=trip.available_weight_kg,
            pickup_date__lte=trip.departure_date,
            latest_delivery_date__gte=trip.arrival_date,
        )
        .exclude(
            sender=trip.traveler,
        )
    )