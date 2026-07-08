# """
# ==========================================================
# NOTIFICATION SERVICES
# ==========================================================

# Centralized notification creation.

# Every module should use this service.

# Example:
#     - Matching Engine
#     - Booking
#     - Payment
#     - Wallet
#     - Delivery
#     - Review
# """

# import logging

# from django.db import transaction

# from .models import Notification


# logger = logging.getLogger(__name__)


# # ==========================================================
# # CREATE SINGLE NOTIFICATION
# # ==========================================================

# @transaction.atomic
# def create_notification(
#     *,
#     user,
#     title,
#     message,
#     notification_type,
#     object_id=None,
#     action_url=None,
# ):
#     """
#     Create a notification.

#     Returns:
#         Notification
#     """

#     notification = Notification.objects.create(
#         user=user,
#         title=title,
#         message=message,
#         notification_type=notification_type,
#         object_id=object_id,
#         action_url=action_url,
#     )

#     logger.info(
#         f"Notification created | "
#         f"User={user.id} "
#         f"Notification={notification.id}"
#     )

#     return notification


# # ==========================================================
# # CREATE BULK NOTIFICATIONS
# # ==========================================================

# @transaction.atomic
# def create_bulk_notifications(
#     *,
#     users,
#     title,
#     message,
#     notification_type,
#     object_id=None,
#     action_url=None,
# ):
#     """
#     Create notifications for multiple users.

#     Returns:
#         list[Notification]
#     """

#     notifications = [

#         Notification(
#             user=user,
#             title=title,
#             message=message,
#             notification_type=notification_type,
#             object_id=object_id,
#             action_url=action_url,
#         )

#         for user in users

#     ]

#     Notification.objects.bulk_create(
#         notifications
#     )

#     logger.info(
#         f"{len(notifications)} notifications created."
#     )

#     return notifications




# # ==========================================================
# # MARK AS READ
# # ==========================================================

# @transaction.atomic
# def mark_notification_as_read(notification):

#     """
#     Mark a notification as read.
#     """

#     if notification.is_read:
#         return notification

#     notification.is_read = True

#     notification.save(
#         update_fields=[
#             "is_read",
#             "updated_at",
#         ]
#     )

#     logger.info(
#         f"Notification marked as read | "
#         f"{notification.id}"
#     )

#     return notification


# # ==========================================================
# # MARK ALL AS READ
# # ==========================================================

# @transaction.atomic
# def mark_all_notifications_as_read(user):

#     """
#     Mark all notifications as read.

#     Returns:
#         int
#     """

#     updated = (
#         Notification.objects.filter(
#             user=user,
#             is_active=True,
#             is_read=False,
#         )
#         .update(
#             is_read=True,
#         )
#     )

#     logger.info(
#         f"All notifications marked as read | "
#         f"User={user.id}"
#     )

#     return updated


# from apps.notifications.models import NotificationType
# # Assuming create_notification is imported here from your utilities
# # from .utils import create_notification


# # ==========================================================
# # WALLET CREDITED
# # ==========================================================

# def notify_wallet_credited(
#     *,
#     user,
#     booking,
#     amount,
# ):
#     return create_notification(
#         user=user,
#         title="Wallet Credited",
#         message=(
#             f"${amount} has been credited to your wallet "
#             f"for booking #{booking.tracking_number}."
#         ),
#         notification_type=NotificationType.WALLET,
#         object_id=booking.id,
#         action_url="/wallet/",
#     )


# # ==========================================================
# # WITHDRAWAL REQUESTED
# # ==========================================================

# def notify_withdrawal_requested(
#     *,
#     user,
#     withdrawal,
# ):
#     return create_notification(
#         user=user,
#         title="Withdrawal Requested",
#         message=(
#             f"Your withdrawal request of "
#             f"${withdrawal.amount} has been submitted."
#         ),
#         notification_type=NotificationType.WALLET,
#         object_id=withdrawal.id,
#         action_url="/wallet/withdrawals/",
#     )


