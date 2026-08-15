"""
==========================================================
MATCH SERVICE
==========================================================

Responsible for:
- Checking package/trip compatibility
- Creating matches
- Updating existing matches
- Deactivating stale matches
- Refreshing package/trip matches

IMPORTANT:
Pricing is NOT handled here.

Traveler pricing comes from:
    Trip.reward_per_kg

Final pricing is handled by:
    Booking Request / Negotiation

MATCHING RULE:
A package can participate in matching ONLY when:

    package.status == PUBLISHED
    package.is_active == True
    package.is_public == True

A trip can participate in matching ONLY when:

    trip.is_public == True
    trip.is_active == True
==========================================================
"""

import logging

from django.db import transaction
from django.utils import timezone

from apps.packages.models import Package, PackageStatus
from apps.matching.models import Match, MatchStatus

logger = logging.getLogger(__name__)


# ==========================================================
# CREATE OR UPDATE MATCH
# ==========================================================

@transaction.atomic
def create_or_update_match(package, trip, score):
    """
    Create or update a Match.

    IMPORTANT:
    This function also performs a final safety check so that
    an unpublished package or inactive/private package can
    never create an active Match.
    """

    # ------------------------------------------------------
    # FINAL PACKAGE SAFETY CHECK
    # ------------------------------------------------------

    if (
        package.status != PackageStatus.PUBLISHED
        or not package.is_active
        or not package.is_public
    ):
        Match.objects.filter(
            package=package,
            trip=trip,
            is_active=True,
        ).update(
            is_active=False,
            updated_at=timezone.now(),
        )

        logger.info(
            "Match blocked | Package=%s is not published/public/active",
            package.id,
        )

        return None

    # ------------------------------------------------------
    # FINAL TRIP SAFETY CHECK
    # ------------------------------------------------------

    if (
        not trip.is_public
        or not trip.is_active
    ):
        Match.objects.filter(
            package=package,
            trip=trip,
            is_active=True,
        ).update(
            is_active=False,
            updated_at=timezone.now(),
        )

        logger.info(
            "Match blocked | Trip=%s is not public/active",
            trip.id,
        )

        return None

    # ------------------------------------------------------
    # CREATE / GET MATCH
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

    # ------------------------------------------------------
    # NEW MATCH
    # ------------------------------------------------------

    if created:

        logger.info(
            "Match created | Package=%s Trip=%s Score=%s",
            package.id,
            trip.id,
            score,
        )

        return match

    changed_fields = []

    # ------------------------------------------------------
    # UPDATE SCORE
    # ------------------------------------------------------

    if match.score != score:
        match.score = score
        changed_fields.append("score")

    # ------------------------------------------------------
    # REACTIVATE MATCH
    # ------------------------------------------------------

    if not match.is_active:
        match.is_active = True
        changed_fields.append("is_active")

    # ------------------------------------------------------
    # RESET STATUS
    # ------------------------------------------------------

    if match.status != MatchStatus.AVAILABLE:
        match.status = MatchStatus.AVAILABLE
        changed_fields.append("status")

    # ------------------------------------------------------
    # SAVE
    # ------------------------------------------------------

    if changed_fields:

        match.updated_at = timezone.now()
        changed_fields.append("updated_at")

        match.save(
            update_fields=changed_fields
        )

        logger.info(
            "Match updated | Package=%s Trip=%s Score=%s",
            package.id,
            trip.id,
            score,
        )

    return match


# ==========================================================
# DEACTIVATE MATCH
# ==========================================================

@transaction.atomic
def deactivate_match(match):
    """
    Soft deactivate a Match.
    """

    if not match.is_active:
        return match

    match.is_active = False
    match.updated_at = timezone.now()

    match.save(
        update_fields=[
            "is_active",
            "updated_at",
        ]
    )

    logger.info(
        "Match deactivated | Match=%s Package=%s Trip=%s",
        match.id,
        match.package_id,
        match.trip_id,
    )

    return match


# ==========================================================
# MATCH SERVICE
# ==========================================================

