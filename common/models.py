"""Shared abstract base models used across all apps."""

from django.db import models


class TimeStampedModel(models.Model):
    """Abstract base providing consistent created_at/updated_at timestamps."""

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="created at")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="updated at")

    class Meta:
        abstract = True
