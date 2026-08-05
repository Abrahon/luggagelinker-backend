"""
==========================================================
REVIEW SERVICES
==========================================================

Business logic for review & rating system.

Responsibilities:

- Update traveler average rating
- Recalculate statistics
- Future review-related business rules

Notifications are handled separately inside:

apps.notifications.services
"""

import logging

from decimal import Decimal

from django.db import transaction

logger = logging.getLogger(__name__)


# ==========================================================
# UPDATE TRAVELER RATING
# ==========================================================

@transaction.atomic
def update_traveler_rating(
    *,
    traveler,
    rating,
):
    """
    Updates traveler rating statistics.

    Called after every successful review creation.
    """

    profile = traveler.profile

    profile.total_reviews += 1
    profile.total_rating += rating

    profile.average_rating = round(
        Decimal(profile.total_rating) /
        Decimal(profile.total_reviews),
        2,
    )

    profile.save(
        update_fields=[
            "total_reviews",
            "total_rating",
            "average_rating",
        ]
    )

    logger.info(
        f"Traveler rating updated | "
        f"Traveler={traveler.id} | "
        f"Average={profile.average_rating}"
    )

    return profile


# ==========================================================
# RECALCULATE TRAVELER RATING
# ==========================================================

from django.db.models import Avg, Count, Sum

@transaction.atomic
def recalculate_traveler_rating(*, traveler):
    """
    Recalculate rating from database using DB aggregates.
    """
    from .models import Review

    profile = traveler.profile

    stats = Review.objects.filter(traveler=traveler).aggregate(
        total_reviews=Count("id"),
        total_rating=Sum("rating"),
        avg_rating=Avg("rating"),
    )

    total_reviews = stats["total_reviews"] or 0
    total_rating = stats["total_rating"] or 0
    avg_rating = stats["avg_rating"] or 0.0

    profile.total_reviews = total_reviews
    profile.total_rating = total_rating
    profile.average_rating = round(Decimal(str(avg_rating)), 2)

    profile.save(
        update_fields=[
            "total_reviews",
            "total_rating",
            "average_rating",
        ]
    )

    logger.info(f"Traveler rating recalculated | Traveler={traveler.id}")

    return profile

# ==========================================================
# GET RATING SUMMARY
# ==========================================================

def get_rating_summary(
    *,
    traveler,
):
    """
    Returns traveler review statistics.

    Useful for profile page and dashboards.
    """

    profile = traveler.profile

    return {
        "average_rating": profile.average_rating,
        "total_reviews": profile.total_reviews,
        "total_rating": profile.total_rating,
    }