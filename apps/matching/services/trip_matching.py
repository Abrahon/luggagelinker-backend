"""
==========================================================
TRIP MATCHING ENGINE
==========================================================

Triggered whenever a new Trip is created.
"""

import logging

from django.db import transaction

from .filters import filter_packages
from .match_service import create_or_update_match
from .scoring import calculate_match_score


logger = logging.getLogger(__name__)


# ==========================================================
# TRIP MATCHING
# ==========================================================

def run_trip_matching(trip):
    """
    Match a trip against all eligible packages safely.
    """
    matches = []
    eligible_packages = filter_packages(trip).iterator()

    for package in eligible_packages:
        score = calculate_match_score(package=package, trip=trip)

        if score < 70:
            continue

        match = create_or_update_match(package=package, trip=trip, score=score)
        matches.append(match)

    return matches