"""
==========================================================
MATCH SERVICE
==========================================================

Single source of truth for Package <-> Trip matching.

Package can match ONLY when:
    status = PUBLISHED
    is_active = True
    is_public = True

Trip can match ONLY when:
    is_public = True
    is_active = True

Matching rules:
    - Same pickup country
    - Same pickup city
    - Same destination country
    - Same destination city
    - Package pickup date <= trip departure date
    - Package latest delivery date >= trip arrival date
    - Package weight <= trip available capacity
    - Sender cannot match their own trip
==========================================================
"""

import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.packages.models import Package, PackageStatus
from apps.matching.models import Match, MatchStatus
from apps.matching.services.scoring import calculate_match_score

logger = logging.getLogger(__name__)


# ==========================================================
# CREATE / UPDATE MATCH
# ==========================================================

def create_or_update_match(package, trip, score):

    # ------------------------------------------------------
    # FINAL SAFETY CHECK
    # ------------------------------------------------------

    if not MatchService.package_can_match(package):

        Match.objects.filter(
            package=package,
            trip=trip,
            is_active=True,
        ).update(
            is_active=False,
            updated_at=timezone.now(),
        )

        return None

    if not MatchService.trip_can_match(trip):

        Match.objects.filter(
            package=package,
            trip=trip,
            is_active=True,
        ).update(
            is_active=False,
            updated_at=timezone.now(),
        )

        return None

    # ------------------------------------------------------
    # CREATE / UPDATE
    # ------------------------------------------------------

    match, created = Match.objects.get_or_create(
        package=package,
        trip=trip,
        defaults={
            "score": score,
            "status": MatchStatus.AVAILABLE,
            "is_active": True,
        },
    )

    if created:

        logger.info(
            "MATCH CREATED | package=%s | trip=%s | score=%s",
            package.id,
            trip.id,
            score,
        )

        return match

    # ------------------------------------------------------
    # UPDATE EXISTING MATCH
    # ------------------------------------------------------

    changed = []

    if match.score != score:
        match.score = score
        changed.append("score")

    if not match.is_active:
        match.is_active = True
        changed.append("is_active")

    if match.status in [
        MatchStatus.REJECTED,
        MatchStatus.EXPIRED,
    ]:
        match.status = MatchStatus.AVAILABLE
        changed.append("status")

    if changed:

        match.updated_at = timezone.now()
        changed.append("updated_at")

        match.save(
            update_fields=changed
        )

        logger.info(
            "MATCH UPDATED | package=%s | trip=%s | score=%s",
            package.id,
            trip.id,
            score,
        )

    return match


