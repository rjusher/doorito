# PEP 0007: File Portal Pipeline — Research

| Field | Value |
|-------|-------|
| **PEP** | 0007 |
| **Summary** | [summary.md](summary.md) |
| **Plan** | [plan.md](plan.md) |

---

<!-- Research originally written pre-implementation. Updated 2026-02-27 with post-implementation findings after all 17 plan steps were completed. -->

## Current State Analysis

PEP 0007 is in **Implementing** status. All 17 implementation steps in plan.md are checked off (`[x]`). The codebase contains the complete implementation. What remains is the finalization phase (aikb updates, CLAUDE.md updates, PEP lifecycle closure).

### Upload Pipeline (Steps 8–12) — Implemented

- **Upload view** (`frontend/views/upload.py`): Functional at `/app/upload/`. Handles GET (render form) and POST (process files). Uses `@frontend_login_required` + `@require_http_methods(["GET", "POST"])`. Supports HTMX partial response via `request.htmx` and standard redirect with Django messages. Hard limit of `MAX_FILES_PER_REQUEST = 10`. Creates a batch via `create_batch()`, loops over files calling `create_upload_file()`, then `finalize_batch()`.
- **Upload templates**: `frontend/templates/frontend/upload/index.html` (full page with drag-and-drop Alpine.js zone) and `frontend/templates/frontend/upload/partials/results.html` (HTMX partial showing per-file status). Both follow existing template conventions.
- **URL route**: `frontend/urls.py:21` maps `upload/` to `upload.upload_view` with name `upload`.
- **Sidebar links**: Both desktop (line 38) and mobile (line 102) sidebars in `frontend/templates/frontend/components/sidebar.html` include Upload nav links.
- **`file.stored` event emission**: `uploads/services/uploads.py:114-137` wraps `UploadFile.objects.create()` and `emit_event()` in `transaction.atomic()`. Only successful uploads (status=STORED) emit events. Payload includes `file_id`, `original_filename`, `content_type`, `size_bytes`, `sha256`, `url`.

### WebhookEndpoint Model & Admin (Steps 2–3) — Implemented

- **Model** (`common/models.py:70-106`): `WebhookEndpoint(TimeStampedModel)` with fields: `id` (UUID7), `url` (URLField, max_length=2048), `secret` (CharField, max_length=255), `event_types` (JSONField, default=list), `is_active` (BooleanField, default=True). `db_table = "webhook_endpoint"`.
- **Migration**: `common/migrations/0002_webhookendpoint.py` exists and has been applied.
- **Admin** (`common/admin.py:52-60`): `WebhookEndpointAdmin` with `list_display = ("url", "is_active", "event_types", "created_at")`, filtering by `is_active` and `created_at`, search by `url`.

### Webhook Delivery Service (Steps 4–7) — Implemented

- **`common/services/webhook.py`**: Two functions:
  - `compute_signature(payload_bytes, secret)` — HMAC-SHA256 hex digest (lines 15–27)
  - `deliver_to_endpoint(client, endpoint, event)` — HTTP POST with `X-Webhook-Signature`, `X-Webhook-Event`, `X-Webhook-Delivery` headers. Returns `{"ok": bool, "status_code": int|None, "error": str}`. Handles `httpx.HTTPStatusError` and `httpx.RequestError` (lines 30–83).
- **`common/services/outbox.py`**: `process_pending_events()` (lines 81–209) fully rewritten with three-phase approach:
  1. **Fetch**: `transaction.atomic()` + `select_for_update(skip_locked=True)`, limited to `DELIVERY_BATCH_SIZE = 20`.
  2. **Deliver**: Shared `httpx.Client(timeout=WEBHOOK_TIMEOUT)` context manager. Matches events to active endpoints (`not ep.event_types or event.event_type in ep.event_types`). No matching endpoints = immediate DELIVERED. Catches `SoftTimeLimitExceeded` for graceful degradation.
  3. **Update**: Increments `attempts`, sets DELIVERED/FAILED/retry with exponential backoff (`min(60 * (2 ** (attempts - 1)), 3600)` + 10% jitter).
