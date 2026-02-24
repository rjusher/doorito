"""Shared custom model fields used across all apps."""

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models


class MoneyField(models.DecimalField):
    """DecimalField pre-configured for monetary values (12,2 with non-negative default)."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_digits", 12)
        kwargs.setdefault("decimal_places", 2)
        kwargs.setdefault("default", Decimal("0.00"))
        if "validators" not in kwargs:
            kwargs["validators"] = [MinValueValidator(Decimal("0.00"))]
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        # Report as plain DecimalField so Django doesn't generate migrations
        # when MoneyField is introduced on existing fields.
        path = "django.db.models.DecimalField"
        return name, path, args, kwargs