# # ==========================================================
# # WITHDRAWAL APPROVED
# # ==========================================================

# def notify_withdrawal_approved(
#     *,
#     user,
#     withdrawal,
# ):
#     return create_notification(
#         user=user,
#         title="Withdrawal Approved",
#         message=(
#             f"Your withdrawal request of "
#             f"${withdrawal.amount} has been approved."
#         ),
#         notification_type=NotificationType.WALLET,
#         object_id=withdrawal.id,
#         action_url="/wallet/withdrawals/",
#     )


# # ==========================================================
# # WITHDRAWAL REJECTED
# # ==========================================================

# def notify_withdrawal_rejected(
#     *,
#     user,
#     withdrawal,
# ):
#     return create_notification(
#         user=user,
#         title="Withdrawal Rejected",
#         message=(
#             f"Your withdrawal request of "
#             f"${withdrawal.amount} has been rejected."
#         ),
#         notification_type=NotificationType.WALLET,
#         object_id=withdrawal.id,
#         action_url="/wallet/withdrawals/",
#     )


# # ==========================================================
# # REFUND COMPLETED
# # ==========================================================

# def notify_refund_completed(
#     *,
#     user,
#     booking,
#     amount,
# ):
#     return create_notification(
#         user=user,
#         title="Refund Completed",
#         message=(
#             f"${amount} has been refunded "
#             f"for booking #{booking.tracking_number}."
#         ),
#         notification_type=NotificationType.PAYMENT,
#         object_id=booking.id,
#         action_url=f"/bookings/{booking.id}/",
#     )


# # ==========================================================
# # REVIEW RECEIVED
# # ==========================================================

# @transaction.atomic
# def notify_review_received(
#     *,
#     user,
#     review,
# ):
#     """
#     Notify traveler that a new review has been received.
#     """

#     return create_notification(
#         user=user,
#         title="New Review Received ⭐",
#         message=(
#             f"You received a {review.rating}★ review "
#             f"from {review.sender.name}."
#         ),
#         notification_type=Notification.NotificationType.REVIEW,
#         object_id=str(review.id),
#         action_url=f"/reviews/{review.id}/",
#     )

"""
==========================================================
NOTIFICATION SERVICES
==========================================================

Centralized notification creation.
Every module uses this service to ensure uniform message distribution.
"""

import logging
from django.db import transaction

