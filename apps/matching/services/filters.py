from django.utils import timezone

from apps.packages.models import Package, PackageStatus
from apps.trips.models import Trip, TripStatus


# ==========================================================
# FILTER TRIPS FOR A PACKAGE
# ==========================================================

def filter_trips(package):
    """
    Return candidate trips for a package.

    Database-level filtering only.
    Final compatibility is always checked by MatchService.
    """

    today = timezone.localdate()

    return (
        Trip.objects
        .filter(
            # --------------------------------------------------
            # ELIGIBILITY
            # --------------------------------------------------

            is_active=True,
            is_public=True,
            status=TripStatus.PLANNED,

            # --------------------------------------------------
            # FUTURE TRIP
            # --------------------------------------------------

            departure_date__gte=today,

            # --------------------------------------------------
            # ROUTE
            # --------------------------------------------------

            from_country__iexact=package.pickup_country,
            from_city__iexact=package.pickup_city,

            to_country__iexact=package.destination_country,
            to_city__iexact=package.destination_city,

            # --------------------------------------------------
            # CAPACITY
            # --------------------------------------------------

            available_weight_kg__gte=package.weight,

            # --------------------------------------------------
            # DATE COMPATIBILITY
            # --------------------------------------------------

            departure_date__gte=package.pickup_date,
            arrival_date__lte=package.latest_delivery_date,
        )
        .exclude(
            traveler_id=package.sender_id,
        )
    )


# ==========================================================
# FILTER PACKAGES FOR A TRIP
# ==========================================================

def filter_packages(trip):
    """
    Return candidate packages for a trip.

    Database-level filtering only.
    Final compatibility is always checked by MatchService.
    """

    today = timezone.localdate()

    return (
        Package.objects
        .filter(
            # --------------------------------------------------
            # ELIGIBILITY
            # --------------------------------------------------

            is_active=True,
            is_public=True,
            status=PackageStatus.PUBLISHED,

            # --------------------------------------------------
            # ROUTE
            # --------------------------------------------------

            pickup_country__iexact=trip.from_country,
            pickup_city__iexact=trip.from_city,

            destination_country__iexact=trip.to_country,
            destination_city__iexact=trip.to_city,

            # --------------------------------------------------
            # CAPACITY
            # --------------------------------------------------

            weight__lte=trip.available_weight_kg,

            # --------------------------------------------------
            # DATE COMPATIBILITY
            # --------------------------------------------------

            pickup_date__lte=trip.departure_date,
            latest_delivery_date__gte=trip.arrival_date,
        )
        .exclude(
            sender_id=trip.traveler_id,
        )
    )