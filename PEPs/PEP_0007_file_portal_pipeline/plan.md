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
- `aikb/models.md` §OutboxEvent — OutboxEvent fields (`attempts`, `max_attempts`, `next_attempt_at`, `error_message`), status lifecycle, partial index, unique constraint on `(event_type, idempotency_key)`
- `aikb/models.md` §Uploads App — UploadBatch, UploadFile models (status choices, FileField at `uploads/%Y/%m/`, FK relationships)
- `aikb/services.md` §common/services/outbox.py — `emit_event()` transactional usage pattern, `process_pending_events()` current placeholder behavior
- `aikb/services.md` §uploads/services/uploads.py — `create_upload_file()`, `create_batch()`, `finalize_batch()`, `validate_file()` signatures
- `aikb/tasks.md` §Task Conventions — `@shared_task(bind=True)` pattern, lazy imports, structured return dicts
- `aikb/tasks.md` §Current Schedule — existing celery-beat entries and schedule format
- `aikb/admin.md` §common/admin.py — `OutboxEventAdmin` pattern (`list_display`, `list_filter`, `readonly_fields`, `date_hierarchy`, custom actions)
- `aikb/conventions.md` §Frontend Patterns — template hierarchy, HTMX/Alpine.js usage, `@frontend_login_required`
- `aikb/dependencies.md` — `.in` → `.txt` compile pattern with `uv`, current dependency list

**Source Files Being Modified:**
- `common/models.py` — `OutboxEvent(TimeStampedModel)` at lines 19–67 (pattern for new `WebhookEndpoint` model)
- `common/services/outbox.py` — `process_pending_events()` at lines 77–120 (the function to be rewritten), `emit_event()` at lines 18–74 (used for `file.stored` and `file.expiring` events)
- `common/admin.py` — `OutboxEventAdmin` at lines 9–48 (pattern for `WebhookEndpointAdmin`, plus `retry_failed_events` action at lines 40–48 needs fix)
- `common/tasks.py` — `deliver_outbox_events_task` at lines 10–35 (thin wrapper around `process_pending_events`)
- `uploads/services/uploads.py` — `create_upload_file()` at lines 76–129 (add `file.stored` event emission)
- `uploads/tasks.py` — `cleanup_expired_upload_files_task` at lines 15–66 (reference for new task pattern)
- `frontend/urls.py` — URL patterns at lines 13–20 (add upload route)
- `frontend/templates/frontend/components/sidebar.html` — desktop nav at lines 27–45, mobile nav at lines 97–104 (add upload link)
- `boot/settings.py` — `Base` class settings at lines 173–178 (add new setting), `CELERY_BEAT_SCHEDULE` property at lines 147–171 (add new beat entry)
- `requirements.in` — production dependencies (add `httpx`)

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
- `conftest.py` — root `user` fixture (lines 6–15)
- `common/tests/conftest.py` — `make_outbox_event` factory fixture
- `common/tests/test_services.py` — test patterns: `@pytest.mark.django_db`, test class structure, `OutboxEvent` assertions
- `uploads/tests/test_services.py` — test patterns: `SimpleUploadedFile`, `tmp_path`, `settings` override, upload service testing

## Prerequisites

- [ ] PostgreSQL database is running: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check --database default`
- [ ] Current tests pass: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest --tb=short -q`
- [ ] PEP 0004 (Event Outbox Infrastructure) is implemented: `grep -q "process_pending_events" common/services/outbox.py && echo "OK"`
- [ ] Upload infrastructure exists (PEP 0003): `python -c "import uploads.models; print('OK')"`

## Implementation Steps

### Step 1: Add `httpx` dependency

- [ ] **Step 1a**: Add `httpx` to `requirements.in`
  - Files: `requirements.in` — add new line after the `django-htmx` entry (line 32)
  - Details: Add `httpx>=0.27` as a new section. This is used for webhook HTTP delivery in `process_pending_events()`.
  - Content to add:
    ```
    # HTTP client (webhook delivery)
    httpx>=0.27
    ```
  - Verify: `grep 'httpx' requirements.in`

- [ ] **Step 1b**: Compile lockfiles and install
  - Files: `requirements.txt` (generated), `requirements-dev.txt` (generated)
  - Details: Run the standard `uv pip compile` workflow with `--generate-hashes`:
    ```bash
    source ~/.virtualenvs/inventlily-d22a143/bin/activate
    uv pip compile --generate-hashes requirements.in -o requirements.txt
    uv pip compile --generate-hashes requirements-dev.in -o requirements-dev.txt
    uv pip install -r requirements-dev.txt
    ```
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && python -c "import httpx; print(httpx.__version__)"`

### Step 2: Add `WebhookEndpoint` model and migration

- [ ] **Step 2a**: Add `WebhookEndpoint` model to `common/models.py`
  - Files: `common/models.py` — add new model class after `OutboxEvent` (after line 67)
  - Details: Follow the `OutboxEvent` pattern: inherit from `TimeStampedModel`, use `uuid7` PK, `TextChoices` for any enums, explicit `db_table`, `Meta` with `verbose_name`/`ordering`, `__str__`. The model stores webhook destination configuration.
  - Model definition:
    ```python
    class WebhookEndpoint(TimeStampedModel):
        """Configured webhook destination for outbox event delivery.

        Events are delivered via HTTP POST to active endpoints whose
        event_types match the event's event_type. An empty event_types
        list matches all events (catch-all).
        """

        id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
        url = models.URLField(max_length=2048, help_text="Target URL to POST events to")
        secret = models.CharField(
            max_length=255,
            help_text="Shared secret for HMAC-SHA256 request signing",
        )
        event_types = models.JSONField(
            default=list,
            blank=True,
            encoder=DjangoJSONEncoder,
            help_text=(
                'JSON list of event types to subscribe to (e.g., ["file.stored"]). '
                "Empty list matches all events."
            ),
        )
        is_active = models.BooleanField(
            default=True,
            help_text="Enable or disable delivery to this endpoint",
        )

        class Meta:
            db_table = "webhook_endpoint"
            verbose_name = "webhook endpoint"
            verbose_name_plural = "webhook endpoints"
            ordering = ["-created_at"]

        def __str__(self):
            status = "active" if self.is_active else "inactive"
            return f"{self.url} ({status})"
    ```
  - Verify: `grep -q "class WebhookEndpoint" common/models.py && echo "OK"`

- [ ] **Step 2b**: Create and apply migration
  - Files: `common/migrations/0002_webhookendpoint.py` (new, auto-generated)
  - Details: Run `makemigrations` and `migrate`:
    ```bash
    source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py makemigrations common
    source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py migrate
    ```
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py showmigrations common | grep -q "webhookendpoint" && echo "OK"`

### Step 3: Add `WebhookEndpointAdmin`

