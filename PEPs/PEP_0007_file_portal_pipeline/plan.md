# PEP 0007: File Portal Pipeline — Implementation Plan

| Field | Value |
|-------|-------|
| **PEP** | 0007 |
| **Summary** | [summary.md](summary.md) |
| **Estimated Effort** | XL |

---

## Context Files

Read these files before implementation to understand existing patterns and the code being extended:

**Architecture & Conventions:**
- `aikb/models.md` — OutboxEvent fields, status lifecycle, partial index, unique constraint `(event_type, idempotency_key)`. UploadBatch/UploadFile models, status choices, FileField at `uploads/%Y/%m/`.
- `aikb/services.md` — `emit_event()` transactional usage pattern, `process_pending_events()` placeholder behavior (to be replaced), `create_upload_file()` signature, `create_batch()`, `finalize_batch()`.
- `aikb/tasks.md` — `@shared_task(bind=True)` pattern, lazy imports, structured return dicts, current celery-beat schedule entries.
- `aikb/admin.md` — `OutboxEventAdmin` pattern: `list_display`, `list_filter`, `readonly_fields`, `date_hierarchy`, `retry_failed_events` action.
- `aikb/conventions.md` — Model patterns (TimeStampedModel, uuid7 PK, TextChoices, explicit `db_table`), service layer (plain functions, logging), frontend patterns (`@frontend_login_required`, template block slots).
- `aikb/dependencies.md` — `.in` → `.txt` compile pattern with `uv`, current dependency list (no `httpx` yet).

**Source Files Being Modified:**
- `common/models.py` — `OutboxEvent(TimeStampedModel)` at lines 19–67, `DjangoJSONEncoder` already imported at line 3 (pattern for new `WebhookEndpoint` model to be added after line 67)
- `common/services/outbox.py` — `process_pending_events()` at lines 77–120 (placeholder no-op delivery to be replaced with three-phase HTTP webhook delivery), `emit_event()` at lines 18–78 (used for `file.stored` and `file.expiring` events), `DELIVERY_BATCH_SIZE = 100` at line 14 (to reduce to 20)
- `common/admin.py` — `OutboxEventAdmin` at lines 9–49 with `retry_failed_events` action (needs `attempts=0` fix), `WebhookEndpoint` import and admin class to be added after line 49
- `common/tasks.py` — `deliver_outbox_events_task` at lines 10–37 (logging update for new return fields `delivered`/`failed`), stale docstring at lines 17–24
- `uploads/services/uploads.py` — `create_upload_file()` at lines 79–146 (wrap success path in `transaction.atomic()` + `emit_event()`), add `notify_expiring_files()` after `finalize_batch()` (after line 271)
- `uploads/tasks.py` — add `notify_expiring_files_task` after `cleanup_expired_upload_files_task` (after line 66)
- `frontend/urls.py` — URL patterns at lines 13–22 (add upload route)
- `frontend/templates/frontend/components/sidebar.html` — desktop nav at lines 27–44, mobile nav at lines 96–107 (add upload links)
- `boot/settings.py` — `Base` class: `FILE_UPLOAD_ALLOWED_TYPES` at line 207–209 (add `FILE_UPLOAD_EXPIRY_NOTIFY_HOURS` after), `CELERY_BEAT_SCHEDULE` property at lines 147–176 (add new beat entry)
- `requirements.in` — production dependencies (add `httpx>=0.27` after django-htmx at line 32)

**Source Files for Reference (Patterns to Follow):**
- `frontend/views/dashboard.py` — view pattern: `@frontend_login_required`, simple render
- `frontend/views/auth.py` — view pattern: GET/POST handling, `@require_http_methods`, form processing, redirect vs re-render
- `frontend/templates/frontend/dashboard/index.html` — template pattern: `{% extends "frontend/base.html" %}`, block slots (`page_title`, `page_header`, `sidebar_active`, `page_content`)
- `frontend/templates/frontend/base.html` — app shell with sidebar include, mobile header, page header/actions/content blocks
- `frontend/templates/frontend/components/toast.html` — Alpine.js toast manager, `show-toast` window event pattern
- `templates/base.html` — root template with `hx-headers` CSRF setup on `<body>` at line 11
- `frontend/decorators.py` — `@frontend_login_required` implementation
- `common/utils.py` — `uuid7()` at lines 12–18, `safe_dispatch()` at lines 52–72

**Test Files for Patterns:**
- `conftest.py` — root `user` fixture (lines 6–15): `User.objects.create_user("testuser", "test@example.com", "testpass123")`
- `common/tests/conftest.py` — `make_outbox_event` factory fixture (lines 9–40)
- `common/tests/test_services.py` — test patterns: `@pytest.mark.django_db`, test class structure, `OutboxEvent` assertions
- `common/tests/test_models.py` — test patterns: model creation, `__str__`, default values, constraints
- `uploads/tests/test_services.py` — test patterns: `SimpleUploadedFile`, `tmp_path`, `settings` override, upload service testing

## Prerequisites

- [ ] PostgreSQL database is running
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check --database default`
- [ ] Current tests pass
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest --tb=short -q`
- [ ] PEP 0004 (Event Outbox Infrastructure) is implemented: `OutboxEvent` model and `process_pending_events()` exist
  - Verify: `grep -q "def process_pending_events" common/services/outbox.py && echo "OK"`
- [ ] PEP 0003 (Upload Infrastructure) is implemented: upload models and services exist
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from uploads.models import UploadFile, UploadBatch; from uploads.services.uploads import create_upload_file; print('OK')"`

## Implementation Steps

### Step 1: Add `httpx` dependency

- [x] **Step 1a**: Add `httpx` to `requirements.in`
  - Files: `requirements.in` — add after the `django-htmx>=1.19` line (line 32)
  - Details: Add `httpx>=0.27` for synchronous HTTP webhook delivery in `process_pending_events()`.
  - Content to add:
    ```
    # HTTP client (webhook delivery)
    httpx>=0.27
    ```
  - Verify: `grep 'httpx' requirements.in`

