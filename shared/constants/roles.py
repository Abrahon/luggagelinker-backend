from django.db import models


class UserRole(models.TextChoices):
    ADMIN = "ADMIN", "Admin"
    SENDER = "SENDER", "Sender"
    TRAVELER = "TRAVELER", "Traveler"