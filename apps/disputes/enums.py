# ==============================================================================
# ENUMS / TEXT CHOICES
# ==============================================================================

from django.db import models


# ==============================================================================
# DISPUTE HISTORY ACTIONS
# ==============================================================================

class DisputeHistoryAction(models.TextChoices):
    """System-level actions recorded in the immutable audit trail."""

    CREATED = "CREATED", "Dispute Case Initialized"
    ASSIGNED = "ASSIGNED", "Moderator Assigned"
    EVIDENCE_ADDED = "EVIDENCE_ADDED", "User Evidence Uploaded"
    EVIDENCE_REQUESTED = "EVIDENCE_REQUESTED", "Information Requested by Admin"

    RESOLVED_REFUND = "RESOLVED_REFUND", "Resolved - Full Refund"
    RESOLVED_RELEASE = "RESOLVED_RELEASE", "Resolved - Escrow Released"
    RESOLVED_PARTIAL = "RESOLVED_PARTIAL", "Resolved - Partial Refund"

    REJECTED = "REJECTED", "Rejected"
    CLOSED = "CLOSED", "Closed"


# ==============================================================================
# DISPUTE STATUS
# ==============================================================================

class DisputeStatus(models.TextChoices):
    """Current workflow state of a dispute."""

    OPEN = "OPEN", "Open"
    UNDER_REVIEW = "UNDER_REVIEW", "Under Review"
    WAITING_FOR_USER = "WAITING_FOR_USER", "Waiting for User"
    RESOLVED = "RESOLVED", "Resolved"
    REJECTED = "REJECTED", "Rejected"
    CLOSED = "CLOSED", "Closed"


# ==============================================================================
# DISPUTE REASONS
# ==============================================================================

class DisputeReason(models.TextChoices):
    """Reason selected when opening a dispute."""

    DAMAGED_CARGO = "DAMAGED_CARGO", "Items Damaged Upon Delivery"
    MISSING_ITEMS = "MISSING_ITEMS", "Items Missing From Shipment"
    NO_SHOW = "NO_SHOW", "Traveler Failed to Meet/Deliver"
    DELAYED_DELIVERY = "DELAYED_DELIVERY", "Unacceptable Delivery Delay"
    OTHER = "OTHER", "Other Policy Violation"


# ==============================================================================
# DISPUTE RESOLUTION TYPES
# ==============================================================================

class ResolutionType(models.TextChoices):
    """Final resolution applied by an administrator."""

    REFUND = "REFUND", "Refund Sender"
    RELEASE_ESCROW = "RELEASE_ESCROW", "Release Escrow"
    PARTIAL_REFUND = "PARTIAL_REFUND", "Partial Refund"
    NO_ACTION = "NO_ACTION", "No Action"