# Service Layer Reference

Doorito uses a service layer pattern to encapsulate business logic outside of models and views.

## Design Principles

1. **Models are data containers** -- they define fields, relationships, and simple computed properties.
2. **Services contain business logic** -- validation, multi-model coordination, side effects.
3. **Views/Admin call services** -- never perform complex logic directly.
4. **CLI commands delegate to services** -- all Click commands should call service functions.
5. **Tasks call services** -- Celery tasks should be thin wrappers around service calls.

## Convention

Services live in `{app}/services/` directories:

```
{app}/
└── services/
    ├── __init__.py
    └── {domain}.py    # One module per domain concern
```

Service functions are plain Python functions (not classes):

```python
# Example service function
def create_widget(store, name, price, created_by=None):
    """Create a new widget with validation."""
    # Business logic here
    return widget
```

## Current State

Two apps have service modules:
- `common/services/outbox.py` -- Outbox event emission, delivery, and cleanup
- `common/services/webhook.py` -- Webhook HTTP delivery and HMAC signing
- `uploads/services/uploads.py` -- File validation, creation, and status transitions; batch management; pre-expiry notifications
- `uploads/services/sessions.py` -- Chunked upload session lifecycle management

When adding services to a new app, follow the same pattern:

1. Create `{app}/services/__init__.py`
2. Create `{app}/services/{domain}.py` with the service functions
3. Import and call from views, admin, CLI, and tasks

---

## Common App

### common/services/outbox.py

Outbox event emission and delivery services. Contains 3 functions. Constants: `DELIVERY_BATCH_SIZE = 20`, `CLEANUP_BATCH_SIZE = 1000`, `WEBHOOK_TIMEOUT = httpx.Timeout(30.0, connect=10.0)`.

**`emit_event(aggregate_type, aggregate_id, event_type, payload, *, idempotency_key=None)`**
Create an outbox event and schedule delivery. Writes the `OutboxEvent` row and registers `deliver_outbox_events_task.delay()` via `transaction.on_commit()` (wrapped in `safe_dispatch()` for eager-mode safety). Auto-generates `idempotency_key` as `f"{aggregate_type}:{aggregate_id}"` when None. Sets `next_attempt_at=timezone.now()`. Returns the created `OutboxEvent` (status=PENDING).

**Transactional usage pattern:** Callers should wrap both the state change and `emit_event()` in the same `transaction.atomic()` block:
```python
with transaction.atomic():
    obj = create_something(...)
    emit_event("Something", str(obj.pk), "something.created", {...})
```

**`process_pending_events(batch_size=20)`**
Process pending outbox events via webhook delivery. Uses a three-phase approach to avoid holding row locks during HTTP I/O:

1. **Phase 1 (Fetch):** `transaction.atomic()` + `select_for_update(skip_locked=True)` to lock and collect up to `batch_size` pending events where `next_attempt_at <= now`. Also loads all active `WebhookEndpoint` records once for the batch.
2. **Phase 2 (Deliver):** Outside any transaction — creates a shared `httpx.Client(timeout=WEBHOOK_TIMEOUT)` and for each event finds matching endpoints (exact event_type match; empty `event_types` list = catch-all). Calls `deliver_to_endpoint()` from `common/services/webhook.py` for each match. Events with no matching active endpoints get `all_ok=True`. Handles `SoftTimeLimitExceeded` to save progress and exit gracefully.
3. **Phase 3 (Update):** `transaction.atomic()` — increments `attempts`, marks DELIVERED (all endpoints succeeded), FAILED (`attempts >= max_attempts`), or retries with exponential backoff (`min(60 * 2^(attempts-1), 3600)` + 10% jitter).

Returns `{"processed": int, "delivered": int, "failed": int, "remaining": int}`.

**`cleanup_delivered_events(retention_hours=168)`**
Delete terminal outbox events (DELIVERED and FAILED) older than `retention_hours` (default 168 = 7 days). Batch-limited to 1000 per run. Returns `{"deleted": int, "remaining": int}`.

### common/services/webhook.py

Webhook HTTP delivery and HMAC-SHA256 signing. Contains 2 functions. Used by `process_pending_events()` in `common/services/outbox.py`.

**`compute_signature(payload_bytes, secret)`**
Compute HMAC-SHA256 signature for webhook payload. Uses `hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()`. Returns hex-encoded signature string.

**`deliver_to_endpoint(client, endpoint, event)`**
Deliver an outbox event to a single webhook endpoint. Serializes `event.payload` to JSON bytes, computes HMAC signature, POSTs to `endpoint.url` with headers: `Content-Type: application/json`, `X-Webhook-Signature: {signature}`, `X-Webhook-Event: {event.event_type}`, `X-Webhook-Delivery: {event.pk}`. Returns `{"ok": bool, "status_code": int|None, "error": str}`. Handles `httpx.HTTPStatusError` (4xx/5xx) and `httpx.RequestError` (network errors/timeouts).

