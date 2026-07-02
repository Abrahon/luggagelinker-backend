from apps.packages.models import Package, PackageStatus
from apps.trips.models import Trip, TripStatus


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
            # FIX: Match on PLANNED or ACTIVE trips, not just ACTIVE
            status__in=[TripStatus.PLANNED, TripStatus.ACTIVE],
            
            # ROUTE MATCHING (Country + City)
            from_country__iexact=package.pickup_country,
            from_city__iexact=package.pickup_city,
            to_country__iexact=package.destination_country,
            to_city__iexact=package.destination_city,
            
            # CAPACITY
            available_weight_kg__gte=package.weight,
            
            # TIMING
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
            # FIX: Look for DRAFT or PUBLISHED packages (avoiding the non-existent "PENDING")
            status__in=[PackageStatus.DRAFT, PackageStatus.PUBLISHED],
            
            # ROUTE MATCHING (Country + City)
            pickup_country__iexact=trip.from_country,
            pickup_city__iexact=trip.from_city,
            destination_country__iexact=trip.to_country,
            destination_city__iexact=trip.to_city,
            
            # CAPACITY
            weight__lte=trip.available_weight_kg,
            
            # TIMING
            pickup_date__lte=trip.departure_date,
            latest_delivery_date__gte=trip.arrival_date,
        )
        .exclude(
            sender=trip.traveler,
        )
    )