class MatchService:

    # ======================================================
    # NORMALIZE
    # ======================================================

    @staticmethod
    def normalize(value):
        """
        Normalize country/city strings before comparison.
        """

        if not value:
            return ""

        return value.strip().casefold()

    # ======================================================
    # CHECK PACKAGE ELIGIBILITY
    # ======================================================

    @staticmethod
    def package_can_match(package):
        """
        A package can participate in matching ONLY when
        Admin has published it.
        """

        return (
            package.status == PackageStatus.PUBLISHED
            and package.is_active
            and package.is_public
        )

    # ======================================================
    # CHECK TRIP ELIGIBILITY
    # ======================================================

    @staticmethod
    def trip_can_match(trip):
        """
        A trip can participate in matching only when
        it is public and active.
        """

        return (
            trip.is_public
            and trip.is_active
        )

    # ======================================================
    # CHECK PACKAGE/TRIP COMPATIBILITY
    # ======================================================

    @staticmethod
    def is_compatible(package, trip):
        """
        Determine whether a package is compatible with a trip.

        Matching rules:

        1. Package must be PUBLISHED
        2. Package must be ACTIVE
        3. Package must be PUBLIC
        4. Trip must be ACTIVE
        5. Trip must be PUBLIC
        6. Exact pickup country
        7. Exact pickup city
        8. Exact destination country
        9. Exact destination city
        10. Package pickup date <= trip departure date
        11. Package delivery deadline >= trip arrival date
        12. Package weight <= available trip capacity

        Pricing is NOT checked here.
        """

        # --------------------------------------------------
        # PACKAGE ELIGIBILITY
        # --------------------------------------------------

        if not MatchService.package_can_match(package):
            return False

        # --------------------------------------------------
        # TRIP ELIGIBILITY
        # --------------------------------------------------

        if not MatchService.trip_can_match(trip):
            return False

        # --------------------------------------------------
        # DO NOT MATCH OWN PACKAGE
        # --------------------------------------------------

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

        if package.weight > trip.available_weight_kg:
            return False

        return True

    # ======================================================
    # CALCULATE MATCH SCORE
    # ======================================================

    @staticmethod
    def calculate_score(package, trip):

        # Do not calculate a meaningful score for an
        # ineligible package/trip.

        if not MatchService.is_compatible(
            package,
            trip,
        ):
            return 0

        score = 0

        # --------------------------------------------------
        # PICKUP COUNTRY
        # --------------------------------------------------

        if (
            MatchService.normalize(package.pickup_country)
            == MatchService.normalize(trip.from_country)
        ):
            score += 20

        # --------------------------------------------------
        # PICKUP CITY
        # --------------------------------------------------

        if (
            MatchService.normalize(package.pickup_city)
            == MatchService.normalize(trip.from_city)
        ):
            score += 20

        # --------------------------------------------------
        # DESTINATION COUNTRY
        # --------------------------------------------------

        if (
            MatchService.normalize(package.destination_country)
            == MatchService.normalize(trip.to_country)
        ):
            score += 20

        # --------------------------------------------------
        # DESTINATION CITY
        # --------------------------------------------------

        if (
            MatchService.normalize(package.destination_city)
            == MatchService.normalize(trip.to_city)
        ):
            score += 20

        # --------------------------------------------------
        # WEIGHT
        # --------------------------------------------------

        if trip.available_weight_kg > 0:

            remaining_capacity = (
                trip.available_weight_kg - package.weight
            )

            if remaining_capacity >= 0:
                score += 10

        # --------------------------------------------------
        # PICKUP DATE
        # --------------------------------------------------

        if (
            package.pickup_date
            and trip.departure_date
            and package.pickup_date <= trip.departure_date
        ):
            score += 5

        # --------------------------------------------------
        # DELIVERY DATE
        # --------------------------------------------------

        if (
            package.latest_delivery_date
            and trip.arrival_date
            and package.latest_delivery_date >= trip.arrival_date
        ):
            score += 5

        return min(score, 100)

    # ======================================================
    # FIND COMPATIBLE PACKAGES
    # ======================================================

    @staticmethod
    def find_compatible_packages(trip, sender):
        """
        Return ONLY published/public/active packages
        belonging to the sender.
        """

        # --------------------------------------------------
        # TRIP MUST BE ELIGIBLE
        # --------------------------------------------------

        if not MatchService.trip_can_match(trip):
            return []

        packages = Package.objects.filter(
            sender=sender,
            status=PackageStatus.PUBLISHED,
            is_active=True,
            is_public=True,
        )

        compatible = []

        for package in packages:

            if MatchService.is_compatible(
                package,
                trip,
            ):
                compatible.append(package)

        return compatible

    # ======================================================
    # FIND COMPATIBLE TRIPS
    # ======================================================

    @staticmethod
    def find_compatible_trips(package):
        """
        Return ONLY public/active trips for a
        PUBLISHED package.
        """

        # --------------------------------------------------
        # PACKAGE MUST BE PUBLISHED
        # --------------------------------------------------

        if not MatchService.package_can_match(package):
            return []

        # --------------------------------------------------
        # LOCAL IMPORT
        # --------------------------------------------------

        from apps.trips.models import Trip

        trips = Trip.objects.filter(
            is_public=True,
            is_active=True,
        ).exclude(
            traveler_id=package.sender_id,
        )

        compatible = []

        for trip in trips:

            if MatchService.is_compatible(
                package,
                trip,
            ):
                compatible.append(trip)

        return compatible

    # ======================================================
    # REFRESH PACKAGE MATCHES
    # ======================================================

    @staticmethod
    @transaction.atomic
    def refresh_package_matches(package):
        """
        Recalculate matches for one package.

        If package is NOT PUBLISHED:
            - deactivate all existing matches
            - create nothing
            - return []

        If package IS PUBLISHED:
            - find compatible trips
            - create/update matches
            - deactivate stale matches
        """

        # --------------------------------------------------
        # PACKAGE NOT READY
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
                "Package not eligible for matching | "
                "Package=%s Status=%s Active=%s Public=%s",
                package.id,
                package.status,
                package.is_active,
                package.is_public,
            )

            return []

        # --------------------------------------------------
        # FIND COMPATIBLE TRIPS
        # --------------------------------------------------

        compatible_trips = (
            MatchService.find_compatible_trips(
                package
            )
        )

        compatible_trip_ids = {
            trip.id
            for trip in compatible_trips
        }

        # --------------------------------------------------
        # DEACTIVATE STALE MATCHES
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
        # CREATE / UPDATE
        # --------------------------------------------------

        matches = []

        for trip in compatible_trips:

            score = MatchService.calculate_score(
                package,
                trip,
            )

            match = create_or_update_match(
                package=package,
                trip=trip,
                score=score,
            )

            if match:
                matches.append(match)

        logger.info(
            "Package matches refreshed | "
            "Package=%s Matches=%s",
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
        """
        Recalculate matches for one trip.

        Only PUBLISHED + ACTIVE + PUBLIC packages
        can be matched.
        """

        # --------------------------------------------------
        # TRIP NOT READY
        # --------------------------------------------------

        if not MatchService.trip_can_match(trip):

            Match.objects.filter(
                trip=trip,
                is_active=True,
            ).update(
                is_active=False,
                updated_at=timezone.now(),
            )

            logger.info(
                "Trip not eligible for matching | "
                "Trip=%s Public=%s Active=%s",
                trip.id,
                trip.is_public,
                trip.is_active,
            )

            return []

        # --------------------------------------------------
        # ONLY PUBLISHED PACKAGES
        # --------------------------------------------------

        packages = Package.objects.filter(
            status=PackageStatus.PUBLISHED,
            is_active=True,
            is_public=True,
        ).exclude(
            sender=trip.traveler,
        )

        compatible_package_ids = set()
        matches = []

        # --------------------------------------------------
        # FIND COMPATIBLE PACKAGES
        # --------------------------------------------------

        for package in packages:

            if not MatchService.is_compatible(
                package,
                trip,
            ):
                continue

            compatible_package_ids.add(
                package.id
            )

            score = MatchService.calculate_score(
                package,
                trip,
            )

            match = create_or_update_match(
                package=package,
                trip=trip,
                score=score,
            )

            if match:
                matches.append(match)

        # --------------------------------------------------
        # DEACTIVATE STALE MATCHES
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

        logger.info(
            "Trip matches refreshed | "
            "Trip=%s Matches=%s",
            trip.id,
            len(matches),
        )

        return matches