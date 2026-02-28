"""Portal data models for batched, chunked file uploads and event outbox."""

from common.models import TimeStampedModel
from common.utils import uuid7
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models


class UploadBatch(TimeStampedModel):
    """Groups multiple uploaded files into a single logical batch."""

    class Status(models.TextChoices):
        INIT = "init", "Init"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETE = "complete", "Complete"
        PARTIAL = "partial", "Partial"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="upload_batches",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.INIT,
    )
    idempotency_key = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
    )

    class Meta:
        db_table = "portal_upload_batch"
        verbose_name = "upload batch"
        verbose_name_plural = "upload batches"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Batch {self.pk} ({self.get_status_display()})"


class UploadFile(TimeStampedModel):
    """Canonical file record for uploaded files.

    Status lifecycle:
        uploading → stored
        uploading → failed
    """

    class Status(models.TextChoices):
        UPLOADING = "uploading", "Uploading"
        STORED = "stored", "Stored"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    batch = models.ForeignKey(
        "UploadBatch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="files",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="upload_files",
    )
    file = models.FileField(upload_to="uploads/%Y/%m/")
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    size_bytes = models.PositiveBigIntegerField(help_text="File size in bytes")
    sha256 = models.CharField(max_length=64, blank=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.UPLOADING,
    )
    error_message = models.TextField(blank=True)

    class Meta:
        db_table = "portal_upload_file"
        verbose_name = "upload file"
        verbose_name_plural = "upload files"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["uploaded_by", "-created_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.original_filename} ({self.get_status_display()})"


class UploadSession(TimeStampedModel):
    """Tracks a chunked upload session for a single file.

    Status lifecycle:
        init → in_progress → complete / failed / aborted
    """

    class Status(models.TextChoices):
        INIT = "init", "Init"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETE = "complete", "Complete"
        FAILED = "failed", "Failed"
        ABORTED = "aborted", "Aborted"

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    file = models.OneToOneField(
        "UploadFile",
        on_delete=models.CASCADE,
        related_name="session",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.INIT,
    )
    chunk_size_bytes = models.PositiveIntegerField(
        default=5_242_880,
        help_text="Target chunk size in bytes (default 5 MB)",
    )
    total_size_bytes = models.PositiveBigIntegerField(
        help_text="Total expected file size in bytes",
    )
    total_parts = models.PositiveIntegerField(
        help_text="Total expected number of parts",
    )
    bytes_received = models.PositiveBigIntegerField(default=0)
    completed_parts = models.PositiveIntegerField(default=0)
    idempotency_key = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
    )
    upload_token = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
    )

    class Meta:
        db_table = "portal_upload_session"
        verbose_name = "upload session"
        verbose_name_plural = "upload sessions"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Session {self.pk} ({self.get_status_display()})"


class UploadPart(TimeStampedModel):
    """Tracks an individual chunk within an upload session."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RECEIVED = "received", "Received"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    session = models.ForeignKey(
        "UploadSession",
        on_delete=models.CASCADE,
        related_name="parts",
    )
    part_number = models.PositiveIntegerField(
        help_text="1-indexed chunk ordinal",
    )
    offset_bytes = models.PositiveBigIntegerField(
        help_text="Byte offset of this part",
    )
    size_bytes = models.PositiveBigIntegerField(
        help_text="Size of this part in bytes",
    )
    sha256 = models.CharField(max_length=64, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    temp_storage_key = models.CharField(
        max_length=500,
        blank=True,
        help_text="Temporary storage location for chunk before assembly",
    )

    class Meta:
        db_table = "portal_upload_part"
        verbose_name = "upload part"
        verbose_name_plural = "upload parts"
        ordering = ["part_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "part_number"],
                name="unique_session_part_number",
            ),
        ]

    def __str__(self):
        return f"Part {self.part_number} of session {self.session_id}"


class PortalEventOutbox(TimeStampedModel):
    """Durable event queue for portal domain events.

    Uses the generic aggregate_type/aggregate_id pattern (not FK-bound)
    to support file, batch, and session-level events.

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
        db_table = "portal_event_outbox"
        verbose_name = "portal event outbox"
        verbose_name_plural = "portal event outbox entries"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["next_attempt_at"],
                condition=models.Q(status="pending"),
                name="idx_portal_outbox_pending_next",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["event_type", "idempotency_key"],
                name="unique_portal_event_type_idempotency_key",
            ),
        ]

    def __str__(self):
        return f"{self.event_type} ({self.get_status_display()})"
