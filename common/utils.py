"""Shared utility functions used across all apps."""

import logging
import secrets
from contextlib import contextmanager

from django.utils import timezone


def generate_reference(prefix):
    """
    Generate a reference number in the format PREFIX-YYYYMMDD-XXXXXX.

    Args:
        prefix: Short identifier (e.g., "PR", "RMA", "ORD")

    Returns:
        String like "PR-20260217-A1B2C3"
    """
    date_part = timezone.now().strftime("%Y%m%d")
    random_part = secrets.token_hex(3).upper()
    return f"{prefix}-{date_part}-{random_part}"


def apply_date_range(queryset, date_from=None, date_to=None, field="created_at"):
    """
    Apply optional date-range filters to a queryset.

    Usage::

        qs = Return.objects.filter(store=store)
        qs = apply_date_range(qs, date_from, date_to)
    """
    if date_from:
        queryset = queryset.filter(**{f"{field}__gte": date_from})
    if date_to:
        queryset = queryset.filter(**{f"{field}__lte": date_to})
    return queryset


@contextmanager
def safe_dispatch(operation_name, logger=None):
    """
    Context manager for operations that should never raise.

    Use around notification dispatch, event emission, audit logging,
    and other side-effects that must not break the main operation.

    Usage::

        with safe_dispatch("send return notification", logger):
            notify(store=store, event_type="return_requested", ...)

        with safe_dispatch("emit return event", logger):
            emit(event_type="return.requested", store=store, ...)
    """
    _logger = logger or logging.getLogger("doorito.dispatch")
    try:
        yield
    except Exception as e:
        _logger.error("Failed to %s: %s", operation_name, e)
