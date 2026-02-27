# PEP 0007: File Portal Pipeline — Research

| Field | Value |
|-------|-------|
| **PEP** | 0007 |
| **Summary** | [summary.md](summary.md) |
| **Plan** | [plan.md](plan.md) |

---

## Current State Analysis

### Upload Infrastructure (Exists, No Entry Point)

The uploads app (`uploads/`) provides a complete data model and service layer for file uploads, but has **no views, no URL routes, and no templates**. The models and services were built by PEP 0003 but no consumer PEP has wired them to the frontend.

**Models** (`uploads/models.py`):
- `UploadBatch` — groups files into a logical batch, tracks batch-level status (INIT → IN_PROGRESS → COMPLETE/PARTIAL/FAILED)
- `UploadFile` — canonical file record with FileField, content type, SHA-256 hash, status lifecycle (UPLOADING → STORED → PROCESSED/DELETED or UPLOADING → FAILED)
- `UploadSession` / `UploadPart` — chunked upload tracking (1:1 with UploadFile, parts tracked per session). These are infrastructure for future presigned-URL chunked uploads; the simple single-request upload flow does not use them.

**Services** (`uploads/services/uploads.py`):
- `validate_file(file, max_size=None)` — validates size and MIME type against `FILE_UPLOAD_MAX_SIZE` and `FILE_UPLOAD_ALLOWED_TYPES` settings
- `compute_sha256(file)` — reads file in 64 KB chunks, seeks back after hashing
- `create_upload_file(user, file, batch=None)` — validates, hashes, stores, returns UploadFile with status STORED or FAILED
- `create_batch(user, idempotency_key="")` — creates an UploadBatch with INIT status
- `finalize_batch(batch)` — transitions batch status based on file statuses
- `mark_file_processed/failed/deleted` — status transition helpers

**Key observation**: `create_upload_file` does NOT currently emit any outbox event. PEP 0006 (not yet implemented) plans to add `file.stored` event emission in this function. PEP 0007 depends on PEP 0006 for this.

### Outbox Event System (Events Created, No Real Delivery)

The outbox pattern is fully wired (PEP 0004) but the delivery function is a no-op placeholder.

**`process_pending_events()`** (`common/services/outbox.py`, lines 77-120):
- Queries events with `status=PENDING` and `next_attempt_at <= now()`
- Locks with `select_for_update(skip_locked=True)` for concurrency safety
- **Immediately marks events as DELIVERED** without any HTTP delivery — line 104: `event.status = OutboxEvent.Status.DELIVERED`
- No retry logic is exercised because there are no failures (everything succeeds trivially)
- The `attempts`, `max_attempts`, and `error_message` fields on `OutboxEvent` exist but are never incremented/populated by `process_pending_events()`

**`OutboxEvent` model** (`common/models.py`, lines 19-67):
- Has `attempts` (default 0), `max_attempts` (default 5), `next_attempt_at`, `error_message` fields — all ready for retry logic
- Status choices: PENDING → DELIVERED (success) or PENDING → ... → FAILED (max retries)
- Partial index `idx_outbox_pending_next` on `next_attempt_at` WHERE `status='pending'` — optimized for the delivery poll query
- Unique constraint on `(event_type, idempotency_key)` — prevents duplicate events

**`deliver_outbox_events_task`** (`common/tasks.py`, lines 10-35):
- Called on-demand via `transaction.on_commit()` and periodically via celery-beat (every 5 min sweep)
- Thin wrapper around `process_pending_events()`

### TTL Cleanup (Runs Without Notification)

**`cleanup_expired_upload_files_task`** (`uploads/tasks.py`, lines 15-66):
- Deletes `UploadFile` records older than `FILE_UPLOAD_TTL_HOURS` (default 24 hours)
- Iterates over expired records, calls `upload.file.delete(save=False)` for each, then bulk-deletes records
- Handles `FileNotFoundError` gracefully (file already gone)
- **No notification** is emitted before or during cleanup — external consumers have no way to know a file is about to be or has been deleted
- Batch-limited to 1000 per run to stay within `CELERY_TASK_TIME_LIMIT` (300s)

