from django.db import models

# Create your models here.
import uuid

from django.db import models
from django.contrib.auth.models import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from apps.accounts.managers import UserManager
from datetime import timedelta

from django.db import models
from django.utils import timezone

from shared.constants.roles import UserRole


class User(AbstractBaseUser, PermissionsMixin):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    email = models.EmailField(
        unique=True
    )

    role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.SENDER
    )

    is_active = models.BooleanField(default=True)

    is_staff = models.BooleanField(default=False)

    is_verified = models.BooleanField(default=False)

    date_joined = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"

    REQUIRED_FIELDS = []

    class Meta:
        db_table = "users"

    def __str__(self):
        return self.email




# otp model
class OTP(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_expired(self):
        return timezone.now() > self.created_at + timedelta(minutes=5)

    def __str__(self):
        if self.user:
            return f"{self.code} ({self.user.email})"
        return f"{self.code} ({self.email})"

    class Meta:
        db_table = "otp"
        ordering = ["-created_at"]