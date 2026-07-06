from django.db import models

# Create your models here.
import uuid

from cloudinary.models import CloudinaryField
from django.db import models

from apps.accounts.models import User


class GenderChoices(models.TextChoices):
    MALE = "male", "Male"
    FEMALE = "female", "Female"
    OTHER = "other", "Other"



class Profile(models.Model):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile",
    )

    profile_picture = CloudinaryField(
        "profile_picture",
        blank=True,
        null=True,
    )

    first_name = models.CharField(
        max_length=100,
        blank=True,
    )

    last_name = models.CharField(
        max_length=100,
        blank=True,
    )

    phone = models.CharField(
        max_length=20,
        blank=True,
    )

    date_of_birth = models.DateField(
        null=True,
        blank=True,
    )

    gender = models.CharField(
        max_length=30,
        choices=GenderChoices.choices,
        blank=True,
    )

    bio = models.TextField(
        blank=True,
    )

    country = models.CharField(
        max_length=100,
        blank=True,
    )
    total_reviews = models.PositiveIntegerField(
    default=0,
    help_text="Total number of reviews received by this traveler.",
    )

    total_rating = models.PositiveIntegerField(
        default=0,
        help_text="Sum of all received ratings.",
    )

    average_rating = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=0.00,
        help_text="Average traveler rating.",
    )
    completed_deliveries = models.PositiveIntegerField(default=0)

    cancelled_deliveries = models.PositiveIntegerField(default=0)


    city = models.CharField(
        max_length=100,
        blank=True,
    )

    address = models.TextField(
        blank=True,
    )

    postal_code = models.CharField(
        max_length=20,
        blank=True,
    )

    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )

    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = "profiles"
        ordering = ["-created_at"]

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self):
        return self.full_name or self.user.email