### Frontend Architecture (Sidebar, Templates, Views)

**Sidebar** (`frontend/templates/frontend/components/sidebar.html`):
- Desktop sidebar (lines 2-46): collapsible, Alpine.js `sidebarOpen` state, persisted via localStorage
- Mobile sidebar (lines 68-122): overlay drawer with backdrop
- Currently has only one nav item: Dashboard
- Has a comment placeholder at line 37: `{# ── Add your navigation links here ──}`
- Active state uses `sidebar_active` block: `'{% block sidebar_active %}{% endblock %}' === 'dashboard'`

**Template hierarchy**:
- `templates/base.html` — root (loads Tailwind CSS, HTMX, Alpine.js, CSRF header on body)
- `frontend/templates/frontend/base.html` — app shell with sidebar, mobile header, page header/actions/content blocks
- Pages extend `frontend/base.html` and fill blocks: `page_title`, `page_header`, `sidebar_active`, `page_content`

**View pattern** (`frontend/views/dashboard.py`):
- Function-based views with `@frontend_login_required` decorator
- Simple render call with template path
- Views module is a directory: `frontend/views/auth.py`, `frontend/views/dashboard.py`

**URL pattern** (`frontend/urls.py`):
- `app_name = "frontend"`, all under `/app/` prefix
- Pattern: `path("", dashboard.dashboard_view, name="dashboard")`

**Toast notifications** (`frontend/templates/frontend/components/toast.html`):
- Alpine.js-based toast manager with show/hide animations
- Supports types: success, warning, error, info
- Can be triggered via HTMX `showToast` events or Alpine.js `show-toast` window events

### Settings (File Upload + Outbox)

**File upload settings** (`boot/settings.py`, Base class):
- `FILE_UPLOAD_MAX_SIZE = 52_428_800` (50 MB)
- `FILE_UPLOAD_TTL_HOURS = 24`
- `FILE_UPLOAD_ALLOWED_TYPES = None` (accept all)

**Outbox settings** (`boot/settings.py`, Base class):
- `OUTBOX_SWEEP_INTERVAL_MINUTES = 5`
- `OUTBOX_RETENTION_HOURS = 168` (7 days)

**Celery beat schedule** (`boot/settings.py`, Base.CELERY_BEAT_SCHEDULE property):
- `cleanup-expired-upload-files` — crontab every N hours
- `deliver-outbox-events-sweep` — timedelta every 5 min
- `cleanup-delivered-outbox-events` — crontab every 6 hours at :30

**Storage** (`boot/settings.py`):
- Dev: `FileSystemStorage` for default, `CompressedManifestStaticFilesStorage` for static
- Production: Same (pending PEP 0006 for S3)

---

## Key Files & Functions

### Files to Create (New)

| File | Purpose |
|------|---------|
| `frontend/views/upload.py` | Upload page view (GET: render form, POST: handle file upload) |
| `frontend/templates/frontend/upload/index.html` | Upload page template with drag-and-drop UI |
| `common/services/webhook.py` | Webhook delivery service: HTTP POST, HMAC signing, endpoint matching |

### Files to Modify

| File | Lines | Change |
|------|-------|--------|
| `common/models.py` | After line 67 | Add `WebhookEndpoint` model |
| `common/admin.py` | After line 48 | Add `WebhookEndpointAdmin` |
| `common/services/outbox.py` | Lines 77-120 | Replace placeholder `process_pending_events()` with real webhook delivery |
| `uploads/tasks.py` | Lines 15-66 | Add pre-expiry notification before cleanup |
| `frontend/urls.py` | Lines 13-20 | Add `/app/upload/` route |
| `frontend/templates/frontend/components/sidebar.html` | Lines 37-45 (desktop), lines 98-103 (mobile) | Add Upload nav link |
| `boot/settings.py` | After line 175 | Add `FILE_UPLOAD_EXPIRY_NOTIFY_HOURS` setting |
| `requirements.in` | After line 32 | Add `httpx>=0.27` |

### Files for Reference (Patterns to Follow)