- [ ] **Step 3**: Register admin class in `common/admin.py`
  - Files: `common/admin.py` — add new admin class after `OutboxEventAdmin` (after line 48), add `WebhookEndpoint` to imports at line 6
  - Details: Follow the `OutboxEventAdmin` pattern. Key fields for `list_display`: `url`, `is_active`, `event_types`, `created_at`. Add filtering by `is_active`. Make `id`, `created_at`, `updated_at` read-only.
  - Admin class:
    ```python
    @admin.register(WebhookEndpoint)
    class WebhookEndpointAdmin(admin.ModelAdmin):
        """Admin interface for webhook endpoint configuration."""

        list_display = ("url", "is_active", "event_types", "created_at")
        list_filter = ("is_active", "created_at")
        search_fields = ("url",)
        readonly_fields = ("pk", "created_at", "updated_at")
        date_hierarchy = "created_at"
    ```
  - Update import at line 6: `from common.models import OutboxEvent, WebhookEndpoint`
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from django.contrib import admin; admin.autodiscover(); print('WebhookEndpoint' in [m.__name__ for m in admin.site._registry])" | grep -q "True" && echo "OK"`

### Step 4: Create webhook delivery service

- [ ] **Step 4**: Create `common/services/webhook.py` (new file)
  - Files: `common/services/webhook.py` — new file
  - Details: Contains two functions: `compute_signature()` for HMAC-SHA256 signing and `deliver_to_endpoint()` for HTTP POST delivery. Uses synchronous `httpx.Client`. Follows the service layer pattern (plain functions, logging, structured returns). This service is called by the rewritten `process_pending_events()`.
  - Service functions:
    ```python
    """Webhook delivery service for outbox events."""

    import hashlib
    import hmac
    import json
    import logging

    import httpx

    logger = logging.getLogger(__name__)

    WEBHOOK_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0)


    def compute_signature(payload_bytes, secret):
        """Compute HMAC-SHA256 signature for webhook payload.

        Args:
            payload_bytes: The raw bytes of the JSON payload.
            secret: The shared secret string.

        Returns:
            Hex-encoded HMAC-SHA256 signature string.
        """
        return hmac.new(
            secret.encode("utf-8"), payload_bytes, hashlib.sha256
        ).hexdigest()


    def deliver_to_endpoint(client, endpoint, event):
        """Deliver an outbox event to a single webhook endpoint.

        Posts the event payload as JSON with HMAC signature and
        metadata headers.

        Args:
            client: An httpx.Client instance (for connection pooling).
            endpoint: A WebhookEndpoint instance.
            event: An OutboxEvent instance.

        Returns:
            dict: {"ok": bool, "status_code": int|None, "error": str}
        """
        payload_bytes = json.dumps(event.payload, default=str).encode("utf-8")
        signature = compute_signature(payload_bytes, endpoint.secret)

        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Signature": signature,
            "X-Webhook-Event": event.event_type,
            "X-Webhook-Delivery": str(event.pk),
        }

        try:
            response = client.post(
                str(endpoint.url), content=payload_bytes, headers=headers
            )
            response.raise_for_status()
            logger.info(
                "Webhook delivered: event=%s endpoint=%s status=%d",
                event.pk,
                endpoint.url,
                response.status_code,
            )
            return {"ok": True, "status_code": response.status_code, "error": ""}
        except httpx.HTTPStatusError as exc:
            error = f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            logger.warning(
                "Webhook HTTP error: event=%s endpoint=%s error=%s",
                event.pk,
                endpoint.url,
                error,
            )
            return {"ok": False, "status_code": exc.response.status_code, "error": error}
        except httpx.RequestError as exc:
            error = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "Webhook request error: event=%s endpoint=%s error=%s",
                event.pk,
                endpoint.url,
                error,
            )
            return {"ok": False, "status_code": None, "error": error}
    ```
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && python -c "from common.services.webhook import compute_signature, deliver_to_endpoint; print('OK')"`

### Step 5: Rewrite `process_pending_events()` with real webhook delivery

- [ ] **Step 5**: Rewrite `process_pending_events()` in `common/services/outbox.py`
  - Files: `common/services/outbox.py` — replace `process_pending_events()` at lines 77–120, update `DELIVERY_BATCH_SIZE` at line 14
  - Details: Replace the placeholder no-op delivery with a three-phase approach (per discussions.md design decision):
    1. **Fetch phase** (`transaction.atomic` + `select_for_update`): Lock and fetch pending events. Release locks after collecting PKs and data.
    2. **Delivery phase** (no transaction): For each event, find matching `WebhookEndpoint` records, POST to each using the webhook service, collect results. Use a shared `httpx.Client` for connection pooling within the batch.
    3. **Update phase** (`transaction.atomic`): Update each event's status based on delivery results — DELIVERED if all endpoints succeeded (or no matching endpoints), retry with backoff if any failed, FAILED if `attempts >= max_attempts`.

    Key changes:
    - Reduce `DELIVERY_BATCH_SIZE` from 100 to 20 (per discussions.md Q3 resolution)
    - Add exponential backoff: `delay = min(60 * (2 ** attempts), 3600)` with 10% jitter
    - Increment `event.attempts` on each delivery attempt
    - Set `event.error_message` on failure
    - Transition to FAILED when `attempts >= max_attempts`
    - Events with no matching active endpoints are marked DELIVERED (no-op, per acceptance criteria)
    - HTTP calls happen OUTSIDE `select_for_update` to avoid holding row locks during network I/O
    - Handle `SoftTimeLimitExceeded` for early exit (save progress, return)

  - Updated imports at top of file (add after line 5):
    ```python
    import random

    import httpx
    from celery.exceptions import SoftTimeLimitExceeded
    ```
  - Updated constant (line 14):
    ```python
    DELIVERY_BATCH_SIZE = 20
    ```
  - Rewritten function:
    ```python
    def process_pending_events(batch_size=DELIVERY_BATCH_SIZE):
        """Process pending outbox events via webhook delivery.

        Three-phase approach to avoid holding row locks during HTTP I/O:
        1. Fetch: lock and collect pending events
        2. Deliver: POST to matching webhook endpoints (no DB locks)
        3. Update: write delivery results back to the database

        Events with no matching active endpoints are marked DELIVERED.
        On delivery failure, events are retried with exponential backoff.
        Events exceeding max_attempts are marked FAILED.

        Args:
            batch_size: Maximum events to process per call.

        Returns:
            dict: {"processed": int, "delivered": int, "failed": int, "remaining": int}
        """
        from common.models import WebhookEndpoint

        now = timezone.now()

        # Phase 1: Fetch pending events (short transaction, releases locks)
        with transaction.atomic():
            events = list(
                OutboxEvent.objects.filter(
                    status=OutboxEvent.Status.PENDING,
                    next_attempt_at__lte=now,
                ).select_for_update(skip_locked=True)[:batch_size]
            )

        if not events:
            remaining = OutboxEvent.objects.filter(
                status=OutboxEvent.Status.PENDING,
            ).count()
            return {"processed": 0, "delivered": 0, "failed": 0, "remaining": remaining}

        # Load active endpoints once for the batch
        endpoints = list(WebhookEndpoint.objects.filter(is_active=True))

        # Phase 2: Deliver (no transaction, no locks)
        results = {}  # event.pk -> {"all_ok": bool, "error": str}
        try:
            with httpx.Client(timeout=WEBHOOK_TIMEOUT) as client:
                for event in events:
                    matching = [
                        ep for ep in endpoints
                        if not ep.event_types or event.event_type in ep.event_types
                    ]

                    if not matching:
                        # No matching endpoints — mark as delivered (no-op)
                        results[event.pk] = {"all_ok": True, "error": ""}
                        continue

                    from common.services.webhook import deliver_to_endpoint

                    errors = []
                    for ep in matching:
                        result = deliver_to_endpoint(client, ep, event)
                        if not result["ok"]:
                            errors.append(f"{ep.url}: {result['error']}")

                    results[event.pk] = {
                        "all_ok": len(errors) == 0,
                        "error": "; ".join(errors),
                    }
        except SoftTimeLimitExceeded:
            logger.warning(
                "Soft time limit reached during webhook delivery, "
                "saving progress for %d/%d events.",
                len(results),
                len(events),
            )

        # Phase 3: Update event statuses (short transaction)
        delivered_count = 0
        failed_count = 0
        now = timezone.now()

        with transaction.atomic():
            for event in events:
                if event.pk not in results:
                    # Not processed (soft time limit hit) — skip, will retry next sweep
                    continue

                r = results[event.pk]
                event.attempts += 1

                if r["all_ok"]:
                    event.status = OutboxEvent.Status.DELIVERED
                    event.delivered_at = now
                    event.next_attempt_at = None
                    event.error_message = ""
                    delivered_count += 1
                elif event.attempts >= event.max_attempts:
                    event.status = OutboxEvent.Status.FAILED
                    event.next_attempt_at = None
                    event.error_message = r["error"]
                    failed_count += 1
                else:
                    # Retry with exponential backoff + jitter
                    delay = min(60 * (2 ** (event.attempts - 1)), 3600)
                    jitter = random.uniform(0, delay * 0.1)  # noqa: S311
                    event.next_attempt_at = now + timedelta(seconds=delay + jitter)
                    event.error_message = r["error"]

                event.save(
                    update_fields=[
                        "status",
                        "attempts",
                        "delivered_at",
                        "next_attempt_at",
                        "error_message",
                        "updated_at",
                    ]
                )

        remaining = OutboxEvent.objects.filter(
            status=OutboxEvent.Status.PENDING,
        ).count()

        return {
            "processed": len(results),
            "delivered": delivered_count,
            "failed": failed_count,
            "remaining": remaining,
        }
    ```
  - Also add at the module level (after `CLEANUP_BATCH_SIZE` line 15):
    ```python
    WEBHOOK_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0)
    ```
  - Note: The return format changes from `{"processed", "remaining"}` to `{"processed", "delivered", "failed", "remaining"}`. Update `deliver_outbox_events_task` in `common/tasks.py` to log the new fields.
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && python -c "from common.services.outbox import process_pending_events; print('OK')"`

