"""Unit tests for outbox services."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.db import IntegrityError
from django.utils import timezone

from common.models import OutboxEvent
from common.services.outbox import (
    cleanup_delivered_events,
    emit_event,
    process_pending_events,
)


@pytest.mark.django_db
class TestEmitEvent:
    """Tests for emit_event() service function."""

    def test_creates_event_with_correct_fields(self):
        event = emit_event("User", "42", "user.created", {"email": "a@b.com"})
        assert event.aggregate_type == "User"
        assert event.aggregate_id == "42"
        assert event.event_type == "user.created"
        assert event.payload == {"email": "a@b.com"}
        assert event.status == OutboxEvent.Status.PENDING

    def test_auto_generates_idempotency_key(self):
        event = emit_event("User", "42", "user.created", {})
        assert event.idempotency_key == "User:42"

    def test_custom_idempotency_key_preserved(self):
        event = emit_event(
            "User",
            "42",
            "user.created",
            {},
            idempotency_key="custom-key-123",
        )
        assert event.idempotency_key == "custom-key-123"

    def test_none_payload_normalized_to_empty_dict(self):
        event = emit_event("User", "1", "user.none_payload", None)
        assert event.payload == {}

    def test_duplicate_raises_integrity_error(self):
        emit_event("User", "1", "user.created", {})
        with pytest.raises(IntegrityError):
            emit_event("User", "1", "user.created", {})

    def test_next_attempt_at_set_to_approximately_now(self):
        before = timezone.now()
        event = emit_event("User", "1", "user.timing", {})
        after = timezone.now()
        assert event.next_attempt_at is not None
        assert before <= event.next_attempt_at <= after

    def test_returned_event_status_is_pending(self):
        event = emit_event("User", "1", "user.status", {})
        assert event.status == OutboxEvent.Status.PENDING


@pytest.mark.django_db
class TestProcessPendingEvents:
    """Tests for process_pending_events() service function."""

    def test_marks_pending_events_as_delivered_no_endpoints(self, make_outbox_event):
        """Events with no matching endpoints are marked DELIVERED (no-op)."""
        event = make_outbox_event()
        result = process_pending_events()
        event.refresh_from_db()
        assert event.status == OutboxEvent.Status.DELIVERED
        assert event.delivered_at is not None
        assert event.next_attempt_at is None
        assert result["processed"] == 1
        assert result["delivered"] == 1

    def test_skips_events_with_future_next_attempt_at(self, make_outbox_event):
        make_outbox_event(
            next_attempt_at=timezone.now() + timedelta(hours=1),
        )
        result = process_pending_events()
        assert result["processed"] == 0

    def test_respects_batch_size(self, make_outbox_event):
        for i in range(5):
            make_outbox_event(
                aggregate_id=str(i),
                event_type=f"test.batch.{i}",
                idempotency_key=f"batch:{i}",
            )
        result = process_pending_events(batch_size=3)
        assert result["processed"] == 3
        assert result["remaining"] == 2

    def test_returns_correct_counts(self, make_outbox_event):
        make_outbox_event(event_type="test.count.1", idempotency_key="count:1")
        make_outbox_event(
            event_type="test.count.2",
            idempotency_key="count:2",
            aggregate_id="2",
        )
        result = process_pending_events()
        assert result["processed"] == 2
        assert result["delivered"] == 2
        assert result["failed"] == 0
        assert result["remaining"] == 0

    def test_noop_when_no_pending_events(self):
        result = process_pending_events()
        assert result == {"processed": 0, "delivered": 0, "failed": 0, "remaining": 0}

    def test_skips_delivered_events(self, make_outbox_event):
        make_outbox_event(status=OutboxEvent.Status.DELIVERED)
        result = process_pending_events()
        assert result["processed"] == 0

    def test_skips_failed_events(self, make_outbox_event):
        make_outbox_event(
            status=OutboxEvent.Status.FAILED,
            next_attempt_at=None,
        )
        result = process_pending_events()
        assert result["processed"] == 0

    @patch("common.services.webhook.deliver_to_endpoint")
    def test_delivers_to_matching_endpoints(
        self, mock_deliver, make_outbox_event, make_webhook_endpoint
    ):
        """Events are delivered to matching active endpoints."""
        make_webhook_endpoint(event_types=["test.created"])
        event = make_outbox_event()
        mock_deliver.return_value = {"ok": True, "status_code": 200, "error": ""}

        result = process_pending_events()

        assert mock_deliver.called
        event.refresh_from_db()
        assert event.status == OutboxEvent.Status.DELIVERED
        assert result["delivered"] == 1

    @patch("common.services.webhook.deliver_to_endpoint")
    def test_no_matching_endpoints_marks_delivered(
        self, mock_deliver, make_outbox_event, make_webhook_endpoint
    ):
        """Events with no matching endpoints are delivered without HTTP calls."""
        make_webhook_endpoint(event_types=["other.event"])
        event = make_outbox_event(event_type="test.created")

        result = process_pending_events()

        mock_deliver.assert_not_called()
        event.refresh_from_db()
        assert event.status == OutboxEvent.Status.DELIVERED
        assert result["delivered"] == 1

    @patch("common.services.webhook.deliver_to_endpoint")
    def test_failed_delivery_increments_attempts_and_sets_backoff(
        self, mock_deliver, make_outbox_event, make_webhook_endpoint
    ):
        """Failed delivery increments attempts and sets next_attempt_at."""
        make_webhook_endpoint(event_types=[])  # catch-all
        event = make_outbox_event()
        mock_deliver.return_value = {
            "ok": False,
            "status_code": 500,
            "error": "HTTP 500: error",
        }

        result = process_pending_events()

        event.refresh_from_db()
        assert event.status == OutboxEvent.Status.PENDING
        assert event.attempts == 1
        assert event.next_attempt_at is not None
        assert event.next_attempt_at > timezone.now()
        assert event.error_message == f"{event.error_message}"
        assert result["delivered"] == 0
        assert result["failed"] == 0  # Not failed yet, just retrying

    @patch("common.services.webhook.deliver_to_endpoint")
    def test_exceeds_max_attempts_transitions_to_failed(
        self, mock_deliver, make_outbox_event, make_webhook_endpoint
    ):
        """Events exceeding max_attempts transition to FAILED."""
        make_webhook_endpoint(event_types=[])  # catch-all
        event = make_outbox_event(attempts=4)  # max_attempts=5, next attempt is 5th
        mock_deliver.return_value = {
            "ok": False,
            "status_code": 500,
            "error": "HTTP 500: error",
        }

        result = process_pending_events()

        event.refresh_from_db()
        assert event.status == OutboxEvent.Status.FAILED
        assert event.attempts == 5
        assert event.next_attempt_at is None
        assert result["failed"] == 1

    @patch("common.services.webhook.deliver_to_endpoint")
    def test_error_message_populated_on_failure(
        self, mock_deliver, make_outbox_event, make_webhook_endpoint
    ):
        """Error message is set when delivery fails."""
        make_webhook_endpoint(event_types=[])
        event = make_outbox_event()
        mock_deliver.return_value = {
            "ok": False,
            "status_code": 503,
            "error": "HTTP 503: Service Unavailable",
        }

        process_pending_events()

        event.refresh_from_db()
        assert "HTTP 503" in event.error_message

    @patch("common.services.webhook.deliver_to_endpoint")
    def test_inactive_endpoints_excluded(
        self, mock_deliver, make_outbox_event, make_webhook_endpoint
    ):
        """Inactive endpoints are not delivered to."""
        make_webhook_endpoint(is_active=False, event_types=[])
        event = make_outbox_event()

        result = process_pending_events()

        mock_deliver.assert_not_called()
        event.refresh_from_db()
        assert event.status == OutboxEvent.Status.DELIVERED
        assert result["delivered"] == 1

    @patch("common.services.webhook.deliver_to_endpoint")
    def test_event_type_exact_match(
        self, mock_deliver, make_outbox_event, make_webhook_endpoint
    ):
        """Event type matching is exact match."""
        make_webhook_endpoint(event_types=["file.stored"])
        event = make_outbox_event(event_type="file.stored")
        mock_deliver.return_value = {"ok": True, "status_code": 200, "error": ""}

        process_pending_events()

        assert mock_deliver.called
        event.refresh_from_db()
        assert event.status == OutboxEvent.Status.DELIVERED

    @patch("common.services.webhook.deliver_to_endpoint")
    def test_empty_event_types_matches_all(
        self, mock_deliver, make_outbox_event, make_webhook_endpoint
    ):
        """Empty event_types list matches all event types (catch-all)."""
        make_webhook_endpoint(event_types=[])
        event = make_outbox_event(event_type="any.event.type")
        mock_deliver.return_value = {"ok": True, "status_code": 200, "error": ""}

        process_pending_events()

        assert mock_deliver.called
        event.refresh_from_db()
        assert event.status == OutboxEvent.Status.DELIVERED


@pytest.mark.django_db
class TestCleanupDeliveredEvents:
    """Tests for cleanup_delivered_events() service function."""

    def test_deletes_old_delivered_events(self, make_outbox_event):
        event = make_outbox_event(status=OutboxEvent.Status.DELIVERED)
        old_time = timezone.now() - timedelta(hours=200)
        OutboxEvent.objects.filter(pk=event.pk).update(created_at=old_time)

        result = cleanup_delivered_events(retention_hours=168)
        assert result["deleted"] == 1
        assert not OutboxEvent.objects.filter(pk=event.pk).exists()

    def test_deletes_old_failed_events(self, make_outbox_event):
        event = make_outbox_event(
            status=OutboxEvent.Status.FAILED,
            next_attempt_at=None,
        )
        old_time = timezone.now() - timedelta(hours=200)
        OutboxEvent.objects.filter(pk=event.pk).update(created_at=old_time)

        result = cleanup_delivered_events(retention_hours=168)
        assert result["deleted"] == 1

    def test_preserves_pending_events(self, make_outbox_event):
        event = make_outbox_event(status=OutboxEvent.Status.PENDING)
        old_time = timezone.now() - timedelta(hours=200)
        OutboxEvent.objects.filter(pk=event.pk).update(created_at=old_time)

        result = cleanup_delivered_events(retention_hours=168)
        assert result["deleted"] == 0
        assert OutboxEvent.objects.filter(pk=event.pk).exists()

    def test_preserves_young_events(self, make_outbox_event):
        make_outbox_event(status=OutboxEvent.Status.DELIVERED)
        result = cleanup_delivered_events(retention_hours=168)
        assert result["deleted"] == 0

    def test_respects_batch_limit(self, make_outbox_event):
        from common.services import outbox

        original = outbox.CLEANUP_BATCH_SIZE
        outbox.CLEANUP_BATCH_SIZE = 2

        try:
            for i in range(5):
                event = make_outbox_event(
                    event_type=f"test.cleanup.{i}",
                    idempotency_key=f"cleanup:{i}",
                    aggregate_id=str(i),
                    status=OutboxEvent.Status.DELIVERED,
                )
                old_time = timezone.now() - timedelta(hours=200)
                OutboxEvent.objects.filter(pk=event.pk).update(created_at=old_time)

            result = cleanup_delivered_events(retention_hours=168)
            assert result["deleted"] == 2
            assert result["remaining"] == 3
        finally:
            outbox.CLEANUP_BATCH_SIZE = original

    def test_returns_correct_counts(self, make_outbox_event):
        result = cleanup_delivered_events(retention_hours=168)
        assert result == {"deleted": 0, "remaining": 0}