| File | What to reference |
|------|-------------------|
| `frontend/views/dashboard.py` | View pattern: `@frontend_login_required`, simple render |
| `frontend/views/auth.py` | View pattern: GET/POST handling, form processing, `require_http_methods` |
| `frontend/templates/frontend/dashboard/index.html` | Template pattern: extends base, blocks for title/header/active/content |
| `common/services/outbox.py:18-74` | `emit_event()` — transactional event emission pattern |
| `common/services/outbox.py:77-120` | `process_pending_events()` — the function to be rewritten |
| `common/models.py:19-67` | `OutboxEvent` model — pattern for new `WebhookEndpoint` model |
| `common/admin.py:9-48` | `OutboxEventAdmin` — pattern for new `WebhookEndpointAdmin` |
| `uploads/services/uploads.py:76-129` | `create_upload_file()` — function that will be called from the upload view |
| `common/tests/test_services.py` | Test patterns: `@pytest.mark.django_db`, test class structure, fixtures |
| `uploads/tests/test_services.py` | Test patterns: `SimpleUploadedFile`, `tmp_path`, `settings` override |
| `conftest.py` | Root `user` fixture |
| `common/tests/conftest.py` | `make_outbox_event` factory fixture |

### Configuration Files

| File | Change |
|------|--------|
| `requirements.in` | Add `httpx>=0.27` |
| `requirements.txt` | Recompile with `uv pip compile --generate-hashes` |
| `requirements-dev.txt` | Recompile |

---

## Technical Constraints

### 1. PEP 0006 Dependency

PEP 0007 **depends on PEP 0006** (S3 Upload Storage). PEP 0006 adds:
- `django-storages[s3]` as a dependency (Production S3 backend)
- `emit_event("file.stored", ...)` call inside `create_upload_file()` (outbox event emission)

If PEP 0006 is not implemented first:
- The upload view will work (files stored locally), but no `file.stored` event will be emitted unless PEP 0007 includes the event emission logic itself
- The webhook delivery handler won't have any events to deliver unless other event sources exist

**Resolution options**: Either (a) implement PEP 0006 first, or (b) have PEP 0007 include the `file.stored` event emission as part of the upload view (rather than in `create_upload_file`), or (c) have PEP 0007 subsume the outbox event emission part of PEP 0006.

### 2. OutboxEvent Retry Logic Gap

The current `process_pending_events()` (lines 93-114) does not implement retry logic:
- It never increments `event.attempts`
- It never sets `event.error_message`
- It never sets `next_attempt_at` to a future time for backoff
- It never transitions to FAILED status

The `OutboxEvent` model has the fields for retry (`attempts`, `max_attempts`, `next_attempt_at`, `error_message`) but the service code doesn't use them. The PEP 0007 rewrite of `process_pending_events()` must implement:
- Increment `attempts` on each delivery attempt
- Exponential backoff: set `next_attempt_at = now() + backoff_delay` on failure
- Transition to FAILED when `attempts >= max_attempts`
- Store the error message in `error_message`

### 3. File Upload Size Limits

- `FILE_UPLOAD_MAX_SIZE` = 50 MB (enforced by `validate_file()`)
- Django's `DATA_UPLOAD_MAX_MEMORY_SIZE` defaults to 2.5 MB — files larger than this are written to temp files on disk, not held in memory. This is fine for the upload view.
- No `FILE_UPLOAD_MAX_NUMBER_FILES` setting exists. The upload view should enforce a reasonable limit to prevent abuse (e.g., max 10 files per request).

### 4. CSRF Protection

- CSRF token is set via `hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'` on the `<body>` tag in `base.html` (line 11)
- HTMX POST requests automatically include the CSRF token
- For non-HTMX multipart/form-data POSTs, the form must include `{% csrf_token %}`

### 5. Celery Serialization

- `CELERY_TASK_SERIALIZER = "json"` — task arguments must be JSON-serializable
- The webhook delivery must happen inside the task, not passed as an argument
- The outbox event payload is already JSONField — no serialization issues

### 6. Database Transaction Boundaries