### Step 6: Update `deliver_outbox_events_task` logging

- [ ] **Step 6**: Update task to log new return fields
  - Files: `common/tasks.py` — modify `deliver_outbox_events_task` at lines 28–34
  - Details: Update the logging to include `delivered` and `failed` counts from the new return format.
  - Updated logging:
    ```python
    if result["processed"] > 0:
        logger.info(
            "Processed %d outbox events: %d delivered, %d failed, %d remaining.",
            result["processed"],
            result["delivered"],
            result["failed"],
            result["remaining"],
        )
    ```
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && python -c "from common.tasks import deliver_outbox_events_task; print('OK')"`

### Step 7: Fix `retry_failed_events` admin action

- [ ] **Step 7**: Reset `attempts=0` in `retry_failed_events` action
  - Files: `common/admin.py` — modify `retry_failed_events` at lines 40–48
  - Details: Per discussions.md design decision, the admin retry action must reset `attempts=0` alongside existing field resets. Without this, a retried event at `max_attempts=5` would immediately re-fail because `process_pending_events()` now checks `attempts >= max_attempts`.
  - Updated `.update()` call:
    ```python
    updated = queryset.filter(status=OutboxEvent.Status.FAILED).update(
        status=OutboxEvent.Status.PENDING,
        next_attempt_at=timezone.now(),
        error_message="",
        attempts=0,
    )
    ```
  - Verify: `grep -A 5 "retry_failed_events" common/admin.py | grep "attempts=0"`

### Step 8: Add `file.stored` event emission to `create_upload_file`

- [ ] **Step 8**: Emit `file.stored` outbox event on successful upload
  - Files: `uploads/services/uploads.py` — modify `create_upload_file()` at lines 76–129
  - Details: Since PEP 0006 is not yet implemented, PEP 0007 includes the `file.stored` event emission. Wrap the successful `UploadFile.objects.create(...)` call and `emit_event()` in `transaction.atomic()` following the pattern documented in `common/services/outbox.py` lines 28–32. Only emit for successful uploads (status=STORED), not failed ones. The event payload includes `file_id`, `original_filename`, `content_type`, `size_bytes`, `sha256`, and `url`.
  - Add import at top of file (after existing `from django.db import transaction` at line 10):
    ```python
    from common.services.outbox import emit_event
    ```
    Note: `transaction` is already imported at line 10.
  - Modify the success path (lines 109–128) to:
    ```python
    sha256 = compute_sha256(file)

    with transaction.atomic():
        upload = UploadFile.objects.create(
            uploaded_by=user,
            file=file,
            original_filename=file.name,
            content_type=content_type,
            size_bytes=size_bytes,
            sha256=sha256,
            batch=batch,
            status=UploadFile.Status.STORED,
        )
        emit_event(
            aggregate_type="UploadFile",
            aggregate_id=str(upload.pk),
            event_type="file.stored",
            payload={
                "file_id": str(upload.pk),
                "original_filename": upload.original_filename,
                "content_type": upload.content_type,
                "size_bytes": upload.size_bytes,
                "sha256": upload.sha256,
                "url": upload.file.url,
            },
        )
    ```
  - The `idempotency_key` defaults to `"UploadFile:{pk}"` via `emit_event`'s auto-generation (see `common/services/outbox.py` line 47).
  - Verify: `grep -A 20 "def create_upload_file" uploads/services/uploads.py | grep "emit_event"` and `grep "from common.services.outbox import emit_event" uploads/services/uploads.py`

### Step 9: Create upload view

- [ ] **Step 9**: Create `frontend/views/upload.py` (new file)
  - Files: `frontend/views/upload.py` — new file
  - Details: Follow the patterns from `frontend/views/dashboard.py` (simple `@frontend_login_required` view) and `frontend/views/auth.py` (GET/POST handling with `@require_http_methods`). The view handles:
    - **GET**: Render the upload form page
    - **POST**: Process uploaded files via `request.FILES.getlist("files")`, delegate to `create_batch()` + `create_upload_file()` + `finalize_batch()`, return results
    - **HTMX detection**: Use `request.htmx` (from `django-htmx` middleware) to return either an HTML fragment (HTMX) or redirect with messages (standard POST)
    - **Max files guard**: Reject requests with more than 10 files (constant `MAX_FILES_PER_REQUEST = 10`)
  - View implementation:
    ```python
    """Upload view for the frontend app."""

    import logging

    from django.contrib import messages
    from django.shortcuts import redirect, render
    from django.views.decorators.http import require_http_methods

    from frontend.decorators import frontend_login_required
    from uploads.services.uploads import create_batch, create_upload_file, finalize_batch

    logger = logging.getLogger(__name__)

    MAX_FILES_PER_REQUEST = 10


    @frontend_login_required
    @require_http_methods(["GET", "POST"])
    def upload_view(request):
        """Upload page with drag-and-drop file upload interface."""
        if request.method == "GET":
            return render(request, "frontend/upload/index.html")

        # POST: process uploaded files
        files = request.FILES.getlist("files")

        if not files:
            error = "No files selected."
            if request.htmx:
                return render(
                    request,
                    "frontend/upload/partials/results.html",
                    {"error": error},
                )
            messages.error(request, error)
            return redirect("frontend:upload")

        if len(files) > MAX_FILES_PER_REQUEST:
            error = f"Too many files. Maximum {MAX_FILES_PER_REQUEST} files per upload."
            if request.htmx:
                return render(
                    request,
                    "frontend/upload/partials/results.html",
                    {"error": error},
                )
            messages.error(request, error)
            return redirect("frontend:upload")

        batch = create_batch(request.user)
        results = []
        for f in files:
            upload = create_upload_file(request.user, f, batch=batch)
            results.append(upload)
        finalize_batch(batch)

        stored_count = sum(1 for r in results if r.status == "stored")
        failed_count = sum(1 for r in results if r.status == "failed")

        if request.htmx:
            return render(
                request,
                "frontend/upload/partials/results.html",
                {
                    "results": results,
                    "batch": batch,
                    "stored_count": stored_count,
                    "failed_count": failed_count,
                },
            )

        if failed_count == 0:
            messages.success(request, f"Uploaded {stored_count} file(s) successfully.")
        elif stored_count > 0:
            messages.warning(
                request,
                f"Uploaded {stored_count} file(s), {failed_count} failed.",
            )
        else:
            messages.error(request, f"All {failed_count} file(s) failed to upload.")

        return redirect("frontend:upload")
    ```
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && python -c "from frontend.views.upload import upload_view; print('OK')"`

