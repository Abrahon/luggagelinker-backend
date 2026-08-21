from django.db import models


class NegotiationStatus(models.TextChoices):

    ACTIVE = "ACTIVE", "Active"

    ACCEPTED = "ACCEPTED", "Accepted"

    REJECTED = "REJECTED", "Rejected"

    EXPIRED = "EXPIRED", "Expired"

    CANCELLED = "CANCELLED", "Cancelled"


class OfferStatus(models.TextChoices):

    PENDING = "PENDING", "Pending"

    ACCEPTED = "ACCEPTED", "Accepted"

    REJECTED = "REJECTED", "Rejected"

    COUNTERED = "COUNTERED", "Countered"

    CANCELLED = "CANCELLED", "Cancelled"