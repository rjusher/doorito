"""Outbox event emission and delivery services."""

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from common.models import OutboxEvent
from common.utils import safe_dispatch

logger = logging.getLogger(__name__)

DELIVERY_BATCH_SIZE = 100
CLEANUP_BATCH_SIZE = 1000


def emit_event(
    aggregate_type, aggregate_id, event_type, payload, *, idempotency_key=None
):
    """Create an outbox event and schedule delivery.

    The event is written to the database as part of the current transaction.
    Delivery is dispatched via transaction.on_commit() to ensure the event
    is committed before the delivery task runs.

    For transactional consistency, callers should wrap both the state change
    and this call in the same transaction.atomic() block:

        with transaction.atomic():
            obj = create_something(...)
            emit_event("Something", str(obj.pk), "something.created", {...})

    Args:
        aggregate_type: Model name (e.g., "UploadFile", "User").
        aggregate_id: String PK of the source record.
        event_type: Dotted event name (e.g., "file.stored").
        payload: Dict of event data (serialized via DjangoJSONEncoder).
        idempotency_key: Deduplication key. Defaults to
            "{aggregate_type}:{aggregate_id}".

    Returns:
        The created OutboxEvent instance (status=PENDING). Note that the
        on_commit delivery dispatch has not fired yet at return time; it
        fires after the outermost transaction commits.
    """
    idempotency_key = idempotency_key or f"{aggregate_type}:{aggregate_id}"
    payload = payload if payload is not None else {}

    event = OutboxEvent.objects.create(
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=payload,
        idempotency_key=idempotency_key,
        next_attempt_at=timezone.now(),
    )

    def _dispatch():
        with safe_dispatch("dispatch outbox delivery", logger):
            from common.tasks import deliver_outbox_events_task

            deliver_outbox_events_task.delay()

    transaction.on_commit(_dispatch)

    logger.info(
        "Outbox event emitted: pk=%s type=%s aggregate=%s:%s",
        event.pk,
        event_type,
        aggregate_type,
        aggregate_id,
    )
    return event


def process_pending_events(batch_size=DELIVERY_BATCH_SIZE):
    """Process pending outbox events.

    Queries events with status=PENDING and next_attempt_at <= now(),
    locks them with select_for_update(skip_locked=True) for concurrency
    safety, and marks them as DELIVERED.

    Note: Handlers are deferred to consumer PEPs. This implementation
    marks events as delivered without calling any handler.

    Args:
        batch_size: Maximum number of events to process per call.

    Returns:
        dict: {"processed": int, "remaining": int}
    """
    now = timezone.now()

    with transaction.atomic():
        events = list(
            OutboxEvent.objects.filter(
                status=OutboxEvent.Status.PENDING,
                next_attempt_at__lte=now,
            ).select_for_update(skip_locked=True)[:batch_size]
        )

        for event in events:
            event.status = OutboxEvent.Status.DELIVERED
            event.delivered_at = now
            event.next_attempt_at = None
            event.save(
                update_fields=[
                    "status",
                    "delivered_at",
                    "next_attempt_at",
                    "updated_at",
                ]
            )

    remaining = OutboxEvent.objects.filter(
        status=OutboxEvent.Status.PENDING,
    ).count()

    return {"processed": len(events), "remaining": remaining}


def cleanup_delivered_events(retention_hours=168):
    """Delete terminal outbox events older than the retention period.

    Targets events with status DELIVERED or FAILED that are older
    than retention_hours.

    Args:
        retention_hours: Hours to retain terminal events (default 168 = 7 days).

    Returns:
        dict: {"deleted": int, "remaining": int}
    """
    cutoff = timezone.now() - timedelta(hours=retention_hours)
    terminal_qs = OutboxEvent.objects.filter(
        status__in=[OutboxEvent.Status.DELIVERED, OutboxEvent.Status.FAILED],
        created_at__lt=cutoff,
    )
    total_terminal = terminal_qs.count()

    if total_terminal == 0:
        return {"deleted": 0, "remaining": 0}

    batch_pks = list(
        terminal_qs.order_by("pk").values_list("pk", flat=True)[:CLEANUP_BATCH_SIZE]
    )
    deleted_count, _ = OutboxEvent.objects.filter(pk__in=batch_pks).delete()
    remaining = max(0, total_terminal - deleted_count)

    logger.info(
        "Cleaned up %d terminal outbox events, %d remaining.",
        deleted_count,
        remaining,
    )
    return {"deleted": deleted_count, "remaining": remaining}
