"""Unit tests for outbox services."""

from datetime import timedelta

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

    def test_marks_pending_events_as_delivered(self, make_outbox_event):
        event = make_outbox_event()
        result = process_pending_events()
        event.refresh_from_db()
        assert event.status == OutboxEvent.Status.DELIVERED
        assert event.delivered_at is not None
        assert event.next_attempt_at is None
        assert result["processed"] == 1

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
        assert result["remaining"] == 0

    def test_noop_when_no_pending_events(self):
        result = process_pending_events()
        assert result == {"processed": 0, "remaining": 0}

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
