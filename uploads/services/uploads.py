"""Ingest file services for file validation, creation, and consumption."""

import logging
import mimetypes

from django.conf import settings
from django.core.exceptions import ValidationError

from uploads.models import IngestFile

logger = logging.getLogger(__name__)


def validate_file(file, max_size=None):
    """Validate an uploaded file's size and MIME type.

    Args:
        file: A Django UploadedFile instance.
        max_size: Maximum file size in bytes. Defaults to
            ``settings.FILE_UPLOAD_MAX_SIZE`` (50 MB).

    Returns:
        A tuple of (mime_type, file_size).

    Raises:
        ValidationError: If the file exceeds the size limit or has a
            disallowed MIME type.
    """
    max_size = max_size or settings.FILE_UPLOAD_MAX_SIZE
    file_size = file.size

    if file_size > max_size:
        raise ValidationError(
            f"File size {file_size} bytes exceeds maximum "
            f"of {max_size} bytes.",
            code="file_too_large",
        )

    mime_type, _ = mimetypes.guess_type(file.name)
    if mime_type is None:
        mime_type = "application/octet-stream"

    allowed_types = settings.FILE_UPLOAD_ALLOWED_TYPES
    if allowed_types is not None and mime_type not in allowed_types:
        raise ValidationError(
            f"File type '{mime_type}' is not allowed. "
            f"Allowed types: {', '.join(allowed_types)}",
            code="file_type_not_allowed",
        )

    return mime_type, file_size


def create_ingest_file(user, file):
    """Validate and store an ingest file.

    Args:
        user: The User instance who owns this ingest file.
        file: A Django UploadedFile instance.

    Returns:
        An IngestFile instance with status READY (success) or FAILED
        (validation error).
    """
    try:
        mime_type, file_size = validate_file(file)
    except ValidationError as exc:
        upload = IngestFile.objects.create(
            user=user,
            file=file,
            original_filename=file.name,
            file_size=file.size,
            mime_type="unknown",
            status=IngestFile.Status.FAILED,
            error_message=str(exc.message),
        )
        logger.warning(
            "Ingest file failed validation for user %s: %s",
            user.pk,
            exc.message,
        )
        return upload

    upload = IngestFile.objects.create(
        user=user,
        file=file,
        original_filename=file.name,
        file_size=file_size,
        mime_type=mime_type,
        status=IngestFile.Status.READY,
    )
    logger.info(
        "Ingest file created: pk=%s user=%s file=%s size=%d",
        upload.pk,
        user.pk,
        file.name,
        file_size,
    )
    return upload


def consume_ingest_file(ingest_file):
    """Mark an ingest file as consumed by a downstream process.

    Uses an atomic UPDATE with a WHERE clause on status to prevent
    race conditions when multiple consumers attempt to consume the
    same ingest file simultaneously.

    Args:
        ingest_file: An IngestFile instance to consume.

    Returns:
        The updated IngestFile instance.

    Raises:
        ValueError: If the ingest file is not in READY status (already
            consumed, failed, or pending).
    """
    updated = IngestFile.objects.filter(
        pk=ingest_file.pk,
        status=IngestFile.Status.READY,
    ).update(status=IngestFile.Status.CONSUMED)

    if updated == 0:
        raise ValueError(
            f"Cannot consume ingest file {ingest_file.pk}: "
            f"status is '{ingest_file.status}', expected 'ready'."
        )

    ingest_file.refresh_from_db()
    logger.info("Ingest file consumed: pk=%s", ingest_file.pk)
    return ingest_file
