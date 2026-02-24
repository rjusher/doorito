"""Django AppConfig for the common app."""

from django.apps import AppConfig


class CommonConfig(AppConfig):
    """Configuration for the common app (shared utilities, base models, constants)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "common"