- `emit_event()` uses `transaction.on_commit()` to dispatch the delivery task — ensures the event is committed before delivery starts
- `process_pending_events()` uses `select_for_update(skip_locked=True)` — safe for concurrent workers
- The rewritten `process_pending_events()` must maintain these concurrency guarantees
- Webhook HTTP calls MUST happen outside the `select_for_update` transaction to avoid holding row locks during slow network calls

### 7. WebhookEndpoint Model Constraints

- Multiple endpoints can exist (fan-out delivery) — an event may need to be delivered to N endpoints
- The current `OutboxEvent` tracks delivery status as a single field — there's no per-endpoint delivery tracking
- **Design tension**: If endpoint A succeeds but endpoint B fails, what is the event's status? Options:
  - (a) Track delivery per-endpoint in a separate `WebhookDelivery` model (more complex, more correct)
  - (b) Re-deliver to ALL endpoints on retry (simpler, but causes duplicate deliveries to endpoint A)
  - (c) Mark as DELIVERED only when ALL endpoints succeed (simplest, but retries hit all endpoints)

### 8. `httpx` and Celery Worker Compatibility

- `httpx 0.28.x` is the latest stable version
- **Known issue**: httpx is incompatible with gevent-based Celery workers. Doorito uses the default `prefork` pool, so this is not a concern.
- Synchronous `httpx.Client` is appropriate since tasks run in prefork workers
- Timeout configuration: `httpx.Timeout(connect=10.0, read=30.0)`

---

## Pattern Analysis

### Pattern: Adding a New View to Frontend

**Reference**: `frontend/views/dashboard.py` (lines 1-11), `frontend/views/auth.py` (lines 1-76)

The upload view should follow these patterns:
1. Create `frontend/views/upload.py` as a new module
2. Import in `frontend/urls.py` as `from frontend.views import upload`
3. Use `@frontend_login_required` decorator
4. For GET+POST views, use `@require_http_methods(["GET", "POST"])` (see `auth.py:10`)
5. Template at `frontend/templates/frontend/upload/index.html`
6. URL name: `path("upload/", upload.upload_view, name="upload")`

### Pattern: Adding a Sidebar Nav Item

**Reference**: `frontend/templates/frontend/components/sidebar.html` (lines 28-35 for dashboard link)

Desktop sidebar nav item structure:
```html
<a href="{% url 'frontend:upload' %}"
   class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors"
   :class="sidebarOpen ? '' : 'justify-center'"
   :class="'{% block sidebar_active %}{% endblock %}' === 'upload' ? 'bg-neutral-800 text-white' : 'hover:bg-neutral-800 hover:text-white'">
  <svg class="w-5 h-5 shrink-0" ...>upload icon</svg>
  <span x-show="sidebarOpen" x-cloak>Upload</span>
</a>
```

Must also add the corresponding link in the mobile sidebar (lines 98-103 area).

### Pattern: Adding a Model to common App

**Reference**: `common/models.py` — `OutboxEvent(TimeStampedModel)` (lines 19-67)

- Inherit from `TimeStampedModel`
- Use `uuid7` for primary key
- Use `TextChoices` for status fields
- Set `db_table`, `verbose_name`, `verbose_name_plural`, `ordering` in Meta
- Define `__str__` method

### Pattern: Service Layer

**Reference**: `common/services/outbox.py`, `uploads/services/uploads.py`

- Services in `{app}/services/{domain}.py`
- Plain functions, not classes
- Logging with `logger = logging.getLogger(__name__)`
- Return dicts with counts for batch operations
- Use `@transaction.atomic` for multi-model operations

### Pattern: Admin Registration

**Reference**: `common/admin.py` (lines 9-48)

- `@admin.register(Model)` decorator
- `list_display` with key fields
- `list_filter` with status and date fields
- `search_fields` for key lookup fields
- `readonly_fields` for computed/auto fields
- `date_hierarchy = "created_at"`
- Custom actions for state transitions (see `retry_failed_events`)

### Pattern: Celery Task

**Reference**: `common/tasks.py` (lines 10-35), `uploads/tasks.py` (lines 15-66)

- `@shared_task(name="...", bind=True, max_retries=2, default_retry_delay=60)`
- Lazy imports inside task body
- Delegate to service functions
- Return dict with counts
- Log with `logger.info` for success

