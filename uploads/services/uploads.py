"""Upload handling services for file validation, creation, and consumption."""

import logging
import mimetypes

from django.conf import settings
from django.core.exceptions import ValidationError

from uploads.models import FileUpload

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


def create_upload(user, file):
    """Validate and store a file upload.

    Args:
        user: The User instance who owns this upload.
        file: A Django UploadedFile instance.

    Returns:
        A FileUpload instance with status READY (success) or FAILED
        (validation error).
    """
    try:
        mime_type, file_size = validate_file(file)
    except ValidationError as exc:
        upload = FileUpload.objects.create(
            user=user,
            file=file,
            original_filename=file.name,
            file_size=file.size,
            mime_type="unknown",
            status=FileUpload.Status.FAILED,
            error_message=str(exc.message),
        )
        logger.warning(
            "Upload failed validation for user %s: %s",
            user.pk,
            exc.message,
        )
        return upload

    upload = FileUpload.objects.create(
        user=user,
        file=file,
        original_filename=file.name,
        file_size=file_size,
        mime_type=mime_type,
        status=FileUpload.Status.READY,
    )
    logger.info(
        "Upload created: pk=%s user=%s file=%s size=%d",
        upload.pk,
        user.pk,
        file.name,
        file_size,
    )
    return upload


def consume_upload(file_upload):
    """Mark an upload as consumed by a downstream process.

    Uses an atomic UPDATE with a WHERE clause on status to prevent
    race conditions when multiple consumers attempt to consume the
    same upload simultaneously.

    Args:
        file_upload: A FileUpload instance to consume.

    Returns:
        The updated FileUpload instance.

    Raises:
        ValueError: If the upload is not in READY status (already
            consumed, failed, or pending).
    """
    updated = FileUpload.objects.filter(
        pk=file_upload.pk,
        status=FileUpload.Status.READY,
    ).update(status=FileUpload.Status.CONSUMED)

    if updated == 0:
        raise ValueError(
            f"Cannot consume upload {file_upload.pk}: "
            f"status is '{file_upload.status}', expected 'ready'."
        )

    file_upload.refresh_from_db()
    logger.info("Upload consumed: pk=%s", file_upload.pk)
    return file_upload
