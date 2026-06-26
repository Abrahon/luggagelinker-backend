from django.db import models

# Create your models here.
import uuid

from django.db import models
from django.contrib.auth.models import AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from apps.accounts.managers import UserManager

from apps.accounts.managers import UserManager
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