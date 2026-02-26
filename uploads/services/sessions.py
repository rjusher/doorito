"""Upload session services for chunked upload lifecycle management."""

import logging
import math

from django.db import models, transaction

from uploads.models import UploadFile, UploadPart, UploadSession

logger = logging.getLogger(__name__)


def create_upload_session(upload_file, total_size_bytes, chunk_size_bytes=None):
    """Create an upload session for chunked file upload.

    Args:
        upload_file: An UploadFile instance to associate the session with.
        total_size_bytes: Total expected file size in bytes.
        chunk_size_bytes: Target chunk size in bytes. Defaults to 5 MB.

    Returns:
        An UploadSession instance.
    """
    if chunk_size_bytes is None:
        chunk_size_bytes = 5_242_880  # 5 MB

    total_parts = math.ceil(total_size_bytes / chunk_size_bytes)

    session = UploadSession.objects.create(
        file=upload_file,
        total_size_bytes=total_size_bytes,
        chunk_size_bytes=chunk_size_bytes,
        total_parts=total_parts,
    )
    logger.info(
        "Upload session created: pk=%s file=%s parts=%d",
        session.pk,
        upload_file.pk,
        total_parts,
    )
    return session


def record_upload_part(session, part_number, offset_bytes, size_bytes, sha256=""):
    """Record a received chunk within an upload session.

    Args:
        session: An UploadSession instance.
        part_number: 1-indexed chunk ordinal.
        offset_bytes: Byte offset of this part in the file.
        size_bytes: Size of this part in bytes.
        sha256: Optional SHA-256 hash of the chunk.

    Returns:
        An UploadPart instance with status RECEIVED.
    """
    part = UploadPart.objects.create(
        session=session,
        part_number=part_number,
        offset_bytes=offset_bytes,
        size_bytes=size_bytes,
        sha256=sha256,
        status=UploadPart.Status.RECEIVED,
    )

    # Update session progress counters
    UploadSession.objects.filter(pk=session.pk).update(
        completed_parts=models.F("completed_parts") + 1,
        bytes_received=models.F("bytes_received") + size_bytes,
        status=UploadSession.Status.IN_PROGRESS,
    )

    logger.info(
        "Upload part recorded: session=%s part=%d size=%d",
        session.pk,
        part_number,
        size_bytes,
    )
    return part


@transaction.atomic
def complete_upload_session(session):
    """Complete an upload session after all parts are received.

    Validates that all expected parts have been received, then
    transitions the session to COMPLETE.

    Args:
        session: An UploadSession instance.

    Returns:
        The updated UploadSession instance.

    Raises:
        ValueError: If not all parts have been received.
    """
    session.refresh_from_db()
    received_count = session.parts.filter(
        status=UploadPart.Status.RECEIVED,
    ).count()

    if received_count < session.total_parts:
        raise ValueError(
            f"Cannot complete session {session.pk}: "
            f"received {received_count} of {session.total_parts} parts."
        )

    session.status = UploadSession.Status.COMPLETE
    session.save(update_fields=["status", "updated_at"])

    # Transition the associated file to STORED
    UploadFile.objects.filter(
        pk=session.file_id,
        status=UploadFile.Status.UPLOADING,
    ).update(status=UploadFile.Status.STORED)

    logger.info("Upload session completed: pk=%s", session.pk)
    return session