from apps import disputes
from .models import Notification, NotificationType

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
    Create a database-backed notification entry.
    """
    notification = Notification.objects.create(
        user=user,
        title=title,
        message=message,
        notification_type=notification_type,
        object_id=object_id,
        action_url=action_url,
    )

    logger.info("Notification created | User=%s Notification=%s", user.id, notification.id)
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
    Create notifications optimized for multiple users simultaneously using bulk_create.
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

    Notification.objects.bulk_create(notifications)
    logger.info("%d notifications created via bulk pipeline.", len(notifications))
    return notifications


# ==========================================================
# MARK AS READ
# ==========================================================
@transaction.atomic
def mark_notification_as_read(notification):
    """
    Mark a targeted notification instance as read.
    """
    if notification.is_read:
        return notification

    notification.is_read = True
    notification.save(update_fields=["is_read", "updated_at"])

    logger.info("Notification marked as read | %s", notification.id)
    return notification


# ==========================================================
# MARK ALL AS READ
# ==========================================================
@transaction.atomic
def mark_all_notifications_as_read(user):
    """
    Mark all unread active notifications for a specific user as read.
    """
    updated = Notification.objects.filter(
        user=user,
        is_active=True,
        is_read=False,
    ).update(is_read=True)

    logger.info("All notifications marked as read | User=%s count=%d", user.id, updated)
    return updated


# ==========================================================
# DISPUTE MODULE INTEGRATIONS ⚖️
# ==========================================================

def notify_dispute_opened(*, user, dispute):
    """Notifies a user that a dispute case file has been formally logged against them."""
    return create_notification(
        user=user,
        title="Dispute Case File Opened ⚠️",
        message=f"A dispute hold has been placed on booking #{dispute.booking.id} due to: {dispute.get_reason_display()}.",
        notification_type=NotificationType.BOOKING,
        object_id=dispute.id,
        action_url=f"/disputes/{dispute.id}/",
    )


def notify_dispute_evidence_requested(*, user, dispute):
    """Alerts a sender or traveler that administration needs documents or upload proofs."""
    return create_notification(
        user=user,
        title="Evidence Action Required 📋",
        message="An administrator has requested additional supporting evidence for your active dispute file.",
        notification_type=NotificationType.BOOKING,
        object_id=dispute.id,
        action_url=f"/disputes/{disputes.id}/",
    )


def notify_dispute_resolved(*, user, dispute, resolution_type):
    """Dispatches formal notice detailing the final arbitration decision on a claim."""
    return create_notification(
        user=user,
        title="Dispute Verdict Rendered ⚖️",
        message=f"Dispute case #{dispute.id} has been resolved via: {resolution_type}.",
        notification_type=NotificationType.PAYMENT,
        object_id=dispute.id,
        action_url=f"/disputes/{dispute.id}/",
    )


# ==========================================================
# WALLET CREDITED
# ==========================================================
def notify_wallet_credited(*, user, booking, amount):
    # Safe handling if tracking_number or id is preferred
    tracking = getattr(booking, 'tracking_number', booking.id)
    return create_notification(
        user=user,
        title="Wallet Credited",
        message=f"${amount} has been credited to your wallet for booking #{tracking}.",
        notification_type=NotificationType.WALLET,
        object_id=booking.id,
        action_url="/wallet/",
    )


# ==========================================================
# WITHDRAWAL PIPELINES
# ==========================================================
def notify_withdrawal_requested(*, user, withdrawal):
    return create_notification(
        user=user,
        title="Withdrawal Requested",
        message=f"Your withdrawal request of ${withdrawal.amount} has been submitted.",
        notification_type=NotificationType.WALLET,
        object_id=withdrawal.id,
        action_url="/wallet/withdrawals/",
    )


def notify_withdrawal_approved(*, user, withdrawal):
    return create_notification(
        user=user,
        title="Withdrawal Approved",
        message=f"Your withdrawal request of ${withdrawal.amount} has been approved.",
        notification_type=NotificationType.WALLET,
        object_id=withdrawal.id,
        action_url="/wallet/withdrawals/",
    )


def notify_withdrawal_rejected(*, user, withdrawal):
    return create_notification(
        user=user,
        title="Withdrawal Rejected",
        message=f"Your withdrawal request of ${withdrawal.amount} has been rejected.",
        notification_type=NotificationType.WALLET,
        object_id=withdrawal.id,
        action_url="/wallet/withdrawals/",
    )


# ==========================================================
# REFUND COMPLETED
# ==========================================================
def notify_refund_completed(*, user, booking, amount):
    tracking = getattr(booking, 'tracking_number', booking.id)
    return create_notification(
        user=user,
        title="Refund Completed",
        message=f"${amount} has been refunded for booking #{tracking}.",
        notification_type=NotificationType.PAYMENT,
        object_id=booking.id,
        action_url=f"/bookings/{booking.id}/",
    )


# ==========================================================
# REVIEW RECEIVED
# ==========================================================
@transaction.atomic
def notify_review_received(*, user, review):
    """
    Notify traveler that a new review has been received.
    """
    # 🔄 Fix: Fallback protection logic for name fields across user variations
    sender = review.sender
    sender_name = f"{sender.get_full_name()}".strip() if hasattr(sender, 'get_full_name') else ""
    if not sender_name:
        sender_name = getattr(sender, 'username', sender.email)

    return create_notification(
        user=user,
        title="New Review Received ⭐",
        message=f"You received a {review.rating}★ review from {sender_name}.",
        notification_type=NotificationType.REVIEW,  # 🔄 Fix: Unified types mapping
        object_id=str(review.id),
        action_url=f"/reviews/{review.id}/",
    )