### Pattern: Template Page

**Reference**: `frontend/templates/frontend/dashboard/index.html`

```html
{% extends "frontend/base.html" %}

{% block page_title %}Upload — Doorito{% endblock %}
{% block page_header %}Upload Files{% endblock %}
{% block sidebar_active %}upload{% endblock %}

{% block page_content %}
<!-- Content here -->
{% endblock %}
```

### Patterns to Avoid

1. **Don't put business logic in views** — the upload view should delegate to `create_upload_file()` and `create_batch()`, not contain file handling logic
2. **Don't make HTTP calls inside `transaction.atomic()`** — webhook delivery must happen after the event is committed
3. **Don't hold `select_for_update` locks during HTTP calls** — fetch events, release lock, then deliver
4. **Don't use `async httpx`** — Celery prefork workers run synchronous code; use `httpx.Client` (sync)

---

## External Research

### httpx Library

**Version**: httpx 0.28.1 (latest stable as of Feb 2026)

**Synchronous usage**:
```python
import httpx

timeout = httpx.Timeout(connect=10.0, read=30.0)
with httpx.Client(timeout=timeout) as client:
    response = client.post(url, content=payload_bytes, headers=headers)
    response.raise_for_status()
```

**Key features for webhook delivery**:
- `json=` parameter auto-serializes and sets Content-Type
- `content=` parameter sends pre-encoded bytes (needed for HMAC signing — must sign the exact bytes sent)
- `headers=` for custom webhook headers
- `httpx.Timeout(connect=, read=)` for per-phase timeouts

**Exception hierarchy** (for error handling in delivery):
- `httpx.HTTPError` (base)
  - `httpx.RequestError` → `TimeoutException` (`ConnectTimeout`, `ReadTimeout`), `NetworkError` (`ConnectError`, `ReadError`)
  - `httpx.HTTPStatusError` (4xx/5xx after `raise_for_status()`)

**HMAC-SHA256 signing**: Not built into httpx. Use Python's `hmac` module:
```python
import hashlib, hmac
signature = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
```

**Celery compatibility**: Safe with prefork workers. Known incompatibility with gevent workers (not relevant to Doorito).

**Dependency weight**: Adds `httpx`, `httpcore`, `certifi`, `idna`, `sniffio`, `anyio`, `h11`. Moderate footprint but well worth it for the API quality.

### Webhook Security Best Practices

**Industry standard** (GitHub, Stripe, Shopify):
1. Sign request body with HMAC-SHA256 using a shared secret
2. Include signature in a header (e.g., `X-Hub-Signature-256`, `Stripe-Signature`)
3. Include event type and delivery ID headers for routing and deduplication
4. Use short timeouts (10-30s) to avoid blocking on slow consumers
5. Implement exponential backoff with jitter for retries
6. Max retry count (typically 3-5 attempts)

**Doorito's proposed headers** (from summary.md):
- `X-Webhook-Signature`: HMAC-SHA256 of request body
- `X-Webhook-Event`: event type (e.g., `file.stored`)
- `X-Webhook-Delivery`: event ID (UUID) for deduplication

### Exponential Backoff Formula

Standard approach used by GitHub/Stripe:
```python
delay = min(base_delay * (2 ** attempt), max_delay)
# With jitter:
delay = delay + random.uniform(0, delay * 0.1)
```

Reasonable defaults: base_delay=60s, max_delay=3600s (1 hour), max_attempts=5.

Schedule: attempt 0 → immediate, attempt 1 → 60s, attempt 2 → 120s, attempt 3 → 240s, attempt 4 → 480s.

---

## Risk & Edge Cases

### Risk 1: Per-Endpoint Delivery Tracking

**Risk**: The `OutboxEvent` model tracks delivery as a single `status` field. With multiple `WebhookEndpoint` records, there's no way to track which endpoints received the event and which didn't.

**Edge case**: Event delivered to endpoint A (2xx), fails for endpoint B (timeout). On retry, endpoint A receives a duplicate.

**Mitigation options**:
- (a) Accept duplicate delivery (simpler) — consumers should be idempotent anyway (`X-Webhook-Delivery` header enables deduplication)
- (b) Add a `WebhookDelivery` join model (`OutboxEvent` × `WebhookEndpoint` → delivery status) — more complex but precise

