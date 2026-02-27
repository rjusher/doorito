"""Unit tests for OutboxEvent and WebhookEndpoint models."""

import uuid
from datetime import datetime
from decimal import Decimal

import pytest
from django.db import IntegrityError

from common.models import OutboxEvent, WebhookEndpoint


@pytest.mark.django_db
class TestOutboxEventCreation:
    """Verify OutboxEvent creation with default values."""

    def test_uuid7_primary_key(self, make_outbox_event):
        event = make_outbox_event()
        assert isinstance(event.pk, uuid.UUID)
        assert event.pk.version == 7

    def test_default_status_is_pending(self, make_outbox_event):
        event = make_outbox_event()
        assert event.status == OutboxEvent.Status.PENDING

    def test_default_attempts_is_zero(self, make_outbox_event):
        event = make_outbox_event()
        assert event.attempts == 0

    def test_default_max_attempts_is_five(self, make_outbox_event):
        event = make_outbox_event()
        assert event.max_attempts == 5

    def test_default_payload_is_empty_dict(self, db):
        event = OutboxEvent.objects.create(
            aggregate_type="Test",
            aggregate_id="1",
            event_type="test.default_payload",
            idempotency_key="test:default_payload",
        )
        assert event.payload == {}

    def test_timestamped_fields_auto_set(self, make_outbox_event):
        event = make_outbox_event()
        assert event.created_at is not None
        assert event.updated_at is not None


@pytest.mark.django_db
class TestOutboxEventConstraints:
    """Verify UniqueConstraint on (event_type, idempotency_key)."""

    def test_duplicate_event_type_and_idempotency_key_raises(self, make_outbox_event):
        make_outbox_event(event_type="user.created", idempotency_key="User:1")
        with pytest.raises(IntegrityError):
            make_outbox_event(event_type="user.created", idempotency_key="User:1")

    def test_same_idempotency_key_different_event_type_allowed(self, make_outbox_event):
        make_outbox_event(event_type="user.created", idempotency_key="User:1")
        event2 = make_outbox_event(event_type="user.updated", idempotency_key="User:1")
        assert event2.pk is not None


@pytest.mark.django_db
class TestOutboxEventStatusChoices:
    """Verify Status TextChoices values."""

    def test_status_values(self):
        assert set(OutboxEvent.Status.values) == {"pending", "delivered", "failed"}


@pytest.mark.django_db
class TestOutboxEventStr:
    """Verify __str__ representation."""

    def test_str_format(self, make_outbox_event):
        event = make_outbox_event(event_type="file.stored")
        assert str(event) == "file.stored (Pending)"

    def test_str_delivered(self, make_outbox_event):
        event = make_outbox_event(
            event_type="file.stored",
            status=OutboxEvent.Status.DELIVERED,
        )
        assert str(event) == "file.stored (Delivered)"


@pytest.mark.django_db
class TestOutboxEventPayload:
    """Verify DjangoJSONEncoder handles special types in payload."""

    def test_payload_with_uuid(self, make_outbox_event):
        test_uuid = uuid.uuid4()
        event = make_outbox_event(payload={"id": test_uuid})
        event.refresh_from_db()
        assert event.payload["id"] == str(test_uuid)

    def test_payload_with_decimal(self, make_outbox_event):
        event = make_outbox_event(payload={"price": Decimal("9.99")})
        event.refresh_from_db()
        assert event.payload["price"] == "9.99"

    def test_payload_with_datetime(self, make_outbox_event):
        now = datetime(2026, 1, 15, 12, 0, 0)
        event = make_outbox_event(payload={"timestamp": now})
        event.refresh_from_db()
        assert "2026-01-15" in event.payload["timestamp"]


@pytest.mark.django_db
class TestWebhookEndpoint:
    """Tests for WebhookEndpoint model."""

    def test_create_with_all_fields(self):
        endpoint = WebhookEndpoint.objects.create(
            url="https://example.com/webhook",
            secret="my-secret",
            event_types=["file.stored", "file.expiring"],
            is_active=True,
        )
        assert endpoint.pk is not None
        assert isinstance(endpoint.pk, uuid.UUID)
        assert endpoint.url == "https://example.com/webhook"
        assert endpoint.secret == "my-secret"
        assert endpoint.event_types == ["file.stored", "file.expiring"]
        assert endpoint.is_active is True

    def test_str_active(self):
        endpoint = WebhookEndpoint.objects.create(
            url="https://example.com/hook",
            secret="s",
            is_active=True,
        )
        assert str(endpoint) == "https://example.com/hook (active)"

    def test_str_inactive(self):
        endpoint = WebhookEndpoint.objects.create(
            url="https://example.com/hook",
            secret="s",
            is_active=False,
        )
        assert str(endpoint) == "https://example.com/hook (inactive)"

    def test_default_event_types_empty_list(self):
        endpoint = WebhookEndpoint.objects.create(
            url="https://example.com/hook",
            secret="s",
        )
        assert endpoint.event_types == []

    def test_default_is_active_true(self):
        endpoint = WebhookEndpoint.objects.create(
            url="https://example.com/hook",
            secret="s",
        )
        assert endpoint.is_active is True

    def test_timestamped_fields_auto_set(self):
        endpoint = WebhookEndpoint.objects.create(
            url="https://example.com/hook",
            secret="s",
        )
        assert endpoint.created_at is not None
        assert endpoint.updated_at is not None