### Step 10: Add upload URL route

- [ ] **Step 10**: Add `/app/upload/` route to `frontend/urls.py`
  - Files: `frontend/urls.py` — add upload import at line 9, add URL pattern after line 19
  - Details: Import the upload view module and add the URL pattern following the existing convention.
  - Updated imports (line 9):
    ```python
    from frontend.views import auth, dashboard, upload
    ```
  - Add URL pattern (after dashboard line 19):
    ```python
    # Upload
    path("upload/", upload.upload_view, name="upload"),
    ```
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from django.urls import reverse; print(reverse('frontend:upload'))"`

### Step 11: Create upload page template

- [ ] **Step 11a**: Create `frontend/templates/frontend/upload/index.html` (new file)
  - Files: `frontend/templates/frontend/upload/index.html` — new file
  - Details: Extends `frontend/base.html` following the `dashboard/index.html` pattern. Implements a drag-and-drop upload zone using Alpine.js for client-side state (drag events, file list preview) and HTMX for form submission. Includes a `{% csrf_token %}` inside the form for non-JS fallback. The form uses `enctype="multipart/form-data"` with `<input type="file" name="files" multiple>`. HTMX posts to the same URL and swaps the results into a target `div`. Non-JS fallback uses a standard form POST.
  - Template structure:
    ```html
    {% extends "frontend/base.html" %}

    {% block page_title %}Upload — Doorito{% endblock %}
    {% block page_header %}Upload Files{% endblock %}
    {% block sidebar_active %}upload{% endblock %}

    {% block page_content %}
    <div class="max-w-2xl">
      <form method="post"
            enctype="multipart/form-data"
            hx-post="{% url 'frontend:upload' %}"
            hx-target="#upload-results"
            hx-swap="innerHTML"
            x-data="uploadZone()"
            class="space-y-6">
        {% csrf_token %}

        {# Drop zone #}
        <div @dragover.prevent="dragOver = true"
             @dragleave.prevent="dragOver = false"
             @drop.prevent="handleDrop($event)"
             :class="dragOver ? 'border-primary-500 bg-primary-50' : 'border-neutral-300'"
             class="border-2 border-dashed rounded-lg p-8 text-center transition-colors cursor-pointer"
             @click="$refs.fileInput.click()">
          <input type="file"
                 name="files"
                 multiple
                 x-ref="fileInput"
                 @change="handleFiles($event)"
                 class="hidden">
          <svg class="w-12 h-12 mx-auto text-neutral-400 mb-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5" />
          </svg>
          <p class="text-neutral-600">
            <span class="font-medium text-primary-600">Click to browse</span> or drag and drop
          </p>
          <p class="text-sm text-neutral-400 mt-1">Up to 10 files, 50 MB each</p>
        </div>

        {# Selected files preview #}
        <div x-show="fileNames.length > 0" x-cloak>
          <h3 class="text-sm font-medium text-neutral-700 mb-2" x-text="`${fileNames.length} file(s) selected`"></h3>
          <ul class="space-y-1">
            <template x-for="name in fileNames" :key="name">
              <li class="text-sm text-neutral-600 flex items-center gap-2">
                <svg class="w-4 h-4 text-neutral-400 shrink-0" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" /></svg>
                <span x-text="name"></span>
              </li>
            </template>
          </ul>
        </div>

        {# Submit button #}
        <button type="submit"
                x-show="fileNames.length > 0"
                x-cloak
                class="bg-primary-600 hover:bg-primary-700 text-white font-medium py-2 px-4 rounded-lg transition-colors">
          Upload
        </button>
      </form>

      {# Results area (swapped by HTMX) #}
      <div id="upload-results" class="mt-6"></div>

      {% if messages %}
      <div class="mt-6 space-y-2">
        {% for message in messages %}
        <div class="rounded-lg p-4 text-sm
          {% if message.tags == 'success' %}bg-success-50 text-success-700 border border-success-200
          {% elif message.tags == 'warning' %}bg-warning-50 text-warning-700 border border-warning-200
          {% elif message.tags == 'error' %}bg-danger-50 text-danger-700 border border-danger-200
          {% else %}bg-info-50 text-info-700 border border-info-200{% endif %}">
          {{ message }}
        </div>
        {% endfor %}
      </div>
      {% endif %}
    </div>

    <script>
      function uploadZone() {
        return {
          dragOver: false,
          fileNames: [],
          handleDrop(event) {
            this.dragOver = false;
            this.$refs.fileInput.files = event.dataTransfer.files;
            this.updateFileNames();
          },
          handleFiles(event) {
            this.updateFileNames();
          },
          updateFileNames() {
            this.fileNames = Array.from(this.$refs.fileInput.files).map(f => f.name);
          }
        }
      }
    </script>
    {% endblock %}
    ```
  - Verify: `test -f frontend/templates/frontend/upload/index.html && echo "OK"`

