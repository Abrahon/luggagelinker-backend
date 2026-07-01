"""
===========================================================
MATCH SCORING ENGINE
===========================================================

This module calculates the compatibility score between
a Package and a Trip.

Maximum Score = 100

Scoring Rules
-------------
Pickup Country      = 20
Pickup City         = 10
Destination Country = 20
Destination City    = 10
Date Compatibility  = 20
Weight Capacity     = 20
"""

from decimal import Decimal


# ===========================================================
# SCORE CONSTANTS
# ===========================================================

PICKUP_COUNTRY_SCORE = Decimal("20")
PICKUP_CITY_SCORE = Decimal("10")

DEST_COUNTRY_SCORE = Decimal("20")
DEST_CITY_SCORE = Decimal("10")

DATE_SCORE = Decimal("20")
WEIGHT_SCORE = Decimal("20")

MAX_SCORE = Decimal("100")


# ===========================================================
# HELPERS
# ===========================================================

def normalize(value):

    """
    Normalize string for comparison.
    """

    if not value:
        return ""

    return value.strip().lower()


# ===========================================================
# DATE MATCH
# ===========================================================

def date_matches(package, trip):

    """
    Trip departure must be on or after package pickup.

    Trip arrival must be before package latest delivery.
    """

    return (
        trip.departure_date >= package.pickup_date
        and
        trip.arrival_date <= package.latest_delivery_date
    )


# ===========================================================
# WEIGHT MATCH
# ===========================================================

def weight_matches(package, trip):

    """
    Trip must have enough available luggage space.
    """

    return (
        trip.available_weight_kg >= package.weight
    )


# ===========================================================
# MAIN SCORING FUNCTION
# ===========================================================

def calculate_match_score(package, trip):

    """
    Calculate compatibility score.

    Returns:
        Decimal
    """

    score = Decimal("0")

    # ======================================================
    # PICKUP COUNTRY
    # ======================================================

    if normalize(package.pickup_country) == normalize(
        trip.from_country
    ):

        score += PICKUP_COUNTRY_SCORE

    # ======================================================
    # PICKUP CITY
    # ======================================================

    if normalize(package.pickup_city) == normalize(
        trip.from_city
    ):

        score += PICKUP_CITY_SCORE

    # ======================================================
    # DESTINATION COUNTRY
    # ======================================================

    if normalize(package.destination_country) == normalize(
        trip.to_country
    ):

        score += DEST_COUNTRY_SCORE

    # ======================================================
    # DESTINATION CITY
    # ======================================================

    if normalize(package.destination_city) == normalize(
        trip.to_city
    ):

        score += DEST_CITY_SCORE

    # ======================================================
    # DATE
    # ======================================================

    if date_matches(package, trip):

        score += DATE_SCORE

    # ======================================================
    # WEIGHT
    # ======================================================

    if weight_matches(package, trip):

        score += WEIGHT_SCORE

    # Never exceed 100
    return min(score, MAX_SCORE)