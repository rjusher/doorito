"""Upload services for file validation, creation, and status transitions."""

import contextlib
import hashlib
import logging
import mimetypes
from datetime import timedelta

from common.services.outbox import emit_event
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from uploads.models import UploadBatch, UploadFile

logger = logging.getLogger(__name__)


def validate_file(file, max_size=None):
    """Validate an uploaded file's size and MIME type.

    Args:
        file: A Django UploadedFile instance.
        max_size: Maximum file size in bytes. Defaults to
            ``settings.FILE_UPLOAD_MAX_SIZE`` (50 MB).

    Returns:
        A tuple of (content_type, size_bytes).

    Raises:
        ValidationError: If the file exceeds the size limit or has a
            disallowed MIME type.
    """
    max_size = max_size or settings.FILE_UPLOAD_MAX_SIZE
    size_bytes = file.size

    if size_bytes > max_size:
        raise ValidationError(
            f"File size {size_bytes} bytes exceeds maximum of {max_size} bytes.",
            code="file_too_large",
        )

    content_type, _ = mimetypes.guess_type(file.name)
    if content_type is None:
        content_type = "application/octet-stream"

    allowed_types = settings.FILE_UPLOAD_ALLOWED_TYPES
    if allowed_types is not None and content_type not in allowed_types:
        raise ValidationError(
            f"File type '{content_type}' is not allowed. "
            f"Allowed types: {', '.join(allowed_types)}",
            code="file_type_not_allowed",
        )

    return content_type, size_bytes


def compute_sha256(file):
    """Compute SHA-256 hash of a file.

    Reads the file in 64 KB chunks. Seeks back to the start after hashing
    so the file can be saved by Django's FileField afterward.

    Args:
        file: A Django UploadedFile instance.

    Returns:
        Hex-encoded SHA-256 hash string (64 characters).
    """
    hasher = hashlib.sha256()
    file.seek(0)
    for chunk in file.chunks(chunk_size=65_536):
        hasher.update(chunk)
    file.seek(0)
    return hasher.hexdigest()


def create_upload_file(user, file, batch=None):
    """Validate, hash, and store an upload file.

    Args:
        user: The User instance who uploaded the file (or None).
        file: A Django UploadedFile instance.
        batch: Optional UploadBatch to associate with.

    Returns:
        An UploadFile instance with status STORED (success) or FAILED
        (validation error).
    """
    try:
        content_type, size_bytes = validate_file(file)
    except ValidationError as exc:
        upload = UploadFile.objects.create(
            uploaded_by=user,
            file=file,
            original_filename=file.name,
            content_type="unknown",
            size_bytes=file.size,
            batch=batch,
            status=UploadFile.Status.FAILED,
            error_message=str(exc.message),
        )
        logger.warning(
            "Upload file failed validation: pk=%s user=%s error=%s",
            upload.pk,
            user.pk if user else None,
            exc.message,
        )
        return upload

    sha256 = compute_sha256(file)

    with transaction.atomic():
        upload = UploadFile.objects.create(
            uploaded_by=user,
            file=file,
            original_filename=file.name,
            content_type=content_type,
            size_bytes=size_bytes,
            sha256=sha256,
            batch=batch,
            status=UploadFile.Status.STORED,
        )
        emit_event(
            aggregate_type="UploadFile",
            aggregate_id=str(upload.pk),
            event_type="file.stored",
            payload={
                "file_id": str(upload.pk),
                "original_filename": upload.original_filename,
                "content_type": upload.content_type,
                "size_bytes": upload.size_bytes,
                "sha256": upload.sha256,
                "url": upload.file.url,
            },
        )
    logger.info(
        "Upload file created: pk=%s user=%s file=%s size=%d sha256=%s",
        upload.pk,
        user.pk if user else None,
        file.name,
        size_bytes,
        sha256[:16],
    )
    return upload


def mark_file_processed(upload_file):
    """Transition an upload file from STORED to PROCESSED.

    Uses an atomic UPDATE with a WHERE clause on status to prevent
    race conditions.

    Args:
        upload_file: An UploadFile instance.

    Returns:
        The updated UploadFile instance.

    Raises:
        ValueError: If the file is not in STORED status.
    """
    updated = UploadFile.objects.filter(
        pk=upload_file.pk,
        status=UploadFile.Status.STORED,
    ).update(status=UploadFile.Status.PROCESSED)

    if updated == 0:
        raise ValueError(
            f"Cannot mark upload file {upload_file.pk} as processed: "
            f"status is '{upload_file.status}', expected 'stored'."
        )

    upload_file.refresh_from_db()
    logger.info("Upload file processed: pk=%s", upload_file.pk)
    return upload_file