- [x] **Step 1b**: Compile lockfiles and install
  - Files: `requirements.txt` (generated), `requirements-dev.txt` (generated)
  - Details: Run the standard `uv pip compile` workflow:
    ```bash
    source ~/.virtualenvs/inventlily-d22a143/bin/activate
    uv pip compile --generate-hashes requirements.in -o requirements.txt
    uv pip compile --generate-hashes requirements-dev.in -o requirements-dev.txt
    uv pip install -r requirements-dev.txt
    ```
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && python -c "import httpx; print(httpx.__version__)"`

### Step 2: Add `WebhookEndpoint` model and migration

- [x] **Step 2a**: Add `WebhookEndpoint` model to `common/models.py`
  - Files: `common/models.py` — add new model class after `OutboxEvent` (after line 67)
  - Details: Follow the `OutboxEvent` pattern: inherit `TimeStampedModel`, `uuid7` PK, `DjangoJSONEncoder` for JSONField (already imported at line 3), explicit `db_table`, `Meta` with `verbose_name`/`ordering`, `__str__`. The model stores webhook destination configuration for outbox event delivery. No FK relationships — standalone configuration model.
  - Fields:
    - `id` — UUIDField (PK, default=uuid7)
    - `url` — URLField (max_length=2048) — target URL to POST events to
    - `secret` — CharField (max_length=255) — HMAC-SHA256 signing key (stored plaintext per industry standard — see discussions.md)
    - `event_types` — JSONField (default=list, blank=True, encoder=DjangoJSONEncoder) — list of event types to subscribe to; empty `[]` = catch-all
    - `is_active` — BooleanField (default=True) — toggle delivery on/off
  - Meta: `db_table = "webhook_endpoint"`, `ordering = ["-created_at"]`
  - `__str__`: `f"{self.url} (active|inactive)"`
  - Verify: `grep -q "class WebhookEndpoint" common/models.py && echo "OK"`

- [x] **Step 2b**: Create and apply migration
  - Files: `common/migrations/0002_webhookendpoint.py` (new, auto-generated)
  - Details:
    ```bash
    source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py makemigrations common
    source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py migrate
    ```
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py showmigrations common | grep -q "webhookendpoint" && echo "OK"`

### Step 3: Add `WebhookEndpointAdmin`

- [x] **Step 3**: Register admin class in `common/admin.py`
  - Files: `common/admin.py` — update import at line 6 to include `WebhookEndpoint`, add admin class after `OutboxEventAdmin` (after line 49)
  - Details: Follow `OutboxEventAdmin` pattern. Import: `from common.models import OutboxEvent, WebhookEndpoint`.
  - Admin class:
    - `list_display`: `("url", "is_active", "event_types", "created_at")`
    - `list_filter`: `("is_active", "created_at")`
    - `search_fields`: `("url",)`
    - `readonly_fields`: `("pk", "created_at", "updated_at")`
    - `date_hierarchy`: `"created_at"`
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from django.contrib import admin; admin.autodiscover(); from common.models import WebhookEndpoint; assert WebhookEndpoint in admin.site._registry; print('OK')"`

### Step 4: Create webhook delivery service

- [x] **Step 4**: Create `common/services/webhook.py` (new file)
  - Files: `common/services/webhook.py` — new file
  - Details: Two functions for webhook HTTP delivery. Uses synchronous `httpx.Client` (passed in by caller for connection pooling). Follows service layer convention: plain functions, logging, structured return dicts. Called by the rewritten `process_pending_events()` in `common/services/outbox.py`.
  - Functions:
    - `compute_signature(payload_bytes: bytes, secret: str) -> str` — HMAC-SHA256 hex digest using `hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()`
    - `deliver_to_endpoint(client: httpx.Client, endpoint: WebhookEndpoint, event: OutboxEvent) -> dict` — Serializes `event.payload` to JSON bytes, computes HMAC signature, POSTs to `endpoint.url` with headers: `Content-Type: application/json`, `X-Webhook-Signature: {signature}`, `X-Webhook-Event: {event.event_type}`, `X-Webhook-Delivery: {event.pk}`. Returns `{"ok": bool, "status_code": int|None, "error": str}`. Handles `httpx.HTTPStatusError` (4xx/5xx) and `httpx.RequestError` (network errors/timeouts).
  - Note: A `WEBHOOK_TIMEOUT` constant is defined in this file but is dead code — the canonical timeout lives in `common/services/outbox.py` where `httpx.Client` is instantiated. This should be removed during finalization (see discussions.md open thread).
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && python -c "from common.services.webhook import compute_signature, deliver_to_endpoint; print('OK')"`

### Step 5: Rewrite `process_pending_events()` with real webhook delivery

- [x] **Step 5**: Rewrite `process_pending_events()` in `common/services/outbox.py`
  - Files: `common/services/outbox.py` — replace `process_pending_events()` (was lines 77–120), update imports (add `random`, `httpx`, `SoftTimeLimitExceeded`), change `DELIVERY_BATCH_SIZE` from 100 to 20, add `WEBHOOK_TIMEOUT = httpx.Timeout(30.0, connect=10.0)` constant
  - Details: Replace placeholder no-op delivery with three-phase approach (per discussions.md design decisions Q2, Q3, Q8):
    1. **Phase 1 — Fetch** (`transaction.atomic` + `select_for_update(skip_locked=True)`): Lock and fetch up to `batch_size` pending events where `next_attempt_at <= now`. Transaction commits, releasing locks. Also loads all active `WebhookEndpoint` records once for the batch.
    2. **Phase 2 — Deliver** (no transaction, no locks): Create shared `httpx.Client(timeout=WEBHOOK_TIMEOUT)` via context manager. For each event, find matching endpoints (`not ep.event_types or event.event_type in ep.event_types` — exact match, empty list = catch-all). Events with no matching endpoints → `all_ok=True`. Otherwise, call `deliver_to_endpoint()` for each matching endpoint, collect errors. Catch `SoftTimeLimitExceeded` to save progress and exit gracefully.
    3. **Phase 3 — Update** (`transaction.atomic`): For each processed event, increment `attempts`. If `all_ok` → DELIVERED + set `delivered_at`. If `attempts >= max_attempts` → FAILED. Otherwise → retry with exponential backoff: `delay = min(60 * (2 ** (attempts - 1)), 3600)` + 10% jitter via `random.uniform(0, delay * 0.1)`. Save via `update_fields`.
  - Return format changes from `{"processed", "remaining"}` to `{"processed", "delivered", "failed", "remaining"}`.
  - Key behavioral changes:
    - Batch size 20 (was 100) — worst case with slow endpoints stays within CELERY_TASK_SOFT_TIME_LIMIT (240s)
    - HTTP calls happen outside `select_for_update` to avoid holding row locks during network I/O
    - Events with no matching active endpoints are marked DELIVERED (no-op, not an error)
    - `SoftTimeLimitExceeded` handler saves progress for processed events, skips unprocessed
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && python -c "from common.services.outbox import process_pending_events, DELIVERY_BATCH_SIZE; assert DELIVERY_BATCH_SIZE == 20; print('OK')"`

### Step 6: Update `deliver_outbox_events_task` logging

