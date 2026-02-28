"""Admin configuration for portal models."""

from django.contrib import admin

from portal.models import (
    PortalEventOutbox,
    UploadBatch,
    UploadFile,
    UploadPart,
    UploadSession,
)


@admin.register(UploadBatch)
class UploadBatchAdmin(admin.ModelAdmin):
    """Admin interface for upload batches."""

    list_display = ("pk", "created_by", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("pk", "idempotency_key", "created_by__email")
    readonly_fields = ("pk", "created_at", "updated_at")
    list_select_related = ("created_by",)
    date_hierarchy = "created_at"


@admin.register(UploadFile)
class UploadFileAdmin(admin.ModelAdmin):
    """Admin interface for upload files."""

    list_display = (
        "original_filename",
        "uploaded_by",
        "content_type",
        "size_bytes",
        "status",
        "created_at",
    )
    list_filter = ("status", "content_type", "created_at")
    search_fields = ("original_filename", "sha256", "uploaded_by__email")
    readonly_fields = (
        "pk",
        "size_bytes",
        "content_type",
        "sha256",
        "status",
        "error_message",
        "created_at",
        "updated_at",
    )
    list_select_related = ("uploaded_by", "batch")
    date_hierarchy = "created_at"


@admin.register(UploadSession)
class UploadSessionAdmin(admin.ModelAdmin):
    """Admin interface for upload sessions."""

    list_display = (
        "pk",
        "file",
        "status",
        "completed_parts",
        "total_parts",
        "bytes_received",
        "total_size_bytes",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("pk", "idempotency_key", "upload_token")
    readonly_fields = (
        "pk",
        "bytes_received",
        "completed_parts",
        "created_at",
        "updated_at",
    )
    list_select_related = ("file",)
    date_hierarchy = "created_at"


@admin.register(UploadPart)
class UploadPartAdmin(admin.ModelAdmin):
    """Admin interface for upload parts."""

    list_display = (
        "pk",
        "session",
        "part_number",
        "size_bytes",
        "status",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = ("pk", "session__pk")
    readonly_fields = ("pk", "created_at", "updated_at")
    list_select_related = ("session",)


@admin.register(PortalEventOutbox)
class PortalEventOutboxAdmin(admin.ModelAdmin):
    """Admin interface for portal event outbox."""

    list_display = (
        "event_type",
        "aggregate_type",
        "aggregate_id",
        "status",
        "attempts",
        "next_attempt_at",
        "created_at",
    )
    list_filter = ("status", "event_type", "aggregate_type", "created_at")
    search_fields = (
        "event_type",
        "aggregate_type",
        "aggregate_id",
        "idempotency_key",
    )
    readonly_fields = (
        "pk",
        "aggregate_type",
        "aggregate_id",
        "event_type",
        "payload",
        "idempotency_key",
        "attempts",
        "delivered_at",
        "error_message",
        "created_at",
        "updated_at",
    )
    date_hierarchy = "created_at"