- [ ] **Step 11b**: Create `frontend/templates/frontend/upload/partials/results.html` (new file)
  - Files: `frontend/templates/frontend/upload/partials/results.html` — new file
  - Details: HTMX partial returned after upload POST. Shows upload results (file list with status indicators) or error message. No `{% extends %}` — this is a fragment swapped into `#upload-results`.
  - Template:
    ```html
    {% if error %}
    <div class="rounded-lg p-4 text-sm bg-danger-50 text-danger-700 border border-danger-200">
      {{ error }}
    </div>
    {% else %}
    <div class="rounded-lg border border-neutral-200 bg-white">
      <div class="px-4 py-3 border-b border-neutral-200">
        <h3 class="text-sm font-medium text-neutral-900">
          Upload Results
          {% if failed_count == 0 %}
            <span class="ml-2 text-success-600">All {{ stored_count }} file(s) stored</span>
          {% elif stored_count > 0 %}
            <span class="ml-2 text-warning-600">{{ stored_count }} stored, {{ failed_count }} failed</span>
          {% else %}
            <span class="ml-2 text-danger-600">All {{ failed_count }} file(s) failed</span>
          {% endif %}
        </h3>
      </div>
      <ul class="divide-y divide-neutral-200">
        {% for upload in results %}
        <li class="px-4 py-3 flex items-center justify-between">
          <div class="flex items-center gap-2 min-w-0">
            <svg class="w-4 h-4 shrink-0
              {% if upload.status == 'stored' %}text-success-500
              {% elif upload.status == 'failed' %}text-danger-500
              {% else %}text-neutral-400{% endif %}"
              xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor">
              {% if upload.status == 'stored' %}
              <path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
              {% elif upload.status == 'failed' %}
              <path stroke-linecap="round" stroke-linejoin="round" d="m9.75 9.75 4.5 4.5m0-4.5-4.5 4.5M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
              {% endif %}
            </svg>
            <span class="text-sm text-neutral-700 truncate">{{ upload.original_filename }}</span>
          </div>
          <div class="text-xs text-neutral-400 shrink-0 ml-4">
            {% if upload.status == 'stored' %}
              {{ upload.size_bytes|filesizeformat }}
            {% elif upload.status == 'failed' %}
              <span class="text-danger-500">{{ upload.error_message }}</span>
            {% endif %}
          </div>
        </li>
        {% endfor %}
      </ul>
    </div>
    {% endif %}
    ```
  - Verify: `test -f frontend/templates/frontend/upload/partials/results.html && echo "OK"`

### Step 12: Add Upload link to sidebar

- [ ] **Step 12**: Add Upload navigation link to both desktop and mobile sidebars
  - Files: `frontend/templates/frontend/components/sidebar.html` — add upload link in desktop nav (after line 35) and mobile nav (after line 103)
  - Details: Add an Upload nav link following the Dashboard link pattern. Use an upload icon SVG. The active state uses `sidebar_active === 'upload'` matching the `{% block sidebar_active %}upload{% endblock %}` in the upload template.
  - Desktop nav link (insert after line 35 `</a>`, before line 37 `{# ── Add your navigation links here`):
    ```html
    {# Upload #}
    <a href="{% url 'frontend:upload' %}"
       class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors"
       :class="sidebarOpen ? '' : 'justify-center'"
       :class="'{% block sidebar_active %}{% endblock %}' === 'upload' ? 'bg-neutral-800 text-white' : 'hover:bg-neutral-800 hover:text-white'">
      <svg class="w-5 h-5 shrink-0" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5" /></svg>
      <span x-show="sidebarOpen" x-cloak>Upload</span>
    </a>
    ```
  - Mobile nav link (insert after line 103 `</a>`, before `</nav>`):
    ```html
    <a href="{% url 'frontend:upload' %}"
       class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors hover:bg-neutral-800 hover:text-white">
      <svg class="w-5 h-5 shrink-0" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5" /></svg>
      <span>Upload</span>
    </a>
    ```
  - Note: The sidebar's `:class` binding for active state uses a Django template `{% block sidebar_active %}{% endblock %}` that is evaluated at render time. Only the page that defines `{% block sidebar_active %}upload{% endblock %}` will see the active state. Other pages see an empty string, so the upload link shows the hover style. This is the existing pattern used by the Dashboard link.
  - Verify: `grep -c "frontend:upload" frontend/templates/frontend/components/sidebar.html` should return `2` (one desktop, one mobile)

### Step 13: Add `FILE_UPLOAD_EXPIRY_NOTIFY_HOURS` setting

- [ ] **Step 13**: Add pre-expiry notification setting to `boot/settings.py`
  - Files: `boot/settings.py` — add new setting in `Base` class after `FILE_UPLOAD_ALLOWED_TYPES` (after line 178)
  - Details: Add a setting that controls how many hours before TTL expiry the `file.expiring` notification fires. Default: 1 hour. With `FILE_UPLOAD_TTL_HOURS=24`, files are notified at ~23 hours, deleted at ~24 hours.
  - Setting to add:
    ```python
    FILE_UPLOAD_EXPIRY_NOTIFY_HOURS = 1  # Hours before TTL expiry to emit file.expiring
    ```
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from django.conf import settings; print(settings.FILE_UPLOAD_EXPIRY_NOTIFY_HOURS)"`

### Step 14: Create pre-expiry notification service and task

