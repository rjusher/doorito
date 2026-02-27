"""Shared fixtures for common app tests."""

import pytest
from django.utils import timezone

from common.models import OutboxEvent


@pytest.fixture
def make_outbox_event(db):
    """Factory fixture to create OutboxEvent instances."""

    def _make(
        aggregate_type="TestModel",
        aggregate_id="1",
        event_type="test.created",
        payload=None,
        status=OutboxEvent.Status.PENDING,
        idempotency_key=None,
        next_attempt_at=None,
        attempts=0,
    ):
        if payload is None:
            payload = {"key": "value"}
        if idempotency_key is None:
            idempotency_key = f"{aggregate_type}:{aggregate_id}"
        if next_attempt_at is None and status == OutboxEvent.Status.PENDING:
            next_attempt_at = timezone.now()
        return OutboxEvent.objects.create(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload,
            status=status,
            idempotency_key=idempotency_key,
            next_attempt_at=next_attempt_at,
            attempts=attempts,
        )

    return _make
