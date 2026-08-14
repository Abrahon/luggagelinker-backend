"""
==========================================================
NOTIFICATION SERVICES
==========================================================

Centralized notification creation.
Every module uses this service to ensure uniform message distribution.
"""

import logging
from django.db import transaction
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model

from .models import Notification, NotificationType

User = get_user_model()
logger = logging.getLogger(__name__)


# Live notification using WebSocket
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
    """
    Create a database-backed notification entry and send WebSocket message.
    """
    notification = Notification.objects.create(
        user=user,
        title=title,
        message=message,
        notification_type=notification_type,
        object_id=object_id,
        action_url=action_url,
    )

    send_notification_ws(notification)

    logger.info(
        "Notification created | User=%s Notification=%s",
        user.id,
        notification.id,
    )

    return notification


# ==========================================================
# BOOKING REQUEST NOTIFICATION
# ==========================================================

@transaction.atomic
def create_booking_request_notification(
    *,
    booking,
    chat_room=None,
    chat_message=None,
):
    """
    Notify the traveler when a new booking request is created.

    This notification is specifically for:
        Sender -> Traveler

    It also optionally links the notification to the
    created chat room and system chat message.
    """

    traveler = booking.traveler
    sender = booking.sender

    sender_name = (
        getattr(sender, "username", None)
        or getattr(sender, "email", None)
        or "A sender"
    )

    package_title = (
        getattr(booking.package, "title", None)
        or "your package"
    )

    weight = booking.agreed_weight_kg

    trip = booking.trip

    route = (
        f"{trip.from_city} → {trip.to_city}"
        if trip
        else "your trip"
    )

    notification = create_notification(
        user=traveler,

        title="New Booking Request",

        message=(
            f"{sender_name} sent a booking request for "
            f"{package_title} ({weight} kg) "
            f"on your {route} trip."
        ),

        notification_type=NotificationType.BOOKING,

        # Booking is the main object.
        object_id=booking.id,

        action_url=(
            f"/bookings/{booking.id}/"
        ),

        sender=sender,

        room_id=(
            chat_room.id
            if chat_room
            else None
        ),

        message_id=(
            chat_message.id
            if chat_message
            else None
        ),
    )

    logger.info(
        "Booking request notification created | "
        "Booking=%s | Traveler=%s | Notification=%s",
        booking.id,
        traveler.id,
        notification.id,
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

    # Refresh objects to obtain generated IDs
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
# MARK AS READ
# ==========================================================
@transaction.atomic
def mark_notification_as_read(notification):
    if notification.is_read:
        return notification

    notification.is_read = True
    notification.save(update_fields=["is_read", "updated_at"])

    logger.info("Notification marked as read | %s", notification.id)
    return notification


@transaction.atomic
def mark_all_notifications_as_read(user):
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
    return create_notification(
        user=user,
        title="Dispute Case File Opened ⚠️",
        message=f"A dispute hold has been placed on booking #{dispute.booking.id} due to: {dispute.get_reason_display()}.",
        notification_type=NotificationType.BOOKING,
        object_id=dispute.id,
        action_url=f"/disputes/{dispute.id}/",
    )


def notify_dispute_evidence_requested(*, user, dispute):
    return create_notification(
        user=user,
        title="Evidence Action Required 📋",
        message="An administrator has requested additional supporting evidence for your active dispute file.",
        notification_type=NotificationType.BOOKING,
        object_id=dispute.id,
        action_url=f"/disputes/{dispute.id}/",
    )


def notify_dispute_resolved(*, user, dispute, resolution_type):
    return create_notification(
        user=user,
        title="Dispute Verdict Rendered ⚖️",
        message=f"Dispute case #{dispute.id} has been resolved via: {resolution_type}.",
        notification_type=NotificationType.PAYMENT,
        object_id=dispute.id,
        action_url=f"/disputes/{dispute.id}/",
    )


def notify_dispute_resolution(dispute):
    booking = dispute.booking
    resolution_label = (
        dispute.get_resolution_display()
        if hasattr(dispute, "get_resolution_display")
        else dispute.resolution
    )
    message_text = f"Dispute case #{dispute.id} has been resolved via: {resolution_label}."

    create_notification(
        user=booking.sender,
        title="Dispute Verdict Rendered ⚖️",
        message=message_text,
        notification_type=NotificationType.PAYMENT,
        object_id=dispute.id,
        action_url=f"/disputes/{dispute.id}/",
    )
    return create_notification(
        user=booking.traveler,
        title="Dispute Verdict Rendered ⚖️",
        message=message_text,
        notification_type=NotificationType.PAYMENT,
        object_id=dispute.id,
        action_url=f"/disputes/{dispute.id}/",
    )


# ==========================================================
# WALLET & WITHDRAWALS
# ==========================================================
def notify_wallet_credited(*, user, booking, amount):
    tracking = getattr(booking, "tracking_number", booking.id)
    return create_notification(
        user=user,
        title="Wallet Credited",
        message=f"${amount} has been credited to your wallet for booking #{tracking}.",
        notification_type=NotificationType.WALLET,
        object_id=booking.id,
        action_url="/wallet/",
    )


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


def notify_refund_completed(*, user, booking, amount):
    tracking = getattr(booking, "tracking_number", booking.id)
    return create_notification(
        user=user,
        title="Refund Completed",
        message=f"${amount} has been refunded for booking #{tracking}.",
        notification_type=NotificationType.PAYMENT,
        object_id=booking.id,
        action_url=f"/bookings/{booking.id}/",
    )


# ==========================================================
# REVIEWS & REPORTS 🚨
# ==========================================================
@transaction.atomic
def notify_review_received(*, user, review):
    sender = review.sender
    sender_name = (
        f"{sender.get_full_name()}".strip()
        if hasattr(sender, "get_full_name")
        else ""
    )
    if not sender_name:
        sender_name = getattr(sender, "username", sender.email)

    return create_notification(
        user=user,
        title="New Review Received ⭐",
        message=f"You received a {review.rating}★ review from {sender_name}.",
        notification_type=NotificationType.REVIEW,
        object_id=str(review.id),
        action_url=f"/reviews/{review.id}/",
    )




@transaction.atomic
def notify_review_updated(*, user, review):
    """
    Notify traveler that an existing review was edited by the sender.
    """
    sender = review.sender
    sender_name = (
        f"{sender.get_full_name()}".strip()
        if hasattr(sender, "get_full_name")
        else ""
    )
    if not sender_name:
        sender_name = getattr(sender, "username", sender.email)

    return create_notification(
        user=user,
        title="Review Updated 📝",
        message=f"{sender_name} updated their review score to {review.rating}★.",
        notification_type=NotificationType.REVIEW,
        object_id=str(review.id),
        action_url=f"/reviews/{review.id}/",
    )


def notify_admin_new_report(report):
    """
    Notify every active staff/admin when a new user report is submitted.
    """
    admins = User.objects.filter(is_staff=True, is_active=True)
    if not admins.exists():
        return []

    return create_bulk_notifications(
        users=admins,
        title="New User Report 🚨",
        message=f"{report.reporter.email} reported {report.reported_user.email}.",
        notification_type=NotificationType.REPORT,
        object_id=report.id,
        action_url=f"/admin/reports/{report.id}",
    )


def notify_report_resolved(report):
    """
    Notify the reporter when admin reviews/resolves their report.
    """
    return create_notification(
        user=report.reporter,
        title="Report Updated",
        message=f"Your report against {report.reported_user.email} has been reviewed.",
        notification_type=NotificationType.REPORT,
        object_id=report.id,
        action_url=f"/reports/{report.id}",
    )


def notify_user_warning(report):
    """
    Notify the reported user if a warning was issued to their account.
    """
    return create_notification(
        user=report.reported_user,
        title="Warning Issued ⚠️",
        message="A warning has been issued to your account after reviewing a report.",
        notification_type=NotificationType.REPORT,
        object_id=report.id,
        action_url="/profile",
    )


def notify_user_suspended(report, days):
    """
    Notify the reported user about account suspension.
    """
    return create_notification(
        user=report.reported_user,
        title="Account Suspended 🛑",
        message=f"Your account has been suspended for {days} days.",
        notification_type=NotificationType.REPORT,
        object_id=report.id,
        action_url="/profile",
    )


def notify_user_banned(report):
    """
    Notify the reported user about permanent ban.
    """
    return create_notification(
        user=report.reported_user,
        title="Account Permanently Banned ❌",
        message="Your account has been permanently banned for violating platform policies.",
        notification_type=NotificationType.REPORT,
        object_id=report.id,
        action_url="/support",
    )


# ==========================================================
# WALLET MODULE INTEGRATIONS 💳
# ==========================================================
def notify_wallet_topup_success(*, user, amount, reference=None):
    """
    Sends notification when a user successfully tops up their wallet.
    """
    # Safely select NotificationType (WALLET -> PAYMENT -> SYSTEM)
    notif_type = getattr(
        NotificationType,
        "WALLET",
        getattr(NotificationType, "PAYMENT", getattr(NotificationType, "SYSTEM", "WALLET")),
    )

    return create_bulk_notifications(
        users=[user],
        title="Wallet Top-up Successful",
        message=f"Your wallet has been successfully credited with ${amount:.2f}.",
        notification_type=notif_type,
        action_url="/wallet/",
    )