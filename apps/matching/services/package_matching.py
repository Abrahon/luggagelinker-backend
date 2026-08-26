import logging

from .match_service import (
    MatchService,
    create_or_update_match,
)

logger = logging.getLogger(__name__)


def run_package_matching(package):
    """
    Find and create all compatible trip matches for a package.

    MatchService is the single source of truth for eligibility
    and compatibility.
    """

    matches = []

    # --------------------------------------------------
    # PACKAGE ELIGIBILITY
    # --------------------------------------------------

    if not MatchService.package_can_match(package):
        logger.info(
            "Package not eligible for matching | package=%s",
            package.id,
        )
        return []

    # --------------------------------------------------
    # FIND COMPATIBLE TRIPS
    # --------------------------------------------------

    trips = MatchService.find_compatible_trips(package)

    logger.info(
        "Compatible trips found | package=%s | count=%s",
        package.id,
        len(trips),
    )

    # --------------------------------------------------
    # CREATE MATCHES
    # --------------------------------------------------

    for trip in trips:

        score = MatchService.calculate_score(
            package,
            trip,
        )

        if score < 70:
            logger.info(
                "Trip skipped because score < 70 | "
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
        "Package matching completed | package=%s | matches=%s",
        package.id,
        len(matches),
    )

    return matches