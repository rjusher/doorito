"""Celery tasks for the common app."""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name="common.tasks.deliver_outbox_events_task",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def deliver_outbox_events_task(self):
    """Deliver pending outbox events.

    Processes at most DELIVERY_BATCH_SIZE (100) pending events per run.
    Called on-demand via transaction.on_commit() and periodically via
    celery-beat as a safety net.

    Returns:
        dict: {"processed": int, "remaining": int}
    """
    from common.services.outbox import process_pending_events

    result = process_pending_events()
    if result["processed"] > 0:
        logger.info(
            "Processed %d outbox events: %d delivered, %d failed, %d remaining.",
            result["processed"],
            result["delivered"],
            result["failed"],
            result["remaining"],
        )
    return result


@shared_task(
    name="common.tasks.cleanup_delivered_outbox_events_task",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def cleanup_delivered_outbox_events_task(self):
    """Delete terminal outbox events older than OUTBOX_RETENTION_HOURS.

    Processes at most CLEANUP_BATCH_SIZE (1000) events per run.

    Returns:
        dict: {"deleted": int, "remaining": int}
    """
    from django.conf import settings

    from common.services.outbox import cleanup_delivered_events

    retention_hours = getattr(settings, "OUTBOX_RETENTION_HOURS", 168)
    result = cleanup_delivered_events(retention_hours=retention_hours)
    if result["deleted"] > 0:
        logger.info(
            "Cleaned up %d terminal outbox events, %d remaining.",
            result["deleted"],
            result["remaining"],
        )
    return result