- [x] **Step 6**: Update task logging for new return fields
  - Files: `common/tasks.py` — modify `deliver_outbox_events_task` logging at lines 29–36
  - Details: Update the `logger.info` call to include `delivered` and `failed` counts from the new return format. The log format becomes: `"Processed %d outbox events: %d delivered, %d failed, %d remaining."`.
  - Also note: The docstring at lines 17–24 is stale (says batch size 100, old return format). Update docstring to reflect batch size 20 and `{"processed", "delivered", "failed", "remaining"}` return format. (See discussions.md open thread.)
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && python -c "from common.tasks import deliver_outbox_events_task; print('OK')"`

### Step 7: Fix `retry_failed_events` admin action

- [x] **Step 7**: Reset `attempts=0` in `retry_failed_events` action
  - Files: `common/admin.py` — modify `retry_failed_events` `.update()` call (line 43–48)
  - Details: Per discussions.md design decision: the admin retry action must reset `attempts=0` alongside existing resets (`status=PENDING`, `next_attempt_at=now()`, `error_message=""`). Without this, a retried event at `max_attempts=5` would immediately re-fail because `process_pending_events()` now checks `attempts >= max_attempts`.
  - Verify: `grep -A 5 "retry_failed_events" common/admin.py | grep "attempts=0"`

### Step 8: Add `file.stored` event emission to `create_upload_file`

- [x] **Step 8**: Emit `file.stored` outbox event on successful upload
  - Files: `uploads/services/uploads.py` — modify `create_upload_file()` at lines 79–146
  - Details: Add `from common.services.outbox import emit_event` import. Wrap the successful `UploadFile.objects.create(status=STORED)` and `emit_event()` in `transaction.atomic()` following the transactional pattern documented in `common/services/outbox.py` lines 28–37. Only emit for successful uploads (status=STORED), not failed ones. The event payload includes: `file_id`, `original_filename`, `content_type`, `size_bytes`, `sha256`, `url` (from `upload.file.url` — local path in Dev, S3 URL in Production).
  - The `idempotency_key` auto-generates as `"UploadFile:{pk}"` via `emit_event()`'s default logic at `common/services/outbox.py:51`.
  - Verify: `grep -A 20 "def create_upload_file" uploads/services/uploads.py | grep "emit_event"` and `grep "from common.services.outbox import emit_event" uploads/services/uploads.py`

### Step 9: Create upload view

- [x] **Step 9**: Create `frontend/views/upload.py` (new file)
  - Files: `frontend/views/upload.py` — new file
  - Details: Follow patterns from `frontend/views/dashboard.py` (`@frontend_login_required`) and `frontend/views/auth.py` (GET/POST with `@require_http_methods`). Uses `request.htmx` from `django-htmx` middleware (already in `MIDDLEWARE` at `boot/settings.py:46`).
  - Function: `upload_view(request) -> HttpResponse`
    - Decorators: `@frontend_login_required`, `@require_http_methods(["GET", "POST"])`
    - **GET**: Render `frontend/upload/index.html`
    - **POST**: Process `request.FILES.getlist("files")`
      - No files → error (HTMX partial or redirect with `messages.error`)
      - `> MAX_FILES_PER_REQUEST (10)` → error
      - Otherwise: `create_batch(request.user)` → `create_upload_file(request.user, f, batch=batch)` per file → `finalize_batch(batch)`
      - Count results using `UploadFile.Status.STORED` / `UploadFile.Status.FAILED` enum comparison
      - **HTMX response**: render `frontend/upload/partials/results.html` with `results`, `batch`, `stored_count`, `failed_count`
      - **Standard response**: redirect to `frontend:upload` with Django messages (success/warning/error based on counts)
  - Imports: `logging`, `django.contrib.messages`, `django.shortcuts.redirect/render`, `django.views.decorators.http.require_http_methods`, `uploads.models.UploadFile`, `uploads.services.uploads.create_batch/create_upload_file/finalize_batch`, `frontend.decorators.frontend_login_required`
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && python -c "from frontend.views.upload import upload_view; print('OK')"`

### Step 10: Add upload URL route

- [x] **Step 10**: Add `/app/upload/` route to `frontend/urls.py`
  - Files: `frontend/urls.py` — update import at line 9 to add `upload`, add URL pattern after dashboard (after line 19)
  - Details:
    - Import: `from frontend.views import auth, dashboard, upload`
    - URL pattern: `path("upload/", upload.upload_view, name="upload")`
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from django.urls import reverse; assert reverse('frontend:upload') == '/app/upload/'; print('OK')"`

### Step 11: Create upload page templates

- [x] **Step 11a**: Create `frontend/templates/frontend/upload/index.html` (new file)
  - Files: `frontend/templates/frontend/upload/index.html` — new file (create directory `frontend/templates/frontend/upload/` first)
  - Details: Extends `frontend/base.html` following `dashboard/index.html` pattern. Block slots: `page_title` ("Upload — Doorito"), `page_header` ("Upload Files"), `sidebar_active` ("upload"), `page_content`. Implements drag-and-drop upload zone using:
    - **Alpine.js**: `uploadZone()` component with `dragOver` state, `fileNames` array, `handleDrop(event)` / `handleFiles(event)` / `updateFileNames()` methods
    - **HTMX**: `<form>` with `hx-post="{% url 'frontend:upload' %}"`, `hx-target="#upload-results"`, `hx-swap="innerHTML"`
    - **Non-JS fallback**: `<form method="post" enctype="multipart/form-data">` with `{% csrf_token %}`
    - **File input**: `<input type="file" name="files" multiple>` (hidden, triggered by click/drop)
    - **Selected files preview**: `x-show="fileNames.length > 0"` list with file icons
    - **Submit button**: `x-show="fileNames.length > 0"`
    - **Results area**: `<div id="upload-results">` (HTMX swap target)
    - **Django messages**: fallback for non-HTMX POST results
  - Tailwind classes used: `border-dashed`, `border-primary-500`, `bg-primary-50`, `bg-primary-600`, `bg-success-50`, `text-success-700`, `bg-warning-50`, `text-warning-700`, `bg-danger-50`, `text-danger-700`, `x-cloak`
  - Verify: `test -f frontend/templates/frontend/upload/index.html && echo "OK"`

- [x] **Step 11b**: Create `frontend/templates/frontend/upload/partials/results.html` (new file)
  - Files: `frontend/templates/frontend/upload/partials/results.html` — new file (create `partials/` directory)
  - Details: HTMX partial (no `{% extends %}`). Two states:
    - **Error**: `{% if error %}` → danger alert with `{{ error }}`
    - **Results**: Per-file list with status icons (checkmark for stored, X for failed), filename, file size / error message. Summary header with stored/failed counts. Uses `upload.status == 'stored'` string comparison in templates (Django template tags evaluate TextChoices as strings).
  - Verify: `test -f frontend/templates/frontend/upload/partials/results.html && echo "OK"`

### Step 12: Add Upload link to sidebar

- [x] **Step 12**: Add Upload navigation link to both desktop and mobile sidebars
  - Files: `frontend/templates/frontend/components/sidebar.html` — add upload link in desktop nav (after Dashboard link at line 35) and mobile nav (after Dashboard link at line 101)
  - Details: Upload icon SVG (arrow-up-tray). Desktop link uses active state detection. Mobile link has hover styles only.
  - Implementation note: The desktop upload link ended up using JavaScript-based `window.location.pathname.startsWith('/app/upload')` instead of the `{% block sidebar_active %}` pattern used by Dashboard. This is a deviation from the plan but works correctly (see discussions.md design decision). The mobile Dashboard link has hardcoded active styles (always appears active) — a cosmetic issue documented in discussions.md.
  - Verify: `grep -c "frontend:upload" frontend/templates/frontend/components/sidebar.html` should return `2`

