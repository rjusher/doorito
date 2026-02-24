"""User model for Doorito."""

from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Custom User model. Extends AbstractUser for future customization."""

    class Meta:
        db_table = "user"
        verbose_name = "user"
        verbose_name_plural = "users"

    def __str__(self):
        return self.email or self.username
