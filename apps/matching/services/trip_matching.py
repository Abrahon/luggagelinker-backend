import logging

from .match_service import (
    MatchService,
    create_or_update_match,
)

from .filters import filter_packages

logger = logging.getLogger(__name__)


def run_trip_matching(trip):
    matches = []

    eligible_packages = filter_packages(trip).iterator()

    for package in eligible_packages:

        if not MatchService.is_compatible(package, trip):
            continue

        score = MatchService.calculate_score(
            package,
            trip,
        )

        if score < 70:
            continue

        match = create_or_update_match(
            package=package,
            trip=trip,
            score=score,
        )

        if match:
            matches.append(match)

    return matches