- [ ] **Step 14a**: Add `notify_expiring_files()` service function to `uploads/services/uploads.py`
  - Files: `uploads/services/uploads.py` — add new function after `finalize_batch()` (after line 254)
  - Details: Query `UploadFile` records with `status=STORED` and `created_at` older than `TTL - NOTIFY_HOURS`. For each matching file, call `emit_event()` with `event_type="file.expiring"`. Catch `IntegrityError` per-file for idempotency (the outbox unique constraint `(event_type, idempotency_key)` prevents duplicate notifications for the same file across sweep runs). Return counts.
  - Add import at top of file:
    ```python
    from django.db import IntegrityError
    ```
    Note: `IntegrityError` is from `django.db`, `transaction` is already imported.
  - Function:
    ```python
    def notify_expiring_files(ttl_hours=None, notify_hours=None):
        """Emit file.expiring events for files approaching TTL expiry.

        Queries files with status=STORED that are within notify_hours of
        their TTL expiry. Relies on the outbox idempotency constraint
        to prevent duplicate notifications across sweep runs.

        Args:
            ttl_hours: File TTL in hours. Defaults to settings.FILE_UPLOAD_TTL_HOURS.
            notify_hours: Hours before expiry to notify. Defaults to
                settings.FILE_UPLOAD_EXPIRY_NOTIFY_HOURS.

        Returns:
            dict: {"notified": int, "skipped": int}
        """
        if ttl_hours is None:
            ttl_hours = settings.FILE_UPLOAD_TTL_HOURS
        if notify_hours is None:
            notify_hours = getattr(settings, "FILE_UPLOAD_EXPIRY_NOTIFY_HOURS", 1)

        cutoff = timezone.now() - timedelta(hours=ttl_hours - notify_hours)
        expiring_qs = UploadFile.objects.filter(
            status=UploadFile.Status.STORED,
            created_at__lt=cutoff,
        )

        notified = 0
        skipped = 0
        for upload in expiring_qs.iterator():
            try:
                with transaction.atomic():
                    emit_event(
                        aggregate_type="UploadFile",
                        aggregate_id=str(upload.pk),
                        event_type="file.expiring",
                        payload={
                            "file_id": str(upload.pk),
                            "original_filename": upload.original_filename,
                            "content_type": upload.content_type,
                            "size_bytes": upload.size_bytes,
                            "sha256": upload.sha256,
                            "url": upload.file.url,
                            "expires_at": str(
                                upload.created_at + timedelta(hours=ttl_hours)
                            ),
                        },
                    )
                notified += 1
            except IntegrityError:
                skipped += 1  # Already notified (idempotency constraint)

        logger.info(
            "Expiring file notifications: %d notified, %d skipped (already notified).",
            notified,
            skipped,
        )
        return {"notified": notified, "skipped": skipped}
    ```
  - Add missing imports at top of file (after existing imports):
    ```python
    from datetime import timedelta

    from django.utils import timezone
    ```
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && python -c "from uploads.services.uploads import notify_expiring_files; print('OK')"`

- [ ] **Step 14b**: Add `notify_expiring_files_task` to `uploads/tasks.py`
  - Files: `uploads/tasks.py` — add new task after `cleanup_expired_upload_files_task` (after line 66)
  - Details: Follow existing task pattern (`@shared_task(bind=True)`, lazy imports, service delegation, structured return). The task runs hourly via celery-beat to sweep for files approaching expiry.
  - Task:
    ```python
    @shared_task(
        name="uploads.tasks.notify_expiring_files_task",
        bind=True,
        max_retries=2,
        default_retry_delay=60,
    )
    def notify_expiring_files_task(self):
        """Emit file.expiring events for files approaching TTL expiry.

        Runs hourly via celery-beat. Relies on outbox idempotency
        constraint to prevent duplicate notifications.

        Returns:
            dict: {"notified": int, "skipped": int}
        """
        from uploads.services.uploads import notify_expiring_files

        result = notify_expiring_files()
        if result["notified"] > 0:
            logger.info(
                "Notified %d expiring files, %d skipped.",
                result["notified"],
                result["skipped"],
            )
        return result
    ```
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && python -c "from uploads.tasks import notify_expiring_files_task; print('OK')"`

- [ ] **Step 14c**: Add celery-beat schedule entry
  - Files: `boot/settings.py` — add entry to `CELERY_BEAT_SCHEDULE` property (after line 170, before the closing `}`)
  - Details: Schedule the task to run every hour using `crontab(minute=0)`.
  - Entry to add:
    ```python
    "notify-expiring-files": {
        "task": "uploads.tasks.notify_expiring_files_task",
        "schedule": crontab(minute=0),
        "options": {"queue": "default"},
    },
    ```
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from django.conf import settings; print('notify-expiring-files' in settings.CELERY_BEAT_SCHEDULE)"`

### Step 15: Write tests

- [ ] **Step 15a**: Add tests for `WebhookEndpoint` model
  - Files: `common/tests/test_models.py` — add `TestWebhookEndpoint` class
  - Details: Test model creation, `__str__` method, default values (empty `event_types` list, `is_active=True`).
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest common/tests/test_models.py::TestWebhookEndpoint -v`

- [ ] **Step 15b**: Add tests for webhook delivery service
  - Files: `common/tests/test_webhook.py` — new file
  - Details: Test `compute_signature()` with known inputs. Test `deliver_to_endpoint()` using `unittest.mock.patch` on `httpx.Client.post` to mock HTTP responses (2xx success, 4xx/5xx HTTP errors, network errors/timeouts). Create `WebhookEndpoint` instances in tests. Use `make_outbox_event` fixture.
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest common/tests/test_webhook.py -v`

- [ ] **Step 15c**: Update tests for rewritten `process_pending_events()`
  - Files: `common/tests/test_services.py` — update `TestProcessPendingEvents` class
  - Details: Existing tests must be updated for the new return format (`{"processed", "delivered", "failed", "remaining"}` instead of `{"processed", "remaining"}`). Add new tests for:
    - Events delivered to matching endpoints (mock httpx)
    - Events with no matching endpoints marked DELIVERED (no HTTP calls)
    - Failed delivery increments `attempts` and sets `next_attempt_at` with backoff
    - Events exceeding `max_attempts` transition to FAILED
    - `error_message` is populated on failure
    - Inactive endpoints are excluded
    - Event type matching (exact match, empty list matches all)
  - Add `WebhookEndpoint` factory fixture to `common/tests/conftest.py`:
    ```python
    @pytest.fixture
    def make_webhook_endpoint(db):
        """Factory fixture to create WebhookEndpoint instances."""
        def _make(url="https://example.com/webhook", secret="test-secret", event_types=None, is_active=True):
            from common.models import WebhookEndpoint
            return WebhookEndpoint.objects.create(
                url=url, secret=secret, event_types=event_types or [], is_active=is_active,
            )
        return _make
    ```
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest common/tests/test_services.py::TestProcessPendingEvents -v`

- [ ] **Step 15d**: Add tests for `file.stored` outbox event in `create_upload_file`
  - Files: `uploads/tests/test_services.py` — add `TestCreateUploadFileOutboxEvent` class after `TestCreateUploadFile` (after line 123)
  - Details: Test that successful uploads emit `file.stored` outbox event with correct payload, and failed uploads do not emit. Follow PEP 0006 plan's test specification.
  - Add import: `from common.models import OutboxEvent`
  - Tests:
    - `test_stored_file_emits_outbox_event` — assert event exists with correct `aggregate_type`, `aggregate_id`, `event_type`, payload fields
    - `test_failed_file_does_not_emit_outbox_event` — oversized file does not create event
    - `test_outbox_event_idempotency_key` — key is `"UploadFile:{pk}"`
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest uploads/tests/test_services.py::TestCreateUploadFileOutboxEvent -v`

