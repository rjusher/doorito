# Admin Interface Reference

The Django admin interface is minimal in the Doorito skeleton. It serves as a superuser/developer tool.

## Registered Admin Classes

### accounts/admin.py

```python
@admin.register(User)
class UserAdmin(BaseUserAdmin):
    pass
```

The only accounts admin class. Uses Django's built-in `UserAdmin` with no customizations.

## Access

- **URL**: `/admin/`
- **Auth**: Django's built-in superuser/staff authentication
- **Models visible**: User, OutboxEvent, UploadBatch, UploadFile, UploadSession, UploadPart

### common/admin.py

One admin class registered for the outbox event model:

```python
@admin.register(OutboxEvent)
class OutboxEventAdmin(admin.ModelAdmin):
    list_display = ("event_type", "aggregate_type", "aggregate_id", "status", "attempts", "next_attempt_at", "created_at")
    list_filter = ("status", "event_type", "aggregate_type", "created_at")
    search_fields = ("event_type", "aggregate_type", "aggregate_id", "idempotency_key")
    readonly_fields = ("pk", "aggregate_type", "aggregate_id", "event_type", "payload", "idempotency_key", "attempts", "delivered_at", "error_message", "created_at", "updated_at")
    date_hierarchy = "created_at"
    actions = ["retry_failed_events"]
```

**Custom action:** `retry_failed_events` -- resets selected FAILED events to PENDING with `next_attempt_at=now()` and clears `error_message`, making them eligible for the next delivery sweep.

### uploads/admin.py

Four admin classes registered for the upload models:

```python
@admin.register(UploadBatch)
class UploadBatchAdmin(admin.ModelAdmin):
    list_display = ("pk", "created_by", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("pk", "idempotency_key", "created_by__email")
    readonly_fields = ("pk", "created_at", "updated_at")
    list_select_related = ("created_by",)
    date_hierarchy = "created_at"
```

```python
@admin.register(UploadFile)
class UploadFileAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "uploaded_by", "content_type", "size_bytes", "status", "created_at")
    list_filter = ("status", "content_type", "created_at")
    search_fields = ("original_filename", "sha256", "uploaded_by__email")
    readonly_fields = ("pk", "size_bytes", "content_type", "sha256", "status", "error_message", "created_at", "updated_at")
    list_select_related = ("uploaded_by", "batch")
    date_hierarchy = "created_at"
```

```python
@admin.register(UploadSession)
class UploadSessionAdmin(admin.ModelAdmin):
    list_display = ("pk", "file", "status", "completed_parts", "total_parts", "bytes_received", "total_size_bytes", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("pk", "idempotency_key", "upload_token")
    readonly_fields = ("pk", "bytes_received", "completed_parts", "created_at", "updated_at")
    list_select_related = ("file",)
    date_hierarchy = "created_at"
```

```python
@admin.register(UploadPart)
class UploadPartAdmin(admin.ModelAdmin):
    list_display = ("pk", "session", "part_number", "size_bytes", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("pk", "session__pk")
    readonly_fields = ("pk", "created_at", "updated_at")
    list_select_related = ("session",)
```

All upload admin classes use `list_select_related` to prevent N+1 queries. `date_hierarchy` provides date-based navigation for upload history (except `UploadPart` which is ordered by `part_number`). Computed/auto fields are read-only to prevent manual override.

## Conventions

When adding new admin classes:

- Use `list_select_related` to optimize database queries
- Use `list_filter` and `search_fields` for navigation
- Keep admin classes in their respective app's `admin.py` file