---

## Uploads App

### uploads/services/uploads.py

Upload handling services for file validation, creation, status transitions, batch management, and pre-expiry notifications. Contains 9 functions.

**`validate_file(file, max_size=None)`**
Validate an uploaded file's size and MIME type. Returns `(content_type, size_bytes)` tuple. Raises `ValidationError` with code `file_too_large` or `file_type_not_allowed`. Uses `mimetypes.guess_type()` for MIME detection (extension-based, falls back to `application/octet-stream`). Checks against `settings.FILE_UPLOAD_MAX_SIZE` (default 50 MB) and `settings.FILE_UPLOAD_ALLOWED_TYPES` (`None` = accept all).

**`compute_sha256(file)`**
Compute SHA-256 hash of a file. Reads in 64 KB chunks. Seeks to start before and after hashing so the file can be saved by Django's `FileField` afterward. Returns hex-encoded hash string (64 characters).

**`create_upload_file(user, file, batch=None)`**
Validate, hash, and store an upload file. Returns an `UploadFile` instance with `status=STORED` (success, with `sha256` computed) or `status=FAILED` (validation error with `error_message` populated). Optionally associates the file with an `UploadBatch`. On success, emits a `file.stored` outbox event (via `emit_event()`) wrapped in `transaction.atomic()` alongside the `UploadFile.objects.create()` call. The event payload includes: `file_id`, `original_filename`, `content_type`, `size_bytes`, `sha256`, and `url` (the file's storage URL — local path in Dev, S3 URL in Production). Failed uploads do not emit events.

**`mark_file_processed(upload_file)`**
Transition an upload file from STORED to PROCESSED. Uses atomic `filter(pk=..., status=STORED).update(status=PROCESSED)` to prevent race conditions. Raises `ValueError` if the upload file is not in STORED status. Returns the refreshed `UploadFile` instance.

**`mark_file_failed(upload_file, error="")`**
Transition an upload file to FAILED status with an error message. Saves via `update_fields` for efficiency. Returns the updated `UploadFile` instance.

**`mark_file_deleted(upload_file)`**
Transition an upload file to DELETED status and remove the physical file via `file.delete(save=False)`. Handles `FileNotFoundError` gracefully. Returns the updated `UploadFile` instance.

**`create_batch(user, idempotency_key="")`**
Create a new upload batch with INIT status. Returns an `UploadBatch` instance.

**`finalize_batch(batch)`**
Finalize a batch based on its files' statuses. Uses `@transaction.atomic`. Transitions to: COMPLETE (all files STORED/PROCESSED), PARTIAL (some succeeded, some failed), or FAILED (all failed or no files). Returns the updated `UploadBatch` instance.

**`notify_expiring_files(ttl_hours=None, notify_hours=None)`**
Emit `file.expiring` outbox events for files approaching TTL expiry. Queries `UploadFile.objects.filter(status=STORED, created_at__lt=cutoff)` where `cutoff = now - timedelta(hours=ttl_hours - notify_hours)`. Iterates with `.iterator()` for memory efficiency. Per file: `transaction.atomic()` + `emit_event(event_type="file.expiring")` with payload including `file_id`, `original_filename`, `content_type`, `size_bytes`, `sha256`, `url`, `expires_at`. Catches `IntegrityError` per file for idempotency (outbox unique constraint prevents duplicate notifications). Defaults from `settings.FILE_UPLOAD_TTL_HOURS` and `settings.FILE_UPLOAD_EXPIRY_NOTIFY_HOURS`. Returns `{"notified": int, "skipped": int}`.

---

### uploads/services/sessions.py

Chunked upload session lifecycle management. Contains 3 functions.

**`create_upload_session(upload_file, total_size_bytes, chunk_size_bytes=None)`**
Create an upload session for chunked file upload. Calculates `total_parts` via `math.ceil(total_size_bytes / chunk_size_bytes)`. Default chunk size is 5 MB. Returns an `UploadSession` instance.

**`record_upload_part(session, part_number, offset_bytes, size_bytes, sha256="")`**
Record a received chunk within an upload session. Creates an `UploadPart` with RECEIVED status. Uses `F()` expressions for atomic counter updates on the session (`completed_parts`, `bytes_received`) and transitions session to IN_PROGRESS. Returns an `UploadPart` instance.

**`complete_upload_session(session)`**
Complete an upload session after all parts are received. Uses `@transaction.atomic`. Validates that received part count matches `total_parts`. Transitions session to COMPLETE and the associated `UploadFile` from UPLOADING to STORED. Raises `ValueError` if not all parts have been received. Returns the updated `UploadSession` instance.
