"""Shared abstract base models used across all apps."""

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from common.utils import uuid7


class TimeStampedModel(models.Model):
    """Abstract base providing consistent created_at/updated_at timestamps."""

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="created at")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="updated at")

    class Meta:
        abstract = True


class OutboxEvent(TimeStampedModel):
    """Transactional outbox event for reliable at-least-once delivery.

    Status lifecycle:
        pending → delivered (success)
        pending → ... retry ... → failed (max retries exhausted)
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        DELIVERED = "delivered", "Delivered"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    aggregate_type = models.CharField(max_length=100)
    aggregate_id = models.CharField(max_length=100)
    event_type = models.CharField(max_length=100)
    payload = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    idempotency_key = models.CharField(max_length=255)
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=5)
    next_attempt_at = models.DateTimeField(null=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        db_table = "outbox_event"
        verbose_name = "outbox event"
        verbose_name_plural = "outbox events"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["next_attempt_at"],
                condition=models.Q(status="pending"),
                name="idx_outbox_pending_next",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["event_type", "idempotency_key"],
                name="unique_event_type_idempotency_key",
            ),
        ]

    def __str__(self):
        return f"{self.event_type} ({self.get_status_display()})"


class WebhookEndpoint(TimeStampedModel):
    """Configured webhook destination for outbox event delivery.

    Events are delivered via HTTP POST to active endpoints whose
    event_types match the event's event_type. An empty event_types
    list matches all events (catch-all).
    """

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    url = models.URLField(max_length=2048, help_text="Target URL to POST events to")
    secret = models.CharField(
        max_length=255,
        help_text="Shared secret for HMAC-SHA256 request signing",
    )
    event_types = models.JSONField(
        default=list,
        blank=True,
        encoder=DjangoJSONEncoder,
        help_text=(
            'JSON list of event types to subscribe to (e.g., ["file.stored"]). '
            "Empty list matches all events."
        ),
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Enable or disable delivery to this endpoint",
    )

    class Meta:
        db_table = "webhook_endpoint"
        verbose_name = "webhook endpoint"
        verbose_name_plural = "webhook endpoints"
        ordering = ["-created_at"]

    def __str__(self):
        status = "active" if self.is_active else "inactive"
        return f"{self.url} ({status})"
