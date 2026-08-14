"""
==========================================================
MATCH SERVICE
==========================================================

Responsible for creating or updating Match records.
"""

import logging

from django.db import transaction
from apps.packages.models import Package, PackageStatus
from apps.matching.models import Match, MatchStatus

logger = logging.getLogger(__name__)


# ==========================================================
# CREATE OR UPDATE MATCH
# ==========================================================

import logging
from django.db import transaction
from apps.matching.models import Match, MatchStatus

logger = logging.getLogger(__name__)

from django.utils import timezone  # Add this import at the top

@transaction.atomic
def create_or_update_match(package, trip, score):
    """
    Create a new Match or update an existing one within a tight atomic scope block.
    """
    match, created = Match.objects.get_or_create(
        package=package,
        trip=trip,
        defaults={
            "score": score,
            "status": MatchStatus.AVAILABLE,
            "is_active": True,
        },
    )

    if not created:
        changed = False
        if match.score != score:
            match.score = score
            changed = True
        if not match.is_active:
            match.is_active = True
            changed = True

        if changed:
            # FIX: Explicitly update the timestamp when restricting save fields
            match.updated_at = timezone.now()
            match.save(update_fields=["score", "is_active", "updated_at"])
            logger.info(f"Match updated | Package={package.id} Trip={trip.id}")
    else:
        logger.info(f"Match created | Package={package.id} Trip={trip.id}")

    return match


# ==========================================================
# DEACTIVATE MATCH
# ==========================================================

@transaction.atomic
def deactivate_match(match):
    """
    Soft delete a Match.
    """

    if not match.is_active:
        return match

    match.is_active = False

    match.save(
        update_fields=[
            "is_active",
            "updated_at",
        ]
    )

    logger.info(
        f"Match deactivated | Match={match.id}"
    )

    return match


# apps/matching/services.py




class MatchService:

    @staticmethod
    def find_compatible_packages(trip, sender):
        """
        Return sender's packages that are compatible
        with the selected trip.
        """

        packages = Package.objects.filter(
            sender=sender,
            status=PackageStatus.PUBLISHED,
            is_active=True,
        )

        compatible = []

        for package in packages:

            # -------------------------------
            # ROUTE
            # -------------------------------

            if (
                package.pickup_country.strip().casefold()
                != trip.from_country.strip().casefold()
            ):
                continue

            if (
                package.pickup_city.strip().casefold()
                != trip.from_city.strip().casefold()
            ):
                continue

            if (
                package.destination_country.strip().casefold()
                != trip.to_country.strip().casefold()
            ):
                continue

            if (
                package.destination_city.strip().casefold()
                != trip.to_city.strip().casefold()
            ):
                continue

            # -------------------------------
            # DATE
            # -------------------------------

            if (
                package.pickup_date
                and trip.departure_date
                and package.pickup_date > trip.departure_date
            ):
                continue

            if (
                package.latest_delivery_date
                and trip.arrival_date
                and trip.arrival_date > package.latest_delivery_date
            ):
                continue

            # -------------------------------
            # WEIGHT
            # -------------------------------

            if package.weight > trip.available_weight_kg:
                continue

            compatible.append(package)

        return compatible