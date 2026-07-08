# ==============================================================================
# ENUMS / TEXT CHOICES
# ==============================================================================

import uuid
from django.db import models  
from django.conf import settings


class DisputeHistoryAction(models.TextChoices):
    """System-level actions captured chronologically within the immutable audit trail."""
    CREATED = "CREATED", "Dispute Case Initialized"
    ASSIGNED = "ASSIGNED", "Moderator Assigned"
    EVIDENCE_ADDED = "EVIDENCE_ADDED", "User Evidence Uploaded"
    EVIDENCE_REQUESTED = "EVIDENCE_REQUESTED", "Information Requested by Admin"
    RESOLVED_REFUND = "RESOLVED_REFUND", "Case Resolved via Full Refund"
    RESOLVED_RELEASE = "RESOLVED_RELEASE", "Case Resolved via Escrow Release"
    RESOLVED_PARTIAL = "RESOLVED_PARTIAL", "Case Resolved via Partial Split"
    REJECTED = "REJECTED", "Case Dismissed/Rejected"
    CLOSED = "CLOSED", "Case Permanently Closed"


class DisputeStatus(models.TextChoices):
    """Tracks the operational state machine lifecycle of a dispute ticket."""
    OPEN = "OPEN", "Open"
    UNDER_REVIEW = "UNDER_REVIEW", "Under Review"
    WAITING_FOR_USER = "WAITING_FOR_USER", "Waiting for User"
    RESOLVED = "RESOLVED", "Resolved"
    REJECTED = "REJECTED", "Rejected"
    CLOSED = "CLOSED", "Closed"