- [ ] **Step 15e**: Add tests for upload view
  - Files: `frontend/tests/test_views_upload.py` — new file
  - Details: Test the upload view with Django's test client. Tests:
    - GET `/app/upload/` returns 200 for authenticated user
    - GET `/app/upload/` redirects to login for unauthenticated user
    - POST with files creates `UploadFile` records and `UploadBatch`
    - POST with no files returns error
    - POST with >10 files returns error
    - HTMX POST returns partial HTML (check `Content-Type`, no redirect)
    - Non-HTMX POST redirects to upload page with messages
  - Use `user` fixture, `client.force_login(user)`, `SimpleUploadedFile` for test files, `tmp_path`/`settings` for `MEDIA_ROOT`.
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest frontend/tests/test_views_upload.py -v`

- [ ] **Step 15f**: Add tests for `notify_expiring_files()`
  - Files: `uploads/tests/test_services.py` — add `TestNotifyExpiringFiles` class
  - Details: Test that files within the notification window get `file.expiring` events emitted, files outside the window do not, and duplicate notifications are handled via idempotency constraint (skipped, not errored).
  - Tests:
    - `test_notifies_files_within_window` — file created >23h ago (with TTL=24h, notify=1h) gets notification
    - `test_skips_files_outside_window` — file created <23h ago does not get notification
    - `test_skips_non_stored_files` — files with status!=STORED are not notified
    - `test_duplicate_notification_skipped` — calling twice for the same file skips on second call
    - `test_event_payload_includes_expires_at` — payload has `expires_at` field
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest uploads/tests/test_services.py::TestNotifyExpiringFiles -v`

- [ ] **Step 15g**: Add tests for `retry_failed_events` admin action fix
  - Files: `common/tests/test_admin.py` — new file or add to existing
  - Details: Test that retrying a failed event resets `attempts` to 0, not just status and `next_attempt_at`.
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest common/tests/test_admin.py -v`

### Step 16: Run full test suite

- [ ] **Step 16**: Verify all tests pass
  - Details: Run the complete test suite to catch any regressions.
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest --tb=short -q`

### Step 17: Rebuild Tailwind CSS

- [ ] **Step 17**: Recompile CSS to include new template classes
  - Details: The upload template introduces new Tailwind classes that may not be in the existing compiled CSS. Run `make css` to recompile.
  - Verify: `make css && test -f static/css/main.css && echo "OK"`

## Testing

- [ ] WebhookEndpoint model tests — Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest common/tests/test_models.py::TestWebhookEndpoint -v`
- [ ] Webhook delivery service tests — Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest common/tests/test_webhook.py -v`
- [ ] Process pending events tests (rewritten) — Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest common/tests/test_services.py::TestProcessPendingEvents -v`
- [ ] Upload outbox event tests — Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest uploads/tests/test_services.py::TestCreateUploadFileOutboxEvent -v`
- [ ] Upload view tests — Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest frontend/tests/test_views_upload.py -v`
- [ ] Pre-expiry notification tests — Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest uploads/tests/test_services.py::TestNotifyExpiringFiles -v`
- [ ] Admin retry action tests — Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest common/tests/test_admin.py -v`
- [ ] Full existing test suite — Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest --tb=short -q`
- [ ] Django system check — Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check`
- [ ] Linting — Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && ruff check .`

## Rollback Plan

This PEP is rollback-safe with the following steps:

1. **Reverse migration**: The only migration is `common/migrations/0002_webhookendpoint.py`. Reverse with:
   ```bash
   source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py migrate common 0001
   ```
   Then delete the migration file.

2. **Revert `process_pending_events()`**: Restore the original placeholder implementation from `common/services/outbox.py` (no-op delivery, marks events as DELIVERED). Reset `DELIVERY_BATCH_SIZE` to 100.

3. **Revert `create_upload_file()`**: Remove the `transaction.atomic()` wrapping and `emit_event()` call. Restore the original direct `UploadFile.objects.create()` call.

4. **Remove new files**: Delete `common/services/webhook.py`, `frontend/views/upload.py`, `frontend/templates/frontend/upload/` directory.

5. **Revert modified files**: Remove upload URL from `frontend/urls.py`, remove upload links from `sidebar.html`, remove `FILE_UPLOAD_EXPIRY_NOTIFY_HOURS` from `boot/settings.py`, remove celery-beat entry for `notify-expiring-files`, remove `notify_expiring_files_task` from `uploads/tasks.py`, remove `notify_expiring_files()` from `uploads/services/uploads.py`.

6. **Revert `retry_failed_events`**: Remove `attempts=0` from the admin action's `.update()` call.

7. **Remove dependency**: Remove `httpx>=0.27` from `requirements.in` and recompile lockfiles.

8. **Existing outbox events**: Any `file.stored` or `file.expiring` events already emitted will be cleaned up by the existing `cleanup_delivered_outbox_events_task` after `OUTBOX_RETENTION_HOURS` (7 days). No manual cleanup needed.

## aikb Impact Map

