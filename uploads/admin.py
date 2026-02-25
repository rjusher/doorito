"""Admin configuration for ingest files."""

from django.contrib import admin

from uploads.models import IngestFile


@admin.register(IngestFile)
class IngestFileAdmin(admin.ModelAdmin):
    """Admin interface for inspecting and managing ingest files."""

    list_display = (
        "original_filename",
        "user",
        "file_size",
        "mime_type",
        "status",
        "created_at",
    )
    list_filter = ("status", "mime_type", "created_at")
    search_fields = ("original_filename", "user__email", "user__username")
    readonly_fields = (
        "file_size",
        "mime_type",
        "status",
        "error_message",
        "created_at",
        "updated_at",
    )
    list_select_related = ("user",)
    date_hierarchy = "created_at"