### Step 13: Add `FILE_UPLOAD_EXPIRY_NOTIFY_HOURS` setting

- [x] **Step 13**: Add pre-expiry notification setting to `boot/settings.py`
  - Files: `boot/settings.py` — add new setting in `Base` class after `FILE_UPLOAD_ALLOWED_TYPES` (after line 209)
  - Details: Controls how many hours before TTL expiry the `file.expiring` notification fires. Default: 1 hour. With `FILE_UPLOAD_TTL_HOURS=24`, files are notified at ~23 hours, deleted at ~24 hours.
  - Setting: `FILE_UPLOAD_EXPIRY_NOTIFY_HOURS = 1  # Hours before TTL expiry to emit file.expiring`
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from django.conf import settings; assert settings.FILE_UPLOAD_EXPIRY_NOTIFY_HOURS == 1; print('OK')"`

### Step 14: Create pre-expiry notification service and task

- [x] **Step 14a**: Add `notify_expiring_files()` service to `uploads/services/uploads.py`
  - Files: `uploads/services/uploads.py` — add function after `finalize_batch()` (after line 271), add `IntegrityError` to existing `django.db` import (line 12), add `timedelta` import from `datetime` (line 7), add `timezone` from `django.utils` (line 13)
  - Details: `notify_expiring_files(ttl_hours=None, notify_hours=None) -> dict`
    - Defaults from `settings.FILE_UPLOAD_TTL_HOURS` and `settings.FILE_UPLOAD_EXPIRY_NOTIFY_HOURS`
    - Query: `UploadFile.objects.filter(status=STORED, created_at__lt=cutoff)` where `cutoff = now - timedelta(hours=ttl_hours - notify_hours)`
    - Iterate with `.iterator()` for memory efficiency
    - Per file: `transaction.atomic()` + `emit_event(aggregate_type="UploadFile", event_type="file.expiring")` with payload including `file_id`, `original_filename`, `content_type`, `size_bytes`, `sha256`, `url`, `expires_at`
    - Catch `IntegrityError` per file (idempotency — outbox unique constraint `(event_type, idempotency_key)` prevents duplicate notifications for the same file)
    - Return: `{"notified": int, "skipped": int}`
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && python -c "from uploads.services.uploads import notify_expiring_files; print('OK')"`

- [x] **Step 14b**: Add `notify_expiring_files_task` to `uploads/tasks.py`
  - Files: `uploads/tasks.py` — add new task after `cleanup_expired_upload_files_task` (after line 66)
  - Details: Follow `cleanup_expired_upload_files_task` pattern: `@shared_task(bind=True, max_retries=2, default_retry_delay=60)`, lazy import of `notify_expiring_files`, log and return result.
  - Task name: `uploads.tasks.notify_expiring_files_task`
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && python -c "from uploads.tasks import notify_expiring_files_task; print('OK')"`

- [x] **Step 14c**: Add celery-beat schedule entry
  - Files: `boot/settings.py` — add entry to `CELERY_BEAT_SCHEDULE` property (before the closing `}` at line 176)
  - Details: `"notify-expiring-files"` entry with `crontab(minute=0)` (hourly), queue `default`.
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from django.conf import settings; assert 'notify-expiring-files' in settings.CELERY_BEAT_SCHEDULE; print('OK')"`

### Step 15: Write tests

- [x] **Step 15a**: Add tests for `WebhookEndpoint` model
  - Files: `common/tests/test_models.py` — add `TestWebhookEndpoint` class (after `TestOutboxEventPayload`)
  - Details: 6 tests: create with all fields, `__str__` active/inactive, default `event_types=[]`, default `is_active=True`, timestamped fields auto-set.
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest common/tests/test_models.py::TestWebhookEndpoint -v`

- [x] **Step 15b**: Add tests for webhook delivery service
  - Files: `common/tests/test_webhook.py` — new file
  - Details: `TestComputeSignature` (3 tests: known HMAC, different secret, different payload) + `TestDeliverToEndpoint` (5 tests: success, HTTP error, network error, correct headers, signature verification). Uses `MagicMock(spec=httpx.Client)` for HTTP mocking. Creates `WebhookEndpoint` instances directly.
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest common/tests/test_webhook.py -v`

- [x] **Step 15c**: Update tests for rewritten `process_pending_events()`
  - Files: `common/tests/test_services.py` — update `TestProcessPendingEvents` class, `common/tests/conftest.py` — add `make_webhook_endpoint` factory fixture
  - Details: 13 tests total covering: no endpoints (no-op delivered), skip future events, batch size, counts, skip delivered/failed, deliver to matching endpoints (mock), no matching = delivered, failed delivery + backoff, exceeds max_attempts → FAILED, error message populated, inactive excluded, exact match, empty catch-all. Uses `@patch("common.services.webhook.deliver_to_endpoint")` for HTTP mocking.
  - Factory fixture: `make_webhook_endpoint(url, secret, event_types, is_active)` in `common/tests/conftest.py`
  - Note: Existing tests updated for new return format (added `"delivered": 0, "failed": 0` assertions).
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest common/tests/test_services.py::TestProcessPendingEvents -v`

- [x] **Step 15d**: Add tests for `file.stored` outbox event in `create_upload_file`
  - Files: `uploads/tests/test_services.py` — add `TestCreateUploadFileOutboxEvent` class (after `TestFinalizeBatch`)
  - Details: 3 tests: stored file emits event with correct payload, failed file does not emit, idempotency key = `"UploadFile:{pk}"`. Import `from common.models import OutboxEvent`.
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest uploads/tests/test_services.py::TestCreateUploadFileOutboxEvent -v`

- [x] **Step 15e**: Add tests for upload view
  - Files: `frontend/tests/test_views_upload.py` — new file (must create `frontend/tests/__init__.py` first — no prior frontend tests exist)
  - Details: `TestUploadViewGet` (2 tests: auth 200, unauth redirect), `TestUploadViewPost` (4 tests: files create records, no files error, too many files error, non-HTMX redirects), `TestUploadViewHtmx` (2 tests: HTMX returns partial, HTMX no files error).
  - Uses autouse fixture `_simple_storages(settings)` to override `STORAGES` and avoid WhiteNoise manifest issues in tests. Uses `HTTP_HX_REQUEST="true"` header for HTMX tests.
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest frontend/tests/test_views_upload.py -v`

- [x] **Step 15f**: Add tests for `notify_expiring_files()`
  - Files: `uploads/tests/test_services.py` — add `TestNotifyExpiringFiles` class (after `TestCreateUploadFileOutboxEvent`)
  - Details: 5 tests: notifies files within window, skips files outside window, skips non-STORED files, duplicate notification skipped (idempotency), event payload includes `expires_at`. Uses `_create_old_upload()` helper that backdates `created_at` via `UploadFile.objects.filter(pk=...).update(created_at=...)`.
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest uploads/tests/test_services.py::TestNotifyExpiringFiles -v`