**Recommendation**: Start with option (a) for simplicity. Document that webhook consumers must be idempotent. The `X-Webhook-Delivery` header (event UUID) enables consumer-side deduplication.

### Risk 2: Slow Webhook Consumers Blocking the Worker

**Risk**: If a webhook endpoint is slow (e.g., 30s read timeout per call), and there are many pending events, the worker could be blocked for extended periods.

**Mitigation**:
- httpx timeout (10s connect, 30s read) bounds each call
- Batch processing (100 events max per run) bounds total time per task execution
- `CELERY_TASK_TIME_LIMIT = 300` (5 min) is the hard ceiling
- Multiple webhook endpoints multiply the time per event

**Edge case**: 100 events × 3 endpoints × 30s timeout = 9000s = 2.5 hours. This exceeds `CELERY_TASK_TIME_LIMIT`.

**Mitigation**: Process fewer events per batch when doing real HTTP delivery. Consider 10-20 events per batch, or process events one at a time with individual task dispatches.

### Risk 3: Pre-Expiry Notification Timing

**Risk**: The `file.expiring` event must be emitted before the cleanup task deletes the file. If the expiry notification and cleanup are in the same task, there's a race condition.

**Edge case**: File TTL is 24 hours, notify 1 hour before = file emits `file.expiring` at 23 hours. But what if the cleanup task runs at exactly 24 hours and the expiry notification hasn't been delivered yet?

**Approaches**:
- (a) Separate sweep task for expiring notifications (runs more frequently than cleanup)
- (b) Emit `file.expiring` at deletion time with a "grace period" delay before actually deleting
- (c) Modify the cleanup task to emit the event, then skip deletion until the next run

**Recommendation**: Option (a) — separate `notify_expiring_files_task` that runs every hour, emitting `file.expiring` for files within `FILE_UPLOAD_EXPIRY_NOTIFY_HOURS` of their TTL. The cleanup task continues to run independently. The notification is a heads-up, not a guarantee of non-deletion.

### Risk 4: WebhookEndpoint Secret Storage

**Risk**: Webhook secrets stored in plaintext in the database. If the database is compromised, all webhook secrets are exposed.

**Mitigation**: This is acceptable for the current threat model (single-operator portal). The secret is used for HMAC signing (proving Doorito sent the request), not for accessing external systems. If needed later, encrypt at rest using django-fernet-fields or similar.

### Risk 5: Event Type Matching

**Risk**: `WebhookEndpoint.event_types` is a JSON list of patterns. The matching logic needs to handle:
- Exact match: `"file.stored"` matches `"file.stored"`
- Wildcard match: `"file.*"` matches `"file.stored"` and `"file.expiring"`
- Empty list: matches all events

**Edge case**: What if `event_types` contains `["file.stored", "file.*"]`? Should the endpoint receive two copies? No — deduplication at the matching level.

**Recommendation**: Start with exact match only. An empty `event_types` list (or null/empty JSON) matches all events. Wildcard matching is a future enhancement.

### Risk 6: Upload View Security

**Edge cases**:
- User uploads 0 files (empty POST) — return error
- User uploads more files than expected — enforce a max count
- User uploads a file with a manipulated Content-Type header — `validate_file()` uses `mimetypes.guess_type()` (extension-based), not the client-provided Content-Type. This is safe.
- Concurrent uploads from the same user — safe because each creates a new UploadFile record

### Risk 7: Idempotency Key Collisions on re-uploads

**Edge case**: User uploads the same file twice. `emit_event()` auto-generates `idempotency_key = "UploadFile:{pk}"`. Since each upload creates a new UploadFile with a new UUID, there's no collision. However, the `(event_type, idempotency_key)` unique constraint would prevent duplicate events for the same file — which is the desired behavior.

### Risk 8: httpx as a New Production Dependency

**Risk**: Adding `httpx` introduces ~7 transitive dependencies. This is a production dependency, not dev-only.