- **`WEBHOOK_TIMEOUT`**: `httpx.Timeout(30.0, connect=10.0)` defined in `common/services/outbox.py:19`.
- **Task logging updated**: `common/tasks.py:29-36` logs `processed`, `delivered`, `failed`, `remaining`.
- **Admin retry fix**: `common/admin.py:43` includes `attempts=0` in `retry_failed_events` action.

### Pre-Expiry Notification (Steps 13–14) — Implemented

- **Setting**: `FILE_UPLOAD_EXPIRY_NOTIFY_HOURS = 1` in `boot/settings.py` (after the upload settings block).
- **Service**: `notify_expiring_files()` in `uploads/services/uploads.py:274-330`. Queries `UploadFile.objects.filter(status=STORED, created_at__lt=cutoff)` where `cutoff = now - timedelta(hours=ttl - notify_hours)`. Uses `iterator()` for memory efficiency. Each file wrapped in `transaction.atomic()` + `emit_event()`. `IntegrityError` caught per-file for idempotency (outbox unique constraint prevents duplicates).
- **Task**: `notify_expiring_files_task` in `uploads/tasks.py:69-93`. `@shared_task(bind=True, max_retries=2, default_retry_delay=60)`.
- **Beat schedule**: `boot/settings.py:171-175` entry `"notify-expiring-files"` runs hourly via `crontab(minute=0)`.

### Dependencies (Step 1) — Implemented

- `httpx>=0.27` added to `requirements.in:34-35`.
- Lockfiles compiled (both `requirements.txt` and `requirements-dev.txt`).

### Tests (Step 15) — Implemented

All test files exist with comprehensive coverage:
- `common/tests/test_models.py:111-165` — `TestWebhookEndpoint`: 6 tests (create, str active/inactive, defaults, timestamps)
- `common/tests/test_webhook.py` — `TestComputeSignature` (3 tests) + `TestDeliverToEndpoint` (5 tests: success, HTTP error, network error, correct headers, signature verification)
- `common/tests/test_services.py:65-265` — `TestProcessPendingEvents`: 13 tests (no endpoints, skip future, batch size, counts, skip delivered/failed, delivers to matching, no matching = delivered, failed delivery backoff, exceeds max_attempts, error message, inactive excluded, exact match, empty catch-all)
- `uploads/tests/test_services.py:243-353` — `TestCreateUploadFileOutboxEvent` (3 tests) + `TestNotifyExpiringFiles` (5 tests)
- `frontend/tests/test_views_upload.py` — `TestUploadViewGet` (2), `TestUploadViewPost` (4), `TestUploadViewHtmx` (2)
- `common/tests/test_admin.py` — `TestRetryFailedEventsAction` (1 test)

### Fixtures

- `conftest.py:6-15` — `user` fixture (root level)
- `common/tests/conftest.py:9-40` — `make_outbox_event` factory fixture
- `common/tests/conftest.py:43-62` — `make_webhook_endpoint` factory fixture

---

## Key Files & Functions

### Files Modified by PEP 0007

| File | Lines | What Changed |
|------|-------|-------------|
| `common/models.py` | 70–106 | Added `WebhookEndpoint` model |
| `common/admin.py` | 6, 43, 52–60 | Added `WebhookEndpoint` import, `attempts=0` in retry action, `WebhookEndpointAdmin` |
| `common/services/outbox.py` | 1–209 | Added imports (`random`, `httpx`, `SoftTimeLimitExceeded`), `DELIVERY_BATCH_SIZE` 100→20, `WEBHOOK_TIMEOUT`, rewrote `process_pending_events()` |
| `common/tasks.py` | 29–36 | Updated logging to include `delivered`/`failed` counts |
| `uploads/services/uploads.py` | 1–330 | Added `emit_event`/`IntegrityError`/`timedelta`/`timezone` imports, wrapped success path in atomic + emit_event, added `notify_expiring_files()` |
| `uploads/tasks.py` | 69–93 | Added `notify_expiring_files_task` |
| `boot/settings.py` | ~171–175, ~209 | Added beat schedule entry, `FILE_UPLOAD_EXPIRY_NOTIFY_HOURS = 1` |
| `frontend/urls.py` | 9, 21 | Added `upload` import, `/app/upload/` route |
| `frontend/templates/frontend/components/sidebar.html` | 37–43, 102–106 | Added Upload links (desktop + mobile) |
| `requirements.in` | 34–35 | Added `httpx>=0.27` |

