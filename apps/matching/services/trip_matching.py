import logging

from .match_service import (
    MatchService,
    create_or_update_match,
)

logger = logging.getLogger(__name__)


def run_trip_matching(trip):
    """
    Find and create all compatible package matches for a trip.

    MatchService is the single source of truth for eligibility
    and compatibility.
    """

    matches = []

    # --------------------------------------------------
    # TRIP ELIGIBILITY
    # --------------------------------------------------

    if not MatchService.trip_can_match(trip):
        logger.info(
            "Trip not eligible for matching | trip=%s",
            trip.id,
        )
        return []

    # --------------------------------------------------
    # FIND COMPATIBLE PACKAGES
    # --------------------------------------------------

    packages = MatchService.find_compatible_packages(trip)

    logger.info(
        "Compatible packages found | trip=%s | count=%s",
        trip.id,
        len(packages),
    )

    # --------------------------------------------------
    # CREATE MATCHES
    # --------------------------------------------------

    for package in packages:

        score = MatchService.calculate_score(
            package,
            trip,
        )

        if score < 70:
            logger.info(
                "Package skipped because score < 70 | "
                "package=%s | trip=%s | score=%s",
                package.id,
                trip.id,
                score,
            )
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