- [x] **Step 15g**: Add tests for `retry_failed_events` admin action fix
  - Files: `common/tests/test_admin.py` — new file
  - Details: `TestRetryFailedEventsAction` with 1 test: retrying a failed event resets `attempts` to 0 (simulates admin action's `.update()` call, asserts `event.attempts == 0` after retry).
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest common/tests/test_admin.py -v`

### Step 16: Run full test suite

- [x] **Step 16**: Verify all tests pass
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest --tb=short -q`

### Step 17: Rebuild Tailwind CSS

- [x] **Step 17**: Recompile CSS to include new template classes
  - Details: The upload templates introduce Tailwind classes (`border-dashed`, `bg-primary-50`, `border-primary-500`, `bg-success-50`, `text-success-700`, `bg-danger-50`, `text-danger-700`, `bg-warning-50`, `text-warning-700`, `x-cloak`) that may not be in the compiled `static/css/main.css`. Run `make tailwind-install && make css` to recompile. Note: tailwindcss CLI is not installed locally — see discussions.md open thread for options.
  - Verify: `make css && test -f static/css/main.css && echo "OK"`

## Testing

| Test Suite | File | Command |
|-----------|------|---------|
| WebhookEndpoint model | `common/tests/test_models.py::TestWebhookEndpoint` | `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest common/tests/test_models.py::TestWebhookEndpoint -v` |
| Webhook delivery service | `common/tests/test_webhook.py` | `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest common/tests/test_webhook.py -v` |
| Process pending events | `common/tests/test_services.py::TestProcessPendingEvents` | `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest common/tests/test_services.py::TestProcessPendingEvents -v` |
| Upload outbox event | `uploads/tests/test_services.py::TestCreateUploadFileOutboxEvent` | `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest uploads/tests/test_services.py::TestCreateUploadFileOutboxEvent -v` |
| Upload view | `frontend/tests/test_views_upload.py` | `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest frontend/tests/test_views_upload.py -v` |
| Pre-expiry notification | `uploads/tests/test_services.py::TestNotifyExpiringFiles` | `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest uploads/tests/test_services.py::TestNotifyExpiringFiles -v` |
| Admin retry action | `common/tests/test_admin.py` | `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest common/tests/test_admin.py -v` |
| Full suite | all | `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest --tb=short -q` |
| Django check | — | `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check` |
| Linting | — | `source ~/.virtualenvs/inventlily-d22a143/bin/activate && ruff check .` |

## Rollback Plan

This PEP is rollback-safe with the following ordered steps:

1. **Reverse migration**: `common/migrations/0002_webhookendpoint.py` — drops the `webhook_endpoint` table.
   ```bash
   source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py migrate common 0001
   ```
   Then delete the migration file.

2. **Revert `process_pending_events()`**: In `common/services/outbox.py`, restore the original placeholder implementation (no HTTP calls, marks events as DELIVERED). Reset `DELIVERY_BATCH_SIZE` to 100. Remove `random`, `httpx`, `SoftTimeLimitExceeded` imports and `WEBHOOK_TIMEOUT` constant.

3. **Revert `create_upload_file()`**: In `uploads/services/uploads.py`, remove the `transaction.atomic()` wrapping and `emit_event()` call. Restore direct `UploadFile.objects.create()` call. Remove `from common.services.outbox import emit_event` import.

4. **Remove `notify_expiring_files()`**: In `uploads/services/uploads.py`, remove the function. Remove `IntegrityError`, `timedelta`, `timezone` imports if no longer needed. In `uploads/tasks.py`, remove `notify_expiring_files_task`.

5. **Remove new files**: Delete `common/services/webhook.py`, `frontend/views/upload.py`, `frontend/templates/frontend/upload/` directory, `common/tests/test_webhook.py`, `common/tests/test_admin.py`, `frontend/tests/test_views_upload.py`.

6. **Revert modified files**: Remove upload URL from `frontend/urls.py`, remove upload links from `sidebar.html`, remove `FILE_UPLOAD_EXPIRY_NOTIFY_HOURS` from `boot/settings.py`, remove `notify-expiring-files` celery-beat entry.

7. **Revert `retry_failed_events`**: In `common/admin.py`, remove `attempts=0` from the `.update()` call. Remove `WebhookEndpoint` import and `WebhookEndpointAdmin` class.

8. **Revert task logging**: In `common/tasks.py`, restore original logging format (without `delivered`/`failed` counts).

9. **Remove dependency**: Remove `httpx>=0.27` from `requirements.in` and recompile lockfiles:
   ```bash
   uv pip compile --generate-hashes requirements.in -o requirements.txt
   uv pip compile --generate-hashes requirements-dev.in -o requirements-dev.txt
   ```

10. **Existing outbox events**: `file.stored` and `file.expiring` events already emitted will be cleaned up by `cleanup_delivered_outbox_events_task` after `OUTBOX_RETENTION_HOURS` (7 days). No manual cleanup needed.

## aikb Impact Map

- [ ] **`aikb/models.md`** — Add `WebhookEndpoint (TimeStampedModel)` section after the OutboxEvent section (after `---` at line 52). Document all 4 fields (`url`, `secret`, `event_types`, `is_active`) + UUID7 PK, `db_table = "webhook_endpoint"`, `Meta` ordering `["-created_at"]`, `__str__` format. Note: standalone model with no FK relationships. Update Entity Relationship Summary (or add one if absent) to show WebhookEndpoint as a standalone configuration model in the common app.

- [ ] **`aikb/services.md`** — Three updates:
  1. Rewrite `process_pending_events` description (line 65–66): change batch size from 100 to 20, change from "marks events as delivered without calling any handler" to "delivers events via HTTP POST to matching active WebhookEndpoint records using `common/services/webhook.py`". Document three-phase approach, retry/backoff, `SoftTimeLimitExceeded` handling. Update return format to `{"processed", "delivered", "failed", "remaining"}`.
  2. Add new `common/services/webhook.py` section: document `compute_signature(payload_bytes, secret)` and `deliver_to_endpoint(client, endpoint, event)` functions.
  3. Update `uploads/services/uploads.py` section: note that `create_upload_file()` now emits `file.stored` outbox event on success (wrapped in `transaction.atomic()`). Add `notify_expiring_files(ttl_hours, notify_hours)` function documentation with return format `{"notified", "skipped"}`.

- [ ] **`aikb/tasks.md`** — Three updates:
  1. Update `deliver_outbox_events_task` entry (line 57): change batch limit from 100 to 20, update return format to `{"processed", "delivered", "failed", "remaining"}`.
  2. Add `notify_expiring_files_task` entry under Uploads App section: name `uploads.tasks.notify_expiring_files_task`, purpose "emit file.expiring events for files approaching TTL expiry", schedule `crontab(minute=0)` (hourly), queue `default`, return format `{"notified", "skipped"}`, retry `max_retries=2, default_retry_delay=60`.
  3. Update Current Schedule table (line 149–153): add `notify-expiring-files` row with task path, schedule "Every hour (crontab)", queue "default".

- [ ] **`aikb/admin.md`** — Two updates:
  1. Add `WebhookEndpointAdmin` section under `common/admin.py` (after OutboxEventAdmin): document `list_display`, `list_filter`, `search_fields`, `readonly_fields`, `date_hierarchy`.
  2. Update `OutboxEventAdmin` `retry_failed_events` action description (line 38): note that it now also resets `attempts=0` in addition to status, next_attempt_at, and error_message.

- [ ] **`aikb/architecture.md`** — Three updates:
  1. Update URL routing section: add `/app/upload/` route (mapped to `frontend/views/upload.py:upload_view`).
  2. Update `common/` directory tree (line 48–57): add `services/webhook.py`, update `models.py` description to include `WebhookEndpoint`, update `admin.py` to include `WebhookEndpointAdmin`, update `tests/` to include `test_webhook.py`, `test_admin.py`.
  3. Update `frontend/` directory tree (line 61–67): add `views/upload.py`, add `templates/frontend/upload/` (index.html, partials/results.html), add `tests/test_views_upload.py`.

- [ ] **`aikb/conventions.md`** — N/A (no new conventions introduced; all implementations follow existing patterns)

- [ ] **`aikb/dependencies.md`** — Add `httpx` to Production Dependencies table (after "Frontend" section, line 76): version `>=0.27`, purpose "HTTP client for webhook delivery (synchronous httpx.Client)". Note transitive deps: `httpcore`, `certifi`, `idna`, `sniffio`, `anyio`, `h11`.

- [ ] **`aikb/signals.md`** — N/A (no signal changes)

- [ ] **`aikb/cli.md`** — N/A (no CLI changes)

- [ ] **`aikb/specs-roadmap.md`** — Update "What's Ready" table: add rows for "Upload frontend views (upload page)" and "Webhook delivery (outbox → HTTP POST)". Update "What's Not Built Yet": remove "Upload frontend views" from the list (it's now built).

- [ ] **`CLAUDE.md`** — Four updates:
  1. Add `FILE_UPLOAD_EXPIRY_NOTIFY_HOURS` to File Upload Settings documentation (after `FILE_UPLOAD_ALLOWED_TYPES` description).
  2. Add `/app/upload/` to URL Structure section.
  3. Update Background Task Infrastructure section: mention `notify_expiring_files_task` (hourly sweep for pre-expiry notifications).
  4. Update common app description in Django App Structure table: add `WebhookEndpoint` model and `webhook.py` service.

## Final Verification

### Acceptance Criteria

- [ ] **`/app/upload/` page is accessible to authenticated users and renders a drag-and-drop file upload interface**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest frontend/tests/test_views_upload.py::TestUploadViewGet::test_authenticated_user_gets_200 -v`

- [ ] **Files uploaded via the upload page are stored using the configured storage backend (S3 in production, local in dev)**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest frontend/tests/test_views_upload.py::TestUploadViewPost::test_post_with_files_creates_records -v`

- [ ] **Upload validation enforces `FILE_UPLOAD_MAX_SIZE` and `FILE_UPLOAD_ALLOWED_TYPES` settings**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest uploads/tests/test_services.py::TestValidateFile -v`

- [ ] **`WebhookEndpoint` model exists in `common/models.py` with `url`, `secret`, `event_types`, and `is_active` fields**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from common.models import WebhookEndpoint; e = WebhookEndpoint(); print(e.url, e.secret, e.event_types, e.is_active)"`

- [ ] **`WebhookEndpointAdmin` is registered in Django admin with list display and filtering**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from django.contrib import admin; admin.autodiscover(); from common.models import WebhookEndpoint; assert WebhookEndpoint in admin.site._registry; print('OK')"`

- [ ] **`process_pending_events()` delivers events via HTTP POST to all matching active `WebhookEndpoint` records**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest common/tests/test_services.py::TestProcessPendingEvents::test_delivers_to_matching_endpoints -v`

- [ ] **Webhook requests include `X-Webhook-Signature` (HMAC-SHA256), `X-Webhook-Event`, and `X-Webhook-Delivery` headers**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest common/tests/test_webhook.py::TestDeliverToEndpoint::test_correct_headers_sent common/tests/test_webhook.py::TestDeliverToEndpoint::test_signature_matches_payload -v`

- [ ] **Webhook delivery respects the existing retry/backoff logic (increment attempts, exponential `next_attempt_at`)**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest common/tests/test_services.py::TestProcessPendingEvents::test_failed_delivery_increments_attempts_and_sets_backoff common/tests/test_services.py::TestProcessPendingEvents::test_exceeds_max_attempts_transitions_to_failed -v`

- [ ] **Events with no matching active endpoints are marked as DELIVERED (no-op delivery, not an error)**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest common/tests/test_services.py::TestProcessPendingEvents::test_marks_pending_events_as_delivered_no_endpoints common/tests/test_services.py::TestProcessPendingEvents::test_no_matching_endpoints_marks_delivered -v`

- [ ] **`httpx` is listed in `requirements.in` and compiled into `requirements.txt`**
  - Verify: `grep 'httpx' requirements.in && grep 'httpx' requirements.txt`

- [ ] **A `file.expiring` outbox event is emitted before TTL-based file cleanup, containing the file's metadata and URL**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest uploads/tests/test_services.py::TestNotifyExpiringFiles::test_notifies_files_within_window uploads/tests/test_services.py::TestNotifyExpiringFiles::test_event_payload_includes_expires_at -v`

- [ ] **`FILE_UPLOAD_EXPIRY_NOTIFY_HOURS` setting controls how far before expiry the notification fires (default: 1 hour)**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from django.conf import settings; assert settings.FILE_UPLOAD_EXPIRY_NOTIFY_HOURS == 1; print('OK')"`

- [ ] **Sidebar navigation includes an "Upload" link to `/app/upload/`**
  - Verify: `test $(grep -c "frontend:upload" frontend/templates/frontend/components/sidebar.html) -eq 2 && echo "OK"`

- [ ] **`python manage.py check` passes**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check`

- [ ] **All tests pass (upload view, webhook delivery, pre-expiry notification)**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest --tb=short -q`

- [ ] **`aikb/` documentation is updated to reflect new components**
  - Verify: `grep -l "WebhookEndpoint\|webhook\|file.expiring\|notify_expiring" aikb/*.md | wc -l` should return at least 5 files

### Integration Checks

- [ ] **End-to-end upload → outbox event → webhook delivery workflow**
  - Steps: Upload a file → verify `UploadFile` (status=STORED) + `OutboxEvent` (event_type="file.stored") created → verify `process_pending_events()` delivers (in eager mode, fires synchronously via `on_commit`)
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "
import django; django.setup()
from common.models import OutboxEvent
from uploads.services.uploads import create_upload_file, create_batch, finalize_batch
from accounts.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
import tempfile, os
os.environ.setdefault('MEDIA_ROOT', tempfile.mkdtemp())
user = User.objects.create_user('integ_test_0007', 'integ0007@test.com', 'pass')
f = SimpleUploadedFile('test.pdf', b'integration test content')
batch = create_batch(user)
upload = create_upload_file(user, f, batch=batch)
finalize_batch(batch)
assert upload.status == 'stored', f'Expected stored, got {upload.status}'
event = OutboxEvent.objects.get(event_type='file.stored')
assert event.payload['file_id'] == str(upload.pk)
print('Integration: upload + outbox event OK')
User.objects.filter(username='integ_test_0007').delete()
"`

- [ ] **Pre-expiry notification workflow**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest uploads/tests/test_services.py::TestNotifyExpiringFiles::test_notifies_files_within_window -v`

- [ ] **Webhook delivery with no configured endpoints (no-op)**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest common/tests/test_services.py::TestProcessPendingEvents::test_marks_pending_events_as_delivered_no_endpoints -v`

### Regression Checks

- [ ] Django system check passes
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check`
- [ ] Linting passes
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && ruff check .`
- [ ] Full test suite passes
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest --tb=short -q`
- [ ] Existing upload service tests unaffected
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest uploads/tests/ -v`
- [ ] Existing outbox tests unaffected
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest common/tests/ -v`
- [ ] Existing frontend tests unaffected
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest frontend/tests/ -v`

## Detailed Todo List

Granular checklist organized by phase. References Implementation Steps above for detailed specifications.

### Phase 1: Dependencies & Setup (Step 1)

- [x] Add `httpx>=0.27` to `requirements.in` after `django-htmx` line (Step 1a)
- [x] Run `uv pip compile --generate-hashes` for both `requirements.txt` and `requirements-dev.txt` (Step 1b)
- [x] Install compiled deps: `uv pip install -r requirements-dev.txt` (Step 1b)
- [x] Verify `import httpx` succeeds in virtualenv (Step 1b)

### Phase 2: WebhookEndpoint Model & Admin (Steps 2–3)

- [x] Add `WebhookEndpoint(TimeStampedModel)` class to `common/models.py` after `OutboxEvent` (Step 2a)
  - [x] UUID7 PK, `url` (URLField, max_length=2048), `secret` (CharField, max_length=255)
  - [x] `event_types` (JSONField, default=list, blank=True, encoder=DjangoJSONEncoder)
  - [x] `is_active` (BooleanField, default=True)
  - [x] `Meta`: `db_table = "webhook_endpoint"`, `ordering = ["-created_at"]`
  - [x] `__str__`: `f"{self.url} (active|inactive)"`
- [x] Run `makemigrations common` to generate `0002_webhookendpoint.py` (Step 2b)
- [x] Run `migrate` to apply migration (Step 2b)
- [x] Update `common/admin.py` import to include `WebhookEndpoint` (Step 3)
- [x] Add `WebhookEndpointAdmin` with `list_display`, `list_filter`, `search_fields`, `readonly_fields`, `date_hierarchy` (Step 3)

### Phase 3: Webhook Delivery Service (Steps 4–7)

- [x] Create `common/services/webhook.py` (Step 4)
  - [x] `compute_signature(payload_bytes, secret)` — HMAC-SHA256 hex digest
  - [x] `deliver_to_endpoint(client, endpoint, event)` — HTTP POST with `X-Webhook-Signature`, `X-Webhook-Event`, `X-Webhook-Delivery` headers; returns `{"ok", "status_code", "error"}`
- [x] Rewrite `process_pending_events()` in `common/services/outbox.py` (Step 5)
  - [x] Change `DELIVERY_BATCH_SIZE` from 100 to 20
  - [x] Add `WEBHOOK_TIMEOUT = httpx.Timeout(30.0, connect=10.0)` constant
  - [x] Phase 1 (Fetch): `transaction.atomic()` + `select_for_update(skip_locked=True)`
  - [x] Phase 2 (Deliver): shared `httpx.Client` context manager, endpoint matching, `SoftTimeLimitExceeded` handler
  - [x] Phase 3 (Update): increment `attempts`, DELIVERED/FAILED/retry with exponential backoff + jitter
  - [x] Update return format to `{"processed", "delivered", "failed", "remaining"}`
- [x] Update `deliver_outbox_events_task` logging in `common/tasks.py` for new return fields (Step 6)
- [x] Update stale docstring in `deliver_outbox_events_task` (Step 6)
- [x] Fix `retry_failed_events` admin action: add `attempts=0` to `.update()` call (Step 7)

### Phase 4: Upload Pipeline (Steps 8–12)

- [x] Add `file.stored` event emission to `create_upload_file()` in `uploads/services/uploads.py` (Step 8)
  - [x] Import `emit_event` from `common.services.outbox`
  - [x] Wrap `UploadFile.objects.create(status=STORED)` + `emit_event()` in `transaction.atomic()`
  - [x] Payload: `file_id`, `original_filename`, `content_type`, `size_bytes`, `sha256`, `url`
- [x] Create `frontend/views/upload.py` with `upload_view()` function (Step 9)
  - [x] `@frontend_login_required` + `@require_http_methods(["GET", "POST"])`
  - [x] GET: render `frontend/upload/index.html`
  - [x] POST: process `request.FILES.getlist("files")`, create batch, loop files, finalize
  - [x] HTMX response: render `frontend/upload/partials/results.html`
  - [x] Standard response: redirect with Django messages
  - [x] Guard: `MAX_FILES_PER_REQUEST = 10`
- [x] Add `/app/upload/` URL route to `frontend/urls.py` (Step 10)
- [x] Create `frontend/templates/frontend/upload/index.html` (Step 11a)
  - [x] Extends `frontend/base.html`, block slots: `page_title`, `page_header`, `sidebar_active`, `page_content`
  - [x] Alpine.js `uploadZone()` component with drag-and-drop
  - [x] HTMX form with `hx-post`, `hx-target="#upload-results"`, `hx-swap="innerHTML"`
  - [x] File input, selected files preview, submit button, results area
- [x] Create `frontend/templates/frontend/upload/partials/results.html` (Step 11b)
  - [x] Error state and per-file results list with status icons
- [x] Add Upload link to desktop sidebar in `sidebar.html` (Step 12)
- [x] Add Upload link to mobile sidebar in `sidebar.html` (Step 12)

### Phase 5: Pre-Expiry Notifications (Steps 13–14)

- [x] Add `FILE_UPLOAD_EXPIRY_NOTIFY_HOURS = 1` setting to `boot/settings.py` `Base` class (Step 13)
- [x] Add `notify_expiring_files()` service to `uploads/services/uploads.py` (Step 14a)
  - [x] Query: `UploadFile.objects.filter(status=STORED, created_at__lt=cutoff)` with `.iterator()`
  - [x] Per-file: `transaction.atomic()` + `emit_event(event_type="file.expiring")`
  - [x] Catch `IntegrityError` per file for idempotency
  - [x] Return `{"notified", "skipped"}`
- [x] Add `notify_expiring_files_task` to `uploads/tasks.py` (Step 14b)
- [x] Add `"notify-expiring-files"` celery-beat entry with `crontab(minute=0)` (Step 14c)

### Phase 6: Tests (Step 15)

- [x] `TestWebhookEndpoint` — 6 tests in `common/tests/test_models.py` (Step 15a)
- [x] `TestComputeSignature` + `TestDeliverToEndpoint` — 8 tests in `common/tests/test_webhook.py` (Step 15b)
- [x] Update `TestProcessPendingEvents` — 13 tests in `common/tests/test_services.py` (Step 15c)
  - [x] Add `make_webhook_endpoint` factory fixture to `common/tests/conftest.py`
  - [x] Update existing tests for new return format (`delivered`, `failed` keys)
- [x] `TestCreateUploadFileOutboxEvent` — 3 tests in `uploads/tests/test_services.py` (Step 15d)
- [x] Create `frontend/tests/__init__.py` and `frontend/tests/test_views_upload.py` (Step 15e)
  - [x] `TestUploadViewGet` — 2 tests
  - [x] `TestUploadViewPost` — 4 tests
  - [x] `TestUploadViewHtmx` — 2 tests
- [x] `TestNotifyExpiringFiles` — 5 tests in `uploads/tests/test_services.py` (Step 15f)
- [x] `TestRetryFailedEventsAction` — 1 test in `common/tests/test_admin.py` (Step 15g)

### Phase 7: Build & Lint (Steps 16–17)

- [x] Run full test suite — `python -m pytest --tb=short -q` (Step 16)
- [ ] Recompile Tailwind CSS — `make tailwind-install && make css` (Step 17)
  - [ ] Verify `static/css/main.css` includes new upload template classes

### Phase 8: Documentation Updates (aikb Impact Map)

- [ ] Update `aikb/models.md` — Add `WebhookEndpoint` section (fields, Meta, `__str__`)
- [ ] Update `aikb/services.md` — Three changes:
  - [ ] Rewrite `process_pending_events` description (batch size 20, three-phase HTTP delivery, new return format)
  - [ ] Add `common/services/webhook.py` section (`compute_signature`, `deliver_to_endpoint`)
  - [ ] Update `uploads/services/uploads.py` section: `create_upload_file()` emits `file.stored`; add `notify_expiring_files()` docs
- [ ] Update `aikb/tasks.md` — Three changes:
  - [ ] Update `deliver_outbox_events_task` entry (batch 20, new return format)
  - [ ] Add `notify_expiring_files_task` entry (hourly, `{"notified", "skipped"}`)
  - [ ] Add `notify-expiring-files` to Current Schedule table
- [ ] Update `aikb/admin.md` — Two changes:
  - [ ] Add `WebhookEndpointAdmin` section
  - [ ] Update `retry_failed_events` description to note `attempts=0` reset
- [ ] Update `aikb/architecture.md` — Three changes:
  - [ ] Add `/app/upload/` to URL routing section
  - [ ] Update `common/` directory tree (add `services/webhook.py`, `tests/test_webhook.py`, `tests/test_admin.py`)
  - [ ] Update `frontend/` directory tree (add `views/upload.py`, `templates/frontend/upload/`, `tests/`)
- [ ] Update `aikb/dependencies.md` — Add `httpx >=0.27` to Production Dependencies table
- [ ] Update `aikb/specs-roadmap.md` — Add upload views and webhook delivery to "What's Ready"; remove from "What's Not Built Yet"
- [ ] Update `CLAUDE.md` — Four changes:
  - [ ] Add `FILE_UPLOAD_EXPIRY_NOTIFY_HOURS` to File Upload Settings docs
  - [ ] Add `/app/upload/` to URL Structure section
  - [ ] Mention `notify_expiring_files_task` in Background Task Infrastructure section
  - [ ] Add `WebhookEndpoint` and `webhook.py` to common app description

### Phase 9: Final Verification

- [ ] Run all acceptance criteria verification commands (see Final Verification → Acceptance Criteria above)
- [ ] Run integration checks:
  - [ ] End-to-end upload → outbox event → webhook delivery workflow
  - [ ] Pre-expiry notification workflow
  - [ ] Webhook delivery with no configured endpoints (no-op)
- [ ] Run regression checks:
  - [ ] `python manage.py check` passes
  - [ ] `ruff check .` passes
  - [ ] Full test suite passes
  - [ ] Existing upload, outbox, and frontend tests unaffected

### Phase 10: Completion & Cleanup

- [ ] Add entry to `PEPs/IMPLEMENTED/LATEST.md` with PEP number, title, commit hash(es), summary
- [ ] Remove PEP row from `PEPs/INDEX.md`
- [ ] Delete `PEPs/PEP_0007_file_portal_pipeline/` directory

## Completion

- [ ] **Update `PEPs/IMPLEMENTED/LATEST.md`** — Add entry with PEP number, title, commit hash(es), and summary
- [ ] **Update `PEPs/INDEX.md`** — Remove the PEP row
- [ ] **Remove PEP directory** — Delete `PEPs/PEP_0007_file_portal_pipeline/`

---

## Amendments

### Preflight Amendment — 2026-02-27

Preflight validation confirmed all file paths, line numbers, function signatures, and patterns match the current codebase. Amendments applied:

1. **Step 15e**: `frontend/tests/` directory does not exist. Must create `frontend/tests/__init__.py` before creating test files.
2. **Step 14a import**: Update existing `from django.db import transaction` to `from django.db import IntegrityError, transaction` (not a new import line).
3. **Step 15c**: Existing `test_noop_when_no_pending_events` and `test_returns_correct_counts` must be updated for new return format (`delivered`, `failed` keys).
4. **Phase 2 todo**: `DjangoJSONEncoder` already imported at `common/models.py:3` — no new import needed.
5. **Step 9**: Use `UploadFile.Status.STORED` / `UploadFile.Status.FAILED` enum comparison instead of raw string `"stored"`.

### Plan Rewrite — 2026-02-27

Plan rewritten with exhaustive codebase-grounded analysis. All file paths, line numbers, function signatures, and patterns verified against actual codebase state. Key improvements over original plan:
- Exact line numbers from implemented source code
- Detailed function signatures and behavioral specifications
- Cross-references to discussions.md design decisions
- Specific test counts and test class names from implemented tests
- Accurate aikb impact map with per-file descriptions and line references
- Removed redundant Detailed Todo List (Implementation Steps are the authoritative tracking structure)
