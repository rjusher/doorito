"""Unit tests for common app Celery tasks."""

from datetime import timedelta

import pytest
from django.utils import timezone

from common.models import OutboxEvent
from common.tasks import (
    cleanup_delivered_outbox_events_task,
    deliver_outbox_events_task,
)


@pytest.mark.django_db
class TestDeliverOutboxEventsTask:
    """Tests for deliver_outbox_events_task."""

    def test_processes_pending_events(self, make_outbox_event):
        event = make_outbox_event()
        result = deliver_outbox_events_task()
        assert result["processed"] == 1
        event.refresh_from_db()
        assert event.status == OutboxEvent.Status.DELIVERED

    def test_noop_when_no_pending_events(self):
        result = deliver_outbox_events_task()
        assert result == {"processed": 0, "delivered": 0, "failed": 0, "remaining": 0}

    def test_returns_result_dict(self, make_outbox_event):
        make_outbox_event()
        result = deliver_outbox_events_task()
        assert "processed" in result
        assert "delivered" in result
        assert "failed" in result
        assert "remaining" in result


@pytest.mark.django_db
class TestCleanupDeliveredOutboxEventsTask:
    """Tests for cleanup_delivered_outbox_events_task."""

    def test_deletes_old_terminal_events(self, make_outbox_event):
        event = make_outbox_event(status=OutboxEvent.Status.DELIVERED)
        old_time = timezone.now() - timedelta(hours=200)
        OutboxEvent.objects.filter(pk=event.pk).update(created_at=old_time)

        result = cleanup_delivered_outbox_events_task()
        assert result["deleted"] == 1

    def test_noop_when_no_terminal_events(self):
        result = cleanup_delivered_outbox_events_task()
        assert result == {"deleted": 0, "remaining": 0}

    def test_reads_retention_from_settings(self, make_outbox_event, settings):
        settings.OUTBOX_RETENTION_HOURS = 1
        event = make_outbox_event(status=OutboxEvent.Status.DELIVERED)
        old_time = timezone.now() - timedelta(hours=2)
        OutboxEvent.objects.filter(pk=event.pk).update(created_at=old_time)

        result = cleanup_delivered_outbox_events_task()
        assert result["deleted"] == 1
