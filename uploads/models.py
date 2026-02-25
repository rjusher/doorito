"""File upload model for temporary file storage."""

from common.models import TimeStampedModel
from django.conf import settings
from django.db import models


class FileUpload(TimeStampedModel):
    """Temporary file upload with lifecycle tracking.

    Files are validated on upload and stored locally. A downstream process
    consumes the file, after which it can be cleaned up. The cleanup task
    deletes expired uploads automatically.

    Status lifecycle:
        pending → ready → consumed
        pending → failed (validation error)

    The ``pending`` status is reserved for future async validation
    (e.g., virus scanning). Currently, create_upload transitions
    directly to ``ready`` or ``failed``.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        READY = "ready", "Ready"
        CONSUMED = "consumed", "Consumed"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="uploads",
    )
    file = models.FileField(upload_to="uploads/%Y/%m/")
    original_filename = models.CharField(max_length=255)
    file_size = models.PositiveBigIntegerField(help_text="File size in bytes")
    mime_type = models.CharField(max_length=100)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    error_message = models.TextField(blank=True)

    class Meta:
        db_table = "file_upload"
        verbose_name = "file upload"
        verbose_name_plural = "file uploads"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.original_filename} ({self.get_status_display()})"
