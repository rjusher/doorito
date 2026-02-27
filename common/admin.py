"""Admin configuration for common app models."""

from django.contrib import admin
from django.utils import timezone

from common.models import OutboxEvent, WebhookEndpoint


@admin.register(OutboxEvent)
class OutboxEventAdmin(admin.ModelAdmin):
    """Admin interface for outbox events."""

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
    search_fields = ("event_type", "aggregate_type", "aggregate_id", "idempotency_key")
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
    actions = ["retry_failed_events"]

    @admin.action(description="Retry selected failed events")
    def retry_failed_events(self, request, queryset):
        """Reset failed events to pending for retry."""
        updated = queryset.filter(status=OutboxEvent.Status.FAILED).update(
            status=OutboxEvent.Status.PENDING,
            next_attempt_at=timezone.now(),
            error_message="",
            attempts=0,
        )
        self.message_user(request, f"{updated} event(s) reset for retry.")


@admin.register(WebhookEndpoint)
class WebhookEndpointAdmin(admin.ModelAdmin):
    """Admin interface for webhook endpoint configuration."""

    list_display = ("url", "is_active", "event_types", "created_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("url",)
    readonly_fields = ("pk", "created_at", "updated_at")
    date_hierarchy = "created_at"
