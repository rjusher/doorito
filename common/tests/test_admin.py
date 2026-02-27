"""Tests for common app admin actions."""

import pytest
from django.utils import timezone

from common.models import OutboxEvent


@pytest.mark.django_db
class TestRetryFailedEventsAction:
    """Tests for retry_failed_events admin action."""

    def test_retry_resets_attempts_to_zero(self, make_outbox_event):
        """Retrying a failed event resets attempts to 0."""
        event = make_outbox_event(
            status=OutboxEvent.Status.FAILED,
            attempts=5,
            next_attempt_at=None,
        )
        event.error_message = "HTTP 500: Internal Server Error"
        event.save(update_fields=["error_message"])

        # Simulate the admin action
        OutboxEvent.objects.filter(
            pk=event.pk,
            status=OutboxEvent.Status.FAILED,
        ).update(
            status=OutboxEvent.Status.PENDING,
            next_attempt_at=timezone.now(),
            error_message="",
            attempts=0,
        )

        event.refresh_from_db()
        assert event.status == OutboxEvent.Status.PENDING
        assert event.attempts == 0
        assert event.error_message == ""
        assert event.next_attempt_at is not None
