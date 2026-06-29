import uuid

from django.db import models


class Plan(models.Model):
    """
    Subscription Plan
    Created & managed by Admin.
    """

    BILLING_MONTHLY = "monthly"
    BILLING_YEARLY = "yearly"

    BILLING_CHOICES = (
        (BILLING_MONTHLY, "Monthly"),
        (BILLING_YEARLY, "Yearly"),
    )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    name = models.CharField(
        max_length=100,
        unique=True,
    )

    slug = models.SlugField(
        max_length=100,
        unique=True,
    )

    description = models.TextField(
        blank=True,
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
    )

    currency = models.CharField(
        max_length=10,
        default="USD",
    )

    billing_cycle = models.CharField(
        max_length=20,
        choices=BILLING_CHOICES,
        default=BILLING_MONTHLY,
    )

    duration_days = models.PositiveIntegerField(
        help_text="Subscription duration in days.",
    )

    trial_days = models.PositiveIntegerField(
        default=0,
        help_text="Free trial duration in days.",
    )

    badge = models.CharField(
        max_length=50,
        blank=True,
        help_text="Example: Most Popular, Best Value",
    )

    is_popular = models.BooleanField(
        default=False,
    )

    is_public = models.BooleanField(
        default=True,
        help_text="Hide plan from frontend without deleting.",
    )

    is_active = models.BooleanField(
        default=True,
    )

    sort_order = models.PositiveIntegerField(
        default=0,
    )

    # ----------------------------------
    # PLAN FEATURES
    # ----------------------------------

    features = models.JSONField(
        default=dict,
        blank=True,
        help_text="Stores plan permissions and limits.",
    )

    # ----------------------------------
    # PAYMENT GATEWAY IDS
    # ----------------------------------

    stripe_product_id = models.CharField(
        max_length=255,
        blank=True,
    )

    stripe_price_id = models.CharField(
        max_length=255,
        blank=True,
    )

    # ----------------------------------
    # TIMESTAMPS
    # ----------------------------------

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = "plans"
        ordering = ["sort_order", "price"]
        verbose_name = "Plan"
        verbose_name_plural = "Plans"

    def __str__(self):
        return f"{self.name} ({self.billing_cycle})"