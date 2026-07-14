
"""
==========================================================
NOTIFICATION SERVICES
==========================================================

Centralized notification creation.
Every module uses this service to ensure uniform message distribution.
"""

import logging
from django.db import transaction
from .models import Notification, NotificationType
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)



# live notification using  websocket
def send_notification_ws(notification):
    """
    Sends notification to the user's websocket.
    """

    channel_layer = get_channel_layer()

    async_to_sync(channel_layer.group_send)(
        f"notification_{notification.user_id}",
        {
            "type": "notification_event",
            "notification": {
                "id": str(notification.id),
                "title": notification.title,
                "message": notification.message,
                "notification_type": notification.notification_type,
                "object_id": (
                    str(notification.object_id)
                    if notification.object_id
                    else None
                ),
                "action_url": notification.action_url,
                "is_read": notification.is_read,
                "created_at": notification.created_at.isoformat(),
            },
        },
    )

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
    send_notification_ws(notification)
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
    Create notifications optimized for multiple users simultaneously.
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

    # Refresh objects so they contain generated IDs (recommended)
    notifications = list(
        Notification.objects.filter(
            user__in=users,
            title=title,
            notification_type=notification_type,
        ).order_by("-created_at")[: len(notifications)]
    )

    for notification in notifications:
        send_notification_ws(notification)

    logger.info(
        "%d notifications created via bulk pipeline.",
        len(notifications),
    )

    return notifications


# ==========================================================
# CREATE Chat NOTIFICATIONS
# ==========================================================



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
# DISPUTE MODULE INTEGRATIONS ⚖️ (Standalone Functions)
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
        action_url=f"/disputes/{dispute.id}/",
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


def notify_dispute_resolution(dispute):
    """
    New function: Dispatches resolution alerts to both parties at the same time.
    Perfect for clean importing within AdminDisputeService.
    """
    booking = dispute.booking
    resolution_label = dispute.get_resolution_display() if hasattr(dispute, 'get_resolution_display') else dispute.resolution
    message_text = f"Dispute case #{dispute.id} has been resolved via: {resolution_label}."

    # Notify Payer / Sender
    create_notification(
        user=booking.sender,
        title="Dispute Verdict Rendered ⚖️",
        message=message_text,
        notification_type=NotificationType.PAYMENT,
        object_id=dispute.id,
        action_url=f"/disputes/{dispute.id}/",
    )
    # Notify Receiver / Traveler
    return create_notification(
        user=booking.traveler,
        title="Dispute Verdict Rendered ⚖️",
        message=message_text,
        notification_type=NotificationType.PAYMENT,
        object_id=dispute.id,
        action_url=f"/disputes/{dispute.id}/",
    )


# ==========================================================
# WALLET CREDITED
# ==========================================================
def notify_wallet_credited(*, user, booking, amount):
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
    sender = review.sender
    sender_name = f"{sender.get_full_name()}".strip() if hasattr(sender, 'get_full_name') else ""
    if not sender_name:
        sender_name = getattr(sender, 'username', sender.email)

    return create_notification(
        user=user,
        title="New Review Received ⭐",
        message=f"You received a {review.rating}★ review from {sender_name}.",
        notification_type=NotificationType.REVIEW,
        object_id=str(review.id),
        action_url=f"/reviews/{review.id}/",
    )


