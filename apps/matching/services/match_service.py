"""
==========================================================
MATCH SERVICE
==========================================================

Responsible for creating or updating Match records.
"""

import logging

from django.db import transaction

from apps.matching.models import Match, MatchStatus

logger = logging.getLogger(__name__)


# ==========================================================
# CREATE OR UPDATE MATCH
# ==========================================================

@transaction.atomic
def create_or_update_match(package, trip, score):
    """
    Create a new Match or update an existing one.

    Returns:
        Match
    """

    match, created = Match.objects.get_or_create(
        package=package,
        trip=trip,
        defaults={
            "score": score,
            "status": MatchStatus.PENDING,
            "is_active": True,
        },
    )

    if not created:

        changed = False

        if match.score != score:
            match.score = score
            changed = True

        if not match.is_active:
            match.is_active = True
            changed = True

        if changed:
            match.save(
                update_fields=[
                    "score",
                    "is_active",
                    "updated_at",
                ]
            )

            logger.info(
                f"Match updated | Package={package.id} "
                f"Trip={trip.id}"
            )

    else:

        logger.info(
            f"Match created | Package={package.id} "
            f"Trip={trip.id}"
        )

    return match


# ==========================================================
# DEACTIVATE MATCH
# ==========================================================

@transaction.atomic
def deactivate_match(match):
    """
    Soft delete a Match.
    """

    if not match.is_active:
        return match

    match.is_active = False

    match.save(
        update_fields=[
            "is_active",
            "updated_at",
        ]
    )

    logger.info(
        f"Match deactivated | Match={match.id}"
    )

    return match