- [ ] `aikb/models.md` — Add `WebhookEndpoint (TimeStampedModel)` section after OutboxEvent. Document fields (`id`, `url`, `secret`, `event_types`, `is_active`), `db_table = "webhook_endpoint"`, `Meta` ordering, `__str__` format. Update Entity Relationship Summary to show WebhookEndpoint as a standalone model in the common app.
- [ ] `aikb/services.md` — Update `common/services/outbox.py` section: change `process_pending_events` description from "marks events as delivered without calling any handler" to document three-phase delivery with webhook HTTP POST, retry with exponential backoff, and `DELIVERY_BATCH_SIZE=20`. Add new `common/services/webhook.py` section documenting `compute_signature()` and `deliver_to_endpoint()`. Update `uploads/services/uploads.py` section: document that `create_upload_file()` now emits `file.stored` outbox event, add `notify_expiring_files()` function documentation.
- [ ] `aikb/tasks.md` — Update `deliver_outbox_events_task` batch limit from 100 to 20 and return format to include `delivered` and `failed` counts. Add `notify_expiring_files_task` entry under Uploads App section (name, purpose, schedule, queue, return format). Update Current Schedule table with new `notify-expiring-files` entry (hourly crontab).
- [ ] `aikb/signals.md` — N/A (no signal changes)
- [ ] `aikb/admin.md` — Add `WebhookEndpointAdmin` section under `common/admin.py` with `list_display`, `list_filter`, `search_fields`, `readonly_fields`, `date_hierarchy`. Update `OutboxEventAdmin` `retry_failed_events` action description to note that it now also resets `attempts=0`.
- [ ] `aikb/cli.md` — N/A (no CLI changes)
- [ ] `aikb/architecture.md` — Update URL Routing to add `/app/upload/` route. Update Background Processing to mention webhook delivery and pre-expiry notification tasks. Add note about `httpx` for webhook delivery.
- [ ] `aikb/conventions.md` — N/A (no new conventions introduced; follows existing patterns)
- [ ] `aikb/dependencies.md` — Add `httpx` to Production Dependencies table: version `>=0.27`, purpose "HTTP client for webhook delivery". Note transitive deps (`httpcore`, `certifi`, `idna`, `sniffio`, `anyio`, `h11`).
- [ ] `aikb/specs-roadmap.md` — Move "upload UI" and "webhook delivery" from "What's Not Built Yet" to "What's Ready". Add "file portal pipeline (upload → webhook → pre-expiry notification)".
- [ ] `CLAUDE.md` — Add `FILE_UPLOAD_EXPIRY_NOTIFY_HOURS` to File Upload Settings table. Add `/app/upload/` to URL Structure section. Update Background Task Infrastructure to mention `notify_expiring_files_task`. Add `WebhookEndpoint` to the common app description in Django App Structure table.

## Final Verification

### Acceptance Criteria

- [ ] **`/app/upload/` page is accessible to authenticated users and renders a drag-and-drop file upload interface**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest frontend/tests/test_views_upload.py -k "test_get_upload_page" -v`

- [ ] **Files uploaded via the upload page are stored using the configured storage backend**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest frontend/tests/test_views_upload.py -k "test_post_upload" -v`

- [ ] **Upload validation enforces `FILE_UPLOAD_MAX_SIZE` and `FILE_UPLOAD_ALLOWED_TYPES` settings**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest uploads/tests/test_services.py::TestValidateFile -v`

- [ ] **`WebhookEndpoint` model exists with `url`, `secret`, `event_types`, and `is_active` fields**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from common.models import WebhookEndpoint; e = WebhookEndpoint(); print(e.url, e.secret, e.event_types, e.is_active)"`

- [ ] **`WebhookEndpointAdmin` is registered in Django admin with list display and filtering**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from django.contrib import admin; admin.autodiscover(); from common.models import WebhookEndpoint; assert WebhookEndpoint in admin.site._registry; print('OK')"`

- [ ] **`process_pending_events()` delivers events via HTTP POST to all matching active endpoints**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest common/tests/test_services.py::TestProcessPendingEvents -v`

- [ ] **Webhook requests include `X-Webhook-Signature`, `X-Webhook-Event`, and `X-Webhook-Delivery` headers**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest common/tests/test_webhook.py -k "test_deliver_to_endpoint" -v`

- [ ] **Webhook delivery respects existing retry/backoff logic**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest common/tests/test_services.py -k "retry" -v`

- [ ] **Events with no matching active endpoints are marked as DELIVERED**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest common/tests/test_services.py -k "no_matching" -v`

- [ ] **`httpx` is listed in `requirements.in` and compiled into `requirements.txt`**
  - Verify: `grep 'httpx' requirements.in && grep 'httpx' requirements.txt`

- [ ] **A `file.expiring` outbox event is emitted before TTL-based file cleanup**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest uploads/tests/test_services.py::TestNotifyExpiringFiles -v`

- [ ] **`FILE_UPLOAD_EXPIRY_NOTIFY_HOURS` setting controls notification timing (default: 1 hour)**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from django.conf import settings; assert settings.FILE_UPLOAD_EXPIRY_NOTIFY_HOURS == 1; print('OK')"`

- [ ] **Sidebar navigation includes an "Upload" link to `/app/upload/`**
  - Verify: `grep -c "frontend:upload" frontend/templates/frontend/components/sidebar.html` should return `2`

- [ ] **`python manage.py check` passes**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check`

- [ ] **All tests pass**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest --tb=short -q`

- [ ] **`aikb/` documentation is updated to reflect new components**
  - Verify: `grep -l "WebhookEndpoint\|webhook\|file.expiring\|notify_expiring" aikb/*.md | wc -l` should return at least 5 files

### Integration Checks

- [ ] **End-to-end upload → outbox event → webhook delivery workflow**
  - Steps:
    1. Create a `WebhookEndpoint` in the database (can use Django admin or shell)
    2. Upload a file via the upload page
    3. Verify `UploadFile` record with status=STORED is created
    4. Verify `OutboxEvent` with `event_type="file.stored"` is created
    5. Verify `process_pending_events()` delivers the event via HTTP POST (in eager mode, this happens synchronously during the upload request via `on_commit` → `deliver_outbox_events_task`)
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "
import django; django.setup()
from common.models import OutboxEvent, WebhookEndpoint
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
print('Integration test passed: upload + outbox event OK')
User.objects.filter(username='integ_test_0007').delete()
"`

- [ ] **Pre-expiry notification workflow**
  - Steps:
    1. Create an `UploadFile` with `created_at` set to >23 hours ago (with TTL=24h, notify=1h)
    2. Call `notify_expiring_files()`
    3. Verify `OutboxEvent` with `event_type="file.expiring"` is created with correct payload
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest uploads/tests/test_services.py::TestNotifyExpiringFiles::test_notifies_files_within_window -v`

- [ ] **Webhook delivery with no configured endpoints (no-op)**
  - Steps:
    1. Ensure no `WebhookEndpoint` records exist
    2. Create a pending `OutboxEvent`
    3. Call `process_pending_events()`
    4. Verify event is marked DELIVERED (no HTTP calls made)
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest common/tests/test_services.py -k "no_matching_endpoints" -v`

### Regression Checks

- [ ] `python manage.py check` passes
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check`
- [ ] `ruff check .` passes
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && ruff check .`
- [ ] Full test suite passes
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest --tb=short -q`
- [ ] Existing upload service tests unaffected
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest uploads/tests/ -v`
- [ ] Existing outbox tests unaffected
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest common/tests/ -v`
- [ ] Existing frontend tests unaffected
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest frontend/tests/ -v`

## Completion

- [ ] **Update `PEPs/IMPLEMENTED/LATEST.md`** — Add entry with PEP number, title, commit hash(es), and summary
- [ ] **Update `PEPs/INDEX.md`** — Remove the PEP row
- [ ] **Remove PEP directory** — Delete `PEPs/PEP_0007_file_portal_pipeline/`
