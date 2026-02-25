"""Celery tasks for the uploads app."""

import logging
from datetime import timedelta

from django.utils import timezone

from celery import shared_task

logger = logging.getLogger(__name__)

BATCH_SIZE = 1000


@shared_task(
    name="uploads.tasks.cleanup_expired_ingest_files_task",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def cleanup_expired_ingest_files_task(self):
    """Delete ingest files older than FILE_UPLOAD_TTL_HOURS.

    Processes at most BATCH_SIZE (1000) expired records per run to
    stay within CELERY_TASK_TIME_LIMIT (300s). Logs the remaining
    count for operational visibility.

    Returns:
        dict: {"deleted": int, "remaining": int}
    """
    from django.conf import settings

    from uploads.models import IngestFile

    ttl_hours = getattr(settings, "FILE_UPLOAD_TTL_HOURS", 24)
    cutoff = timezone.now() - timedelta(hours=ttl_hours)
    expired_qs = IngestFile.objects.filter(created_at__lt=cutoff)
    total_expired = expired_qs.count()

    if total_expired == 0:
        logger.info("No expired ingest files to clean up.")
        return {"deleted": 0, "remaining": 0}

    batch_pks = list(
        expired_qs.order_by("pk").values_list("pk", flat=True)[:BATCH_SIZE]
    )
    batch = IngestFile.objects.filter(pk__in=batch_pks)

    deleted_files = 0
    for upload in batch.iterator():
        try:
            upload.file.delete(save=False)
            deleted_files += 1
        except FileNotFoundError:
            deleted_files += 1  # File already gone, still count it

    deleted_count, _ = batch.delete()
    remaining = max(0, total_expired - deleted_count)

    logger.info(
        "Cleaned up %d expired ingest files (%d files removed), "
        "%d remaining.",
        deleted_count,
        deleted_files,
        remaining,
    )
    return {"deleted": deleted_count, "remaining": remaining}