class MatchService:

    # ======================================================
    # NORMALIZE
    # ======================================================

    @staticmethod
    def normalize(value):

        if value is None:
            return ""

        return str(value).strip().casefold()

    # ======================================================
    # PACKAGE ELIGIBILITY
    # ======================================================

    @staticmethod
    def package_can_match(package):

        return (
            package.status == PackageStatus.PUBLISHED
            and package.is_active is True
            and package.is_public is True
        )

    # ======================================================
    # TRIP ELIGIBILITY
    # ======================================================

    @staticmethod
    def trip_can_match(trip):

        return (
            trip.is_public is True
            and trip.is_active is True
        )

    # ======================================================
    # COMPATIBILITY
    # ======================================================

    @staticmethod
    def is_compatible(package, trip):

        # Package
        if not MatchService.package_can_match(package):
            return False

        # Trip
        if not MatchService.trip_can_match(trip):
            return False

        # Prevent own trip
        if trip.traveler_id == package.sender_id:
            return False

        # --------------------------------------------------
        # PICKUP COUNTRY
        # --------------------------------------------------

        if (
            MatchService.normalize(package.pickup_country)
            != MatchService.normalize(trip.from_country)
        ):
            return False

        # --------------------------------------------------
        # PICKUP CITY
        # --------------------------------------------------

        if (
            MatchService.normalize(package.pickup_city)
            != MatchService.normalize(trip.from_city)
        ):
            return False

        # --------------------------------------------------
        # DESTINATION COUNTRY
        # --------------------------------------------------

        if (
            MatchService.normalize(package.destination_country)
            != MatchService.normalize(trip.to_country)
        ):
            return False

        # --------------------------------------------------
        # DESTINATION CITY
        # --------------------------------------------------

        if (
            MatchService.normalize(package.destination_city)
            != MatchService.normalize(trip.to_city)
        ):
            return False

        # --------------------------------------------------
        # PICKUP DATE
        # --------------------------------------------------

        if (
            package.pickup_date
            and trip.departure_date
            and package.pickup_date > trip.departure_date
        ):
            return False

        # --------------------------------------------------
        # DELIVERY DATE
        # --------------------------------------------------

        if (
            package.latest_delivery_date
            and trip.arrival_date
            and package.latest_delivery_date < trip.arrival_date
        ):
            return False

        # --------------------------------------------------
        # WEIGHT
        # --------------------------------------------------

        available_weight = (
            trip.available_weight_kg
            if trip.available_weight_kg is not None
            else Decimal("0")
        )

        if package.weight > available_weight:
            return False

        return True

    # ======================================================
    # SCORE
    # ======================================================

    @staticmethod
    def calculate_score(package, trip):

        if not MatchService.is_compatible(
            package,
            trip,
        ):
            return Decimal("0.00")

        return calculate_match_score(
            package=package,
            trip=trip,
        )

    # ======================================================
    # FIND COMPATIBLE TRIPS
    # ======================================================

    @staticmethod
    def find_compatible_trips(package):

        if not MatchService.package_can_match(package):
            return []

        from apps.trips.models import Trip

        trips = (
            Trip.objects
            .filter(
                is_public=True,
                is_active=True,
            )
            .exclude(
                traveler_id=package.sender_id
            )
        )

        return [
            trip
            for trip in trips
            if MatchService.is_compatible(
                package,
                trip,
            )
        ]

    # ======================================================
    # FIND COMPATIBLE PACKAGES
    # ======================================================

    @staticmethod
    def find_compatible_packages(trip):

        if not MatchService.trip_can_match(trip):
            return []

        packages = (
            Package.objects
            .filter(
                status=PackageStatus.PUBLISHED,
                is_active=True,
                is_public=True,
            )
            .exclude(
                sender_id=trip.traveler_id
            )
        )

        return [
            package
            for package in packages
            if MatchService.is_compatible(
                package,
                trip,
            )
        ]

    # ======================================================
    # REFRESH PACKAGE MATCHES
    # ======================================================

    @staticmethod
    @transaction.atomic
    def refresh_package_matches(package):

        logger.info(
            "Refreshing package matches | package=%s | status=%s",
            package.id,
            package.status,
        )

        # --------------------------------------------------
        # PACKAGE NOT ELIGIBLE
        # --------------------------------------------------

        if not MatchService.package_can_match(package):

            Match.objects.filter(
                package=package,
                is_active=True,
            ).update(
                is_active=False,
                updated_at=timezone.now(),
            )

            logger.info(
                "Package not eligible | package=%s",
                package.id,
            )

            return []

        # --------------------------------------------------
        # FIND COMPATIBLE TRIPS
        # --------------------------------------------------

        trips = MatchService.find_compatible_trips(
            package
        )

        compatible_trip_ids = {
            trip.id
            for trip in trips
        }

        # --------------------------------------------------
        # DEACTIVATE OLD MATCHES
        # --------------------------------------------------

        Match.objects.filter(
            package=package,
            is_active=True,
        ).exclude(
            trip_id__in=compatible_trip_ids
        ).update(
            is_active=False,
            updated_at=timezone.now(),
        )

        # --------------------------------------------------
        # CREATE MATCHES
        # --------------------------------------------------

        matches = []

        for trip in trips:

            score = MatchService.calculate_score(
                package,
                trip,
            )

            if score <= 0:
                continue

            match = create_or_update_match(
                package=package,
                trip=trip,
                score=score,
            )

            if match:
                matches.append(match)

        logger.info(
            "Package matching completed | package=%s | matches=%s",
            package.id,
            len(matches),
        )

        return matches

    # ======================================================
    # REFRESH TRIP MATCHES
    # ======================================================

    @staticmethod
    @transaction.atomic
    def refresh_trip_matches(trip):

        logger.info(
            "Refreshing trip matches | trip=%s",
            trip.id,
        )

        # --------------------------------------------------
        # TRIP NOT ELIGIBLE
        # --------------------------------------------------

        if not MatchService.trip_can_match(trip):

            Match.objects.filter(
                trip=trip,
                is_active=True,
            ).update(
                is_active=False,
                updated_at=timezone.now(),
            )

            return []

        # --------------------------------------------------
        # FIND COMPATIBLE PACKAGES
        # --------------------------------------------------

        packages = MatchService.find_compatible_packages(
            trip
        )

        compatible_package_ids = {
            package.id
            for package in packages
        }

        # --------------------------------------------------
        # DEACTIVATE OLD
        # --------------------------------------------------

        Match.objects.filter(
            trip=trip,
            is_active=True,
        ).exclude(
            package_id__in=compatible_package_ids
        ).update(
            is_active=False,
            updated_at=timezone.now(),
        )

        # --------------------------------------------------
        # CREATE
        # --------------------------------------------------

        matches = []

        for package in packages:

            score = MatchService.calculate_score(
                package,
                trip,
            )

            if score <= 0:
                continue

            match = create_or_update_match(
                package=package,
                trip=trip,
                score=score,
            )

            if match:
                matches.append(match)

        logger.info(
            "Trip matching completed | trip=%s | matches=%s",
            trip.id,
            len(matches),
        )

        return matches