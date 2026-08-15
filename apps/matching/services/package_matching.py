import logging

from .match_service import (
    MatchService,
    create_or_update_match,
)

from .filters import filter_trips

logger = logging.getLogger(__name__)


def run_package_matching(package):
    matches = []

    eligible_trips = filter_trips(package).iterator()

    for trip in eligible_trips:

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