def mark_file_failed(upload_file, error=""):
    """Transition an upload file to FAILED status.

    Args:
        upload_file: An UploadFile instance.
        error: Error message describing the failure.

    Returns:
        The updated UploadFile instance.
    """
    upload_file.status = UploadFile.Status.FAILED
    upload_file.error_message = error
    upload_file.save(update_fields=["status", "error_message", "updated_at"])
    logger.warning("Upload file failed: pk=%s error=%s", upload_file.pk, error)
    return upload_file


def mark_file_deleted(upload_file):
    """Transition an upload file to DELETED status and remove the physical file.

    Args:
        upload_file: An UploadFile instance.

    Returns:
        The updated UploadFile instance.
    """
    with contextlib.suppress(FileNotFoundError):
        upload_file.file.delete(save=False)

    upload_file.status = UploadFile.Status.DELETED
    upload_file.save(update_fields=["status", "updated_at"])
    logger.info("Upload file deleted: pk=%s", upload_file.pk)
    return upload_file


def create_batch(user, idempotency_key=""):
    """Create a new upload batch.

    Args:
        user: The User instance creating the batch (or None).
        idempotency_key: Optional client-provided key to prevent
            duplicate batch creation.

    Returns:
        An UploadBatch instance.
    """
    batch = UploadBatch.objects.create(
        created_by=user,
        idempotency_key=idempotency_key,
    )
    logger.info(
        "Upload batch created: pk=%s user=%s",
        batch.pk,
        user.pk if user else None,
    )
    return batch


@transaction.atomic
def finalize_batch(batch):
    """Finalize a batch based on its files' statuses.

    Transitions batch to:
    - COMPLETE: all files are STORED or PROCESSED
    - PARTIAL: some files are STORED/PROCESSED, some FAILED
    - FAILED: all files are FAILED (or no files)

    Args:
        batch: An UploadBatch instance.

    Returns:
        The updated UploadBatch instance.
    """
    file_statuses = list(batch.files.values_list("status", flat=True))

    if not file_statuses:
        batch.status = UploadBatch.Status.FAILED
    else:
        success_statuses = {UploadFile.Status.STORED, UploadFile.Status.PROCESSED}
        successes = sum(1 for s in file_statuses if s in success_statuses)
        failures = sum(1 for s in file_statuses if s == UploadFile.Status.FAILED)

        if failures == 0:
            batch.status = UploadBatch.Status.COMPLETE
        elif successes == 0:
            batch.status = UploadBatch.Status.FAILED
        else:
            batch.status = UploadBatch.Status.PARTIAL

    batch.save(update_fields=["status", "updated_at"])
    logger.info("Upload batch finalized: pk=%s status=%s", batch.pk, batch.status)
    return batch


def notify_expiring_files(ttl_hours=None, notify_hours=None):
    """Emit file.expiring events for files approaching TTL expiry.

    Queries files with status=STORED that are within notify_hours of
    their TTL expiry. Relies on the outbox idempotency constraint
    to prevent duplicate notifications across sweep runs.

    Args:
        ttl_hours: File TTL in hours. Defaults to settings.FILE_UPLOAD_TTL_HOURS.
        notify_hours: Hours before expiry to notify. Defaults to
            settings.FILE_UPLOAD_EXPIRY_NOTIFY_HOURS.

    Returns:
        dict: {"notified": int, "skipped": int}
    """
    if ttl_hours is None:
        ttl_hours = settings.FILE_UPLOAD_TTL_HOURS
    if notify_hours is None:
        notify_hours = getattr(settings, "FILE_UPLOAD_EXPIRY_NOTIFY_HOURS", 1)

    cutoff = timezone.now() - timedelta(hours=ttl_hours - notify_hours)
    expiring_qs = UploadFile.objects.filter(
        status=UploadFile.Status.STORED,
        created_at__lt=cutoff,
    )

    notified = 0
    skipped = 0
    for upload in expiring_qs.iterator():
        try:
            with transaction.atomic():
                emit_event(
                    aggregate_type="UploadFile",
                    aggregate_id=str(upload.pk),
                    event_type="file.expiring",
                    payload={
                        "file_id": str(upload.pk),
                        "original_filename": upload.original_filename,
                        "content_type": upload.content_type,
                        "size_bytes": upload.size_bytes,
                        "sha256": upload.sha256,
                        "url": upload.file.url,
                        "expires_at": str(
                            upload.created_at + timedelta(hours=ttl_hours)
                        ),
                    },
                )
            notified += 1
        except IntegrityError:
            skipped += 1  # Already notified (idempotency constraint)

    logger.info(
        "Expiring file notifications: %d notified, %d skipped (already notified).",
        notified,
        skipped,
    )
    return {"notified": notified, "skipped": skipped}
