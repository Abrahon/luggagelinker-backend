"""
==========================================================
PACKAGE MATCHING ENGINE
==========================================================

Triggered whenever a new Package is created.
"""

import logging

from django.db import transaction

from .filters import filter_trips
from .match_service import create_or_update_match
from .scoring import calculate_match_score


logger = logging.getLogger(__name__)


# ==========================================================
# PACKAGE MATCHING
# ==========================================================

@transaction.atomic
def run_package_matching(package):
    """
    Match a package against all eligible trips.

    Returns:
        list[Match]
    """

    matches = []

    eligible_trips = filter_trips(package)

    logger.info(
        f"Package={package.id} | "
        f"Eligible Trips={eligible_trips.count()}"
    )

    for trip in eligible_trips:

        score = calculate_match_score(
            package=package,
            trip=trip,
        )

        # Ignore very poor matches
        if score < 70:
            continue

        match = create_or_update_match(
            package=package,
            trip=trip,
            score=score,
        )

        matches.append(match)

    logger.info(
        f"Package={package.id} | "
        f"Matches Created={len(matches)}"
    )

    return matches