**Mitigation**: httpx is well-maintained, widely used, and has minimal security surface. The alternative (`requests`) has similar dependency weight. `urllib3` (stdlib-adjacent) lacks the clean timeout API.

---

## Recommendations

### Implementation Order

1. **WebhookEndpoint model + admin** — foundation for delivery configuration, no functional impact, can be tested independently
2. **httpx dependency** — add to requirements.in, compile, install
3. **Webhook delivery service** (`common/services/webhook.py`) — HMAC signing, HTTP POST, error handling. Unit-testable with mocked httpx.
4. **Rewrite `process_pending_events()`** — replace placeholder with real delivery that calls webhook service. This is the highest-risk change.
5. **Upload view + template + sidebar link** — new page, no modifications to existing code (except URLs and sidebar)
6. **Pre-expiry notification** — new sweep task + `file.expiring` event emission. Modify cleanup task or add new task.
7. **Settings** — `FILE_UPLOAD_EXPIRY_NOTIFY_HOURS`
8. **Tests** — throughout, but especially for webhook delivery and the rewritten `process_pending_events()`

### PEP 0006 Dependency Resolution

PEP 0006 has not been implemented yet. Two parts of PEP 0006 are relevant:
- **S3 storage backend** — only affects Production storage; the upload view works with FileSystemStorage in Dev
- **`file.stored` event emission in `create_upload_file()`** — required for the webhook pipeline to have events to deliver

**Recommendation**: PEP 0007 should either (a) wait for PEP 0006 to be implemented first, or (b) include the `file.stored` event emission itself (the ~10-line change to `create_upload_file()`), and let PEP 0006 focus only on S3 storage. The upload page will work in Dev without S3.

### Per-Endpoint vs Per-Event Delivery Tracking

**Recommendation**: Start with per-event tracking (current model). Mark event as DELIVERED only when ALL matching endpoints succeed. On retry, re-deliver to ALL endpoints. Document that consumers must be idempotent. This matches the summary.md design and avoids a new join model.

If fan-out becomes a real requirement (more than 2-3 endpoints), add a `WebhookDelivery` join model in a follow-up PEP.

### process_pending_events() Rewrite Strategy

The current function structure (lines 77-120):
1. Lock pending events with `select_for_update(skip_locked=True)` inside `transaction.atomic()`
2. Loop over events and mark as DELIVERED

The rewrite should:
1. Lock and **fetch** pending events inside `transaction.atomic()` (release lock after fetch)
2. For each event, **outside** the transaction:
   a. Find matching `WebhookEndpoint` records
   b. POST to each endpoint with HMAC signature
   c. Track success/failure per endpoint
3. After delivery attempts, update event status in a new `transaction.atomic()`:
   - All endpoints succeeded → DELIVERED
   - Any endpoint failed → increment attempts, set next_attempt_at with backoff
   - attempts >= max_attempts → FAILED

**Critical**: HTTP calls must NOT happen inside `select_for_update` to avoid holding row locks during network I/O.

### Batch Size for Real Delivery

With real HTTP calls, processing 100 events per batch (current `DELIVERY_BATCH_SIZE`) could exceed time limits. Each event × N endpoints × up to 30s timeout = long processing time.

**Recommendation**: Reduce batch size to 10-20 for initial implementation. Or switch to a per-event task dispatch model where `process_pending_events()` dispatches individual `deliver_single_event_task(event_id)` tasks, one per event.

### Things to Verify During Implementation

1. `httpx.Client` connection pooling behavior — does it reuse connections across events in the same batch?
2. Django's `FILE_UPLOAD_HANDLERS` setting — default handlers stream large files to temp files, which is correct for the upload view
3. The sidebar's active state detection uses string comparison in Alpine.js — verify the `upload` string works correctly with the `:class` binding
4. The upload template needs to handle both standard form POST and HTMX POST — test with and without JavaScript enabled
5. `DATA_UPLOAD_MAX_MEMORY_SIZE` (Django default 2.5 MB) — files above this go to temp disk; verify this works with the upload flow
6. The outbox unique constraint `(event_type, idempotency_key)` — verify it doesn't interfere with multiple `file.stored` events for different files (different PKs → different idempotency keys → no conflict)
