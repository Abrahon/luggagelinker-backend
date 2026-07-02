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

def run_package_matching(package):
    """
    Match a package against all eligible trips safely without long database transaction blocks.
    """
    matches = []
    # Force evaluation cleanly using iterator to save web server memory pools
    eligible_trips = filter_trips(package).iterator()

    for trip in eligible_trips:
        score = calculate_match_score(package=package, trip=trip)

        # Drop anything below target match standard threshold
        if score < 70:
            continue

        # Single atomic execution transaction encapsulates inside this handler loop 
        match = create_or_update_match(package=package, trip=trip, score=score)
        matches.append(match)

    return matches