### New Files Created by PEP 0007

| File | Purpose |
|------|---------|
| `common/services/webhook.py` | `compute_signature()` + `deliver_to_endpoint()` |
| `common/migrations/0002_webhookendpoint.py` | Migration for `WebhookEndpoint` model |
| `frontend/views/upload.py` | Upload page view (GET + POST) |
| `frontend/templates/frontend/upload/index.html` | Upload page with drag-and-drop UI |
| `frontend/templates/frontend/upload/partials/results.html` | HTMX partial for upload results |
| `common/tests/test_webhook.py` | Tests for webhook delivery service |
| `common/tests/test_admin.py` | Tests for admin retry action |
| `frontend/tests/test_views_upload.py` | Tests for upload view |

### Key Function Signatures

- `compute_signature(payload_bytes: bytes, secret: str) -> str` — `common/services/webhook.py:15`
- `deliver_to_endpoint(client: httpx.Client, endpoint: WebhookEndpoint, event: OutboxEvent) -> dict` — `common/services/webhook.py:30`
- `process_pending_events(batch_size=DELIVERY_BATCH_SIZE) -> dict` — `common/services/outbox.py:81` — returns `{"processed", "delivered", "failed", "remaining"}`
- `notify_expiring_files(ttl_hours=None, notify_hours=None) -> dict` — `uploads/services/uploads.py:274` — returns `{"notified", "skipped"}`
- `upload_view(request) -> HttpResponse` — `frontend/views/upload.py:20`

---

## Technical Constraints

