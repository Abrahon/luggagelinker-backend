"""
==========================================================
NOTIFICATION SERVICES
==========================================================

Centralized notification creation.

Every module should use this service.

Example:
    - Matching Engine
    - Booking
    - Payment
    - Wallet
    - Delivery
    - Review
"""

import logging

from django.db import transaction

from .models import Notification


logger = logging.getLogger(__name__)


# ==========================================================
# CREATE SINGLE NOTIFICATION
# ==========================================================

@transaction.atomic
def create_notification(
    *,
    user,
    title,
    message,
    notification_type,
    object_id=None,
    action_url=None,
):
    """
    Create a notification.

    Returns:
        Notification
    """

    notification = Notification.objects.create(
        user=user,
        title=title,
        message=message,
        notification_type=notification_type,
        object_id=object_id,
        action_url=action_url,
    )

    logger.info(
        f"Notification created | "
        f"User={user.id} "
        f"Notification={notification.id}"
    )

    return notification


# ==========================================================
# CREATE BULK NOTIFICATIONS
# ==========================================================

@transaction.atomic
def create_bulk_notifications(
    *,
    users,
    title,
    message,
    notification_type,
    object_id=None,
    action_url=None,
):
    """
    Create notifications for multiple users.

    Returns:
        list[Notification]
    """

    notifications = [

        Notification(
            user=user,
            title=title,
            message=message,
            notification_type=notification_type,
            object_id=object_id,
            action_url=action_url,
        )

        for user in users

    ]

    Notification.objects.bulk_create(
        notifications
    )

    logger.info(
        f"{len(notifications)} notifications created."
    )

    return notifications


# ==========================================================
# MARK AS READ
# ==========================================================

@transaction.atomic
def mark_notification_as_read(notification):

    """
    Mark a notification as read.
    """

    if notification.is_read:
        return notification

    notification.is_read = True

    notification.save(
        update_fields=[
            "is_read",
            "updated_at",
        ]
    )

    logger.info(
        f"Notification marked as read | "
        f"{notification.id}"
    )

    return notification


# ==========================================================
# MARK ALL AS READ
# ==========================================================

@transaction.atomic
def mark_all_notifications_as_read(user):

    """
    Mark all notifications as read.

    Returns:
        int
    """

    updated = (
        Notification.objects.filter(
            user=user,
            is_active=True,
            is_read=False,
        )
        .update(
            is_read=True,
        )
    )

    logger.info(
        f"All notifications marked as read | "
        f"User={user.id}"
    )

    return updated