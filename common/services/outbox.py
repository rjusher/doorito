"""Outbox event emission and delivery services."""

import logging
import random
from datetime import timedelta

import httpx
from celery.exceptions import SoftTimeLimitExceeded
from django.db import transaction
from django.utils import timezone

from common.models import OutboxEvent
from common.utils import safe_dispatch

logger = logging.getLogger(__name__)

DELIVERY_BATCH_SIZE = 20
CLEANUP_BATCH_SIZE = 1000
WEBHOOK_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


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
    """Process pending outbox events via webhook delivery.

    Three-phase approach to avoid holding row locks during HTTP I/O:
    1. Fetch: lock and collect pending events
    2. Deliver: POST to matching webhook endpoints (no DB locks)
    3. Update: write delivery results back to the database

    Events with no matching active endpoints are marked DELIVERED.
    On delivery failure, events are retried with exponential backoff.
    Events exceeding max_attempts are marked FAILED.

    Args:
        batch_size: Maximum events to process per call.

    Returns:
        dict: {"processed": int, "delivered": int, "failed": int, "remaining": int}
    """
    from common.models import WebhookEndpoint

    now = timezone.now()

    # Phase 1: Fetch pending events (short transaction, releases locks)
    with transaction.atomic():
        events = list(
            OutboxEvent.objects.filter(
                status=OutboxEvent.Status.PENDING,
                next_attempt_at__lte=now,
            ).select_for_update(skip_locked=True)[:batch_size]
        )

    if not events:
        remaining = OutboxEvent.objects.filter(
            status=OutboxEvent.Status.PENDING,
        ).count()
        return {"processed": 0, "delivered": 0, "failed": 0, "remaining": remaining}

    # Load active endpoints once for the batch
    endpoints = list(WebhookEndpoint.objects.filter(is_active=True))

    # Phase 2: Deliver (no transaction, no locks)
    results = {}  # event.pk -> {"all_ok": bool, "error": str}
    try:
        with httpx.Client(timeout=WEBHOOK_TIMEOUT) as client:
            for event in events:
                matching = [
                    ep
                    for ep in endpoints
                    if not ep.event_types or event.event_type in ep.event_types
                ]

                if not matching:
                    # No matching endpoints — mark as delivered (no-op)
                    results[event.pk] = {"all_ok": True, "error": ""}
                    continue

                from common.services.webhook import deliver_to_endpoint

                errors = []
                for ep in matching:
                    result = deliver_to_endpoint(client, ep, event)
                    if not result["ok"]:
                        errors.append(f"{ep.url}: {result['error']}")

                results[event.pk] = {
                    "all_ok": len(errors) == 0,
                    "error": "; ".join(errors),
                }
    except SoftTimeLimitExceeded:
        logger.warning(
            "Soft time limit reached during webhook delivery, "
            "saving progress for %d/%d events.",
            len(results),
            len(events),
        )

    # Phase 3: Update event statuses (short transaction)
    delivered_count = 0
    failed_count = 0
    now = timezone.now()

    with transaction.atomic():
        for event in events:
            if event.pk not in results:
                # Not processed (soft time limit hit) — skip, will retry next sweep
                continue

            r = results[event.pk]
            event.attempts += 1

            if r["all_ok"]:
                event.status = OutboxEvent.Status.DELIVERED
                event.delivered_at = now
                event.next_attempt_at = None
                event.error_message = ""
                delivered_count += 1
            elif event.attempts >= event.max_attempts:
                event.status = OutboxEvent.Status.FAILED
                event.next_attempt_at = None
                event.error_message = r["error"]
                failed_count += 1
            else:
                # Retry with exponential backoff + jitter
                delay = min(60 * (2 ** (event.attempts - 1)), 3600)
                jitter = random.uniform(0, delay * 0.1)
                event.next_attempt_at = now + timedelta(seconds=delay + jitter)
                event.error_message = r["error"]

            event.save(
                update_fields=[
                    "status",
                    "attempts",
                    "delivered_at",
                    "next_attempt_at",
                    "error_message",
                    "updated_at",
                ]
            )

    remaining = OutboxEvent.objects.filter(
        status=OutboxEvent.Status.PENDING,
    ).count()

    return {
        "processed": len(results),
        "delivered": delivered_count,
        "failed": failed_count,
        "remaining": remaining,
    }


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