### Database Schema
- **`WebhookEndpoint`** has no FK relationships — standalone configuration model. No cascade concerns.
- **`OutboxEvent` unique constraint** `(event_type, idempotency_key)` is relied upon for `file.expiring` deduplication. Default idempotency key from `emit_event()` is `f"{aggregate_type}:{aggregate_id}"`, so `file.stored` and `file.expiring` for the same `UploadFile` coexist (different `event_type` values).
- **`select_for_update(skip_locked=True)`** in `process_pending_events()` requires PostgreSQL (SQLite doesn't support `skip_locked`). Fine since the project targets PostgreSQL 16+.

### Celery Timing Constraints
- **`CELERY_TASK_TIME_LIMIT = 300`** (5 min hard), **`CELERY_TASK_SOFT_TIME_LIMIT = 240`** (4 min soft).
- **Worst-case delivery**: 20 events × N endpoints × 30s read timeout. Mitigated by `SoftTimeLimitExceeded` catch at 240s — saves progress and exits.
- **Realistic case**: Healthy endpoints respond in <1s. Unhealthy endpoints hit 10s connect timeout. 20 × 1 × 10s = 200s, within limits.

### File Upload Constraints
- **`FILE_UPLOAD_MAX_SIZE = 52_428_800`** (50 MB) — enforced server-side by `validate_file()`.
- **Django default `DATA_UPLOAD_MAX_MEMORY_SIZE = 2_621_440`** (2.5 MB) — files above this use temp disk (handled by Django's upload handlers).
- **`MAX_FILES_PER_REQUEST = 10`** — hard-coded constant in `frontend/views/upload.py:15`.
- **Upload path**: `uploads/%Y/%m/` via `UploadFile.file` FileField. Dev: `MEDIA_ROOT` (local). Production: S3 via `django-storages`.

### Dev Mode Behavior
- **`CELERY_TASK_ALWAYS_EAGER=True`** means webhook delivery fires synchronously during the upload request (via `on_commit` → `deliver_outbox_events_task`). With no `WebhookEndpoint` configured, events are marked DELIVERED immediately (no HTTP calls).

---

## Pattern Analysis

### Patterns Followed

1. **Model pattern** (`common/models.py`): `WebhookEndpoint` follows `OutboxEvent` — inherits `TimeStampedModel`, `uuid7` PK, `DjangoJSONEncoder` for JSONField, explicit `db_table`, `Meta` with `verbose_name`/`ordering`, `__str__`.

2. **Service layer pattern** (`common/services/webhook.py`): Plain functions, logging, structured return dicts. Same approach as `common/services/outbox.py`.

3. **Task pattern** (`uploads/tasks.py`): `notify_expiring_files_task` follows `cleanup_expired_upload_files_task` — `@shared_task(bind=True, max_retries=2, default_retry_delay=60)`, lazy imports, service delegation, structured return.

4. **Admin pattern** (`common/admin.py`): `WebhookEndpointAdmin` follows `OutboxEventAdmin` — `list_display`, `list_filter`, `search_fields`, `readonly_fields`, `date_hierarchy`.

5. **View pattern** (`frontend/views/upload.py`): Follows `dashboard.py` for `@frontend_login_required` and `auth.py` for GET/POST with `@require_http_methods`. Uses `request.htmx` from `django-htmx`.

6. **Template pattern** (`frontend/templates/frontend/upload/`): `index.html` extends `frontend/base.html` using `page_title`, `page_header`, `sidebar_active`, `page_content` blocks. `partials/results.html` is standalone (no extends).

7. **Test pattern**: `@pytest.mark.django_db`, test classes, `SimpleUploadedFile`, `tmp_path`/`settings`, factory fixtures, `unittest.mock.patch` for HTTP mocking.

### Notable Implementation Details

- **Upload view status comparison** (`frontend/views/upload.py:57-58`): Uses `r.status == UploadFile.Status.STORED` (enum comparison), which is correct.
- **`WEBHOOK_TIMEOUT` duplication**: Defined in both `common/services/outbox.py:19` and `common/services/webhook.py:12`. The outbox module uses its own; the webhook module's definition is unused by `process_pending_events()`. This is dead code in `webhook.py`.
- **Sidebar active state**: The upload link uses `window.location.pathname.startsWith('/app/upload')` for JavaScript-based active state detection instead of the `sidebar_active` block comparison used by the Dashboard link. Functional deviation from the plan but works correctly.

### Patterns to Avoid
- **Module-level model imports in services**: Both `outbox.py` and `webhook.py` use lazy imports inside functions to avoid circular imports. Established pattern — maintain it.
- **Plaintext secrets**: `WebhookEndpoint.secret` stores HMAC secret as plaintext `CharField`. Standard for webhook signing (GitHub, Stripe) but worth noting.

---

## External Research

### httpx Library
- **Version**: `>=0.27` specified in `requirements.in`.
- **Usage**: Synchronous `httpx.Client` with context manager for connection pooling across events in a batch.
- **Timeout API**: `httpx.Timeout(timeout=30.0, connect=10.0)` — 30s overall, 10s for connection.
- **Error handling**: `httpx.HTTPStatusError` for 4xx/5xx (raised by `raise_for_status()`), `httpx.RequestError` base class for network errors.

### HMAC-SHA256 Webhook Signing
- Industry standard: GitHub (`X-Hub-Signature-256`), Stripe (`Stripe-Signature`), Shopify (`X-Shopify-Hmac-SHA256`).
- Implementation: `hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()`.
- Consumer verifies by recomputing with their copy of the secret.

### Webhook Delivery Best Practices
- **Idempotent consumers**: `X-Webhook-Delivery` header (event UUID) enables consumer-side deduplication.
- **Exponential backoff**: `min(60 * (2^(attempts-1)), 3600)` with 10% jitter. Sequence: 60s, 120s, 240s, 480s (capped at 3600s). With `max_attempts=5`, ~15 minutes before FAILED.
- **Fan-out**: Per-event tracking. All matching endpoints must succeed for DELIVERED. On retry, all re-tried (consumers must be idempotent).

---

## Risk & Edge Cases

### Risks in Implemented Code

1. **WEBHOOK_TIMEOUT duplication** — `common/services/outbox.py:19` and `common/services/webhook.py:12` both define `WEBHOOK_TIMEOUT`. The webhook module's copy is unused. **Risk**: Low. Dead code. Consider removing from `webhook.py` during finalization.

2. **Race condition in three-phase delivery** — Between Phase 1 (fetch + release locks) and Phase 3 (update), another worker could fetch the same PENDING events. `skip_locked=True` only helps while locks are held (Phase 1). After Phase 1 commits, locks are released and events remain PENDING. **Risk**: Medium in Production with multiple workers. Mitigated by consumer idempotency via `X-Webhook-Delivery`, 5-minute sweep interval spacing, and the fact that concurrent duplicate delivery is benign (consumers dedup and discard).

3. **Large file upload blocking** — Files uploaded through Django (server-side), not direct-to-S3. A 50 MB file blocks the WSGI worker. With `WEB_WORKERS=4`, 4 concurrent large uploads could exhaust all workers. **Risk**: Low for single-consumer portal use case. Deferred to future presigned URL PEP.

4. **`file.expiring` vs cleanup task ordering** — If `cleanup_expired_upload_files_task` runs before `notify_expiring_files_task`, files could be deleted without notification. With defaults (notify hourly, cleanup every 6h), the notify sweep runs more frequently. **Risk**: Low. Notification is documented as "best-effort, not a gate."

5. **`notify_expiring_files()` has no batch limit** — Uses `expiring_qs.iterator()` without `[:N]` slice. If thousands of files expire simultaneously, all processed in one task run. **Risk**: Low for typical use. Soft time limit (240s) provides safety net.

6. **`SoftTimeLimitExceeded` in Update phase** — If soft limit fires during Phase 3 (`transaction.atomic` block), the atomic block rolls back all updates within it. Events not yet saved lose their progress. **Risk**: Very low. Phase 3 is fast (no network I/O).

### Remaining Work (Not Yet Done)

7. **aikb documentation not updated** — The plan's aikb Impact Map lists 11 files needing updates. Verified by inspection: `aikb/tasks.md` still says `DELIVERY_BATCH_SIZE = 100` and return format `{"processed": int, "remaining": int}`; `aikb/services.md` still says `process_pending_events` "marks events as delivered without calling any handler."

8. **`CLAUDE.md` not updated** — Needs: `FILE_UPLOAD_EXPIRY_NOTIFY_HOURS` in File Upload Settings, `/app/upload/` in URL Structure, `notify_expiring_files_task` in Background Task Infrastructure, `WebhookEndpoint` in common app description.

9. **Tailwind CSS not rebuilt** — Step 17 notes `tailwindcss` CLI not installed locally. Upload templates use Tailwind classes that may not be in compiled `static/css/main.css`. **Risk**: Medium for visual correctness, none for functionality.

10. **PEP lifecycle not closed** — PEPs/INDEX.md not updated, PEPs/IMPLEMENTED/LATEST.md not updated, PEP directory not deleted.

11. **`common/tasks.py:19` docstring stale** — Says "Processes at most DELIVERY_BATCH_SIZE (100) pending events per run" but actual batch size is now 20.

---

## Recommendations

### For Finalization Phase

The implementation is code-complete with all 17 steps checked. The remaining work is finalization:

1. **Run the full test suite** to confirm all tests pass. Check `manage.py check` and `ruff check .`.

2. **Update aikb/ files** per the plan's Impact Map (lines 1060–1072):
   - `aikb/models.md`: Add `WebhookEndpoint` section after OutboxEvent
   - `aikb/services.md`: Update `process_pending_events` description, add `webhook.py` section, add `notify_expiring_files()`, update `create_upload_file()` docs
   - `aikb/tasks.md`: `DELIVERY_BATCH_SIZE` 100→20, return format update, add `notify_expiring_files_task`, update schedule table
   - `aikb/admin.md`: Add `WebhookEndpointAdmin`, update retry action description
   - `aikb/dependencies.md`: Add `httpx`
   - `aikb/architecture.md`: Add `/app/upload/` route, update background processing
   - `aikb/specs-roadmap.md`: Move items to "What's Ready"

3. **Update `CLAUDE.md`**: Add `FILE_UPLOAD_EXPIRY_NOTIFY_HOURS`, `/app/upload/`, `notify_expiring_files_task`, `WebhookEndpoint`.

4. **Fix stale docstring**: `common/tasks.py:19` — change "100" to "20" in `deliver_outbox_events_task` docstring.

5. **Clean up WEBHOOK_TIMEOUT duplication**: Consider removing unused `WEBHOOK_TIMEOUT` from `common/services/webhook.py` since `process_pending_events()` uses its own from `common/services/outbox.py`.

6. **Check `common/tests/test_tasks.py`**: Exists but was not listed in the plan's test steps. Verify it doesn't depend on the old `process_pending_events()` return format.

7. **Finalize PEP lifecycle**: Update INDEX.md, add LATEST.md entry, delete PEP directory.
