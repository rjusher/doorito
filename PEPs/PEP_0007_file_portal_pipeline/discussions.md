# PEP 0007: File Portal Pipeline — Discussions

| Field | Value |
|-------|-------|
| **PEP** | 0007 |
| **Summary** | [summary.md](summary.md) |
| **Research** | [research.md](research.md) |

---

## Resolved Questions

### Q2: Per-Endpoint vs Per-Event Delivery Tracking
- **Resolved**: 2026-02-27
- **Answer**: Per-event tracking (Option 1). Mark an event as DELIVERED only when ALL matching active endpoints receive a 2xx. On retry, re-deliver to ALL matching endpoints.
- **Rationale**: The summary explicitly describes a single-consumer use case ("external AI agent"). The `OutboxEvent` model has a single `status` field with no per-endpoint state, and adding a `WebhookDelivery` join model would require a new migration, new admin UI, new test fixtures, and changes to `process_pending_events`, `cleanup_delivered_events`, and the admin `retry_failed_events` action — significant scope expansion for a feature that isn't needed yet. The `X-Webhook-Delivery` header (event UUID) enables consumer-side deduplication, which is the industry standard (GitHub, Stripe, Shopify all document that consumers should be idempotent). Duplicate delivery to a previously-successful endpoint is a benign edge case: the consumer deduplicates and discards. If fan-out to many endpoints becomes a real requirement, a `WebhookDelivery` join model can be added in a follow-up PEP without breaking the event schema.

### Q3: Delivery Batch Size with Real HTTP Calls
- **Resolved**: 2026-02-27
- **Answer**: Reduce `DELIVERY_BATCH_SIZE` from 100 to 20 (Option 1).
- **Rationale**: Worst-case analysis: 20 events x 1 endpoint x 30s read timeout = 600s, which exceeds `CELERY_TASK_TIME_LIMIT` (300s). However, this worst case requires ALL 20 endpoints to be unreachable and all hitting the full 30s read timeout. In practice, healthy endpoints respond in <1s and unhealthy ones hit the 10s connect timeout. Realistic worst case: 20 events x 1 endpoint x 10s connect timeout = 200s, well within the 300s limit. With 2 endpoints: 20 x 2 x 10s = 400s, which exceeds the limit. **Mitigation**: batch size of 20 combined with early-exit on `SoftTimeLimitExceeded` (240s soft limit). The task catches the soft limit exception, saves progress (updates attempted events), and returns. Remaining events are picked up by the next sweep (5 min interval) or by a new `on_commit` dispatch. This is simpler than per-event task dispatch (Option 2) and avoids the task queue overhead of dispatching hundreds of individual tasks during backlogs. The batch size can be tuned later via a constant — it's a one-line change.

### Q5: Event Type Matching in WebhookEndpoint
- **Resolved**: 2026-02-27
- **Answer**: Exact match only (Option 1). Empty `event_types` list (or `[]`) matches all events.
- **Rationale**: Only two event types exist in the system: `file.stored` (from PEP 0006) and `file.expiring` (from this PEP). Wildcard matching (`file.*`, `fnmatch`) adds code paths, test cases, and documentation for a feature with zero current demand. The matching logic is a simple `if not endpoint.event_types or event.event_type in endpoint.event_types` — clean and obvious. If wildcards are needed later (e.g., many event types with a naming hierarchy), the matching function can be extended without changing the model schema (the JSON list format supports any string, including future wildcards). The operator can simply list both event types explicitly: `["file.stored", "file.expiring"]`.

### Q6: PEP 0006 Dependency — How to Handle?
- **Resolved**: 2026-02-27
- **Answer**: Option 2 — Include `file.stored` emission in PEP 0007. PEP 0006 focuses solely on S3 storage backend.
- **Rationale**: PEP 0007 added the `emit_event()` call to `create_upload_file()` in `uploads/services/uploads.py:114-137`, wrapped in `transaction.atomic()`. This was the correct choice: (a) PEP 0007's upload page + webhook delivery + `file.stored` event forms a testable end-to-end pipeline, (b) PEP 0006 was separately finalized as a pure storage backend PEP (commit `b7b22ff`), (c) the `file.stored` event is tested end-to-end with webhook delivery, providing better integration coverage. No conflict arose because PEP 0006 was finalized without the event emission.

### Q7: Pre-Expiry Notification Architecture
- **Resolved**: 2026-02-27
- **Answer**: Option 1 — Separate `notify_expiring_files_task` sweep task running hourly via celery-beat.
- **Rationale**: Clean separation of concerns. The sweep query (`UploadFile.objects.filter(status="stored", created_at__lt=cutoff)`) runs independently of the cleanup task. The notification is best-effort, not a gate on deletion — if the sweep misses a run, the cleanup task still deletes files on schedule. The outbox idempotency constraint prevents duplicate notifications across sweep runs. Options 2-3 (integrating notification into the cleanup task) were rejected because they couple notification to deletion, creating edge cases where a crash between notification and deletion leaves files in a limbo state.

### Q8: Celery Eager Mode and Webhook HTTP Calls in Dev
- **Resolved**: 2026-02-27
- **Answer**: Option 1 — Accept and document. No special-casing for eager mode.
- **Rationale**: With no `WebhookEndpoint` configured (the default in Dev), `process_pending_events()` finds no matching endpoints and marks events as DELIVERED immediately — zero HTTP calls, no behavioral change from the pre-PEP-0007 placeholder. A developer who adds a webhook endpoint for testing explicitly wants the HTTP call to fire. Skipping delivery in eager mode (Option 2) would make local webhook testing impossible without switching to non-eager Celery.

### Q9: Upload View — Single-File or Multi-File, and Max Count?
- **Resolved**: 2026-02-27
- **Answer**: Option 1 — Multi-file with max 10 per request.
- **Rationale**: The summary says "files" (plural) and the `UploadBatch` model exists to group multiple files. The view creates a batch, loops over uploaded files, and finalizes. `MAX_FILES_PER_REQUEST = 10` is a hardcoded constant in `frontend/views/upload.py:15` (not a settings variable — it's a guard against abuse, not a configurable business rule). The `<input type="file" multiple>` element and drag-and-drop zone support multiple file selection.

### Q10: Plan.md Template Status
- **Resolved**: 2026-02-27
- **Answer**: Plan.md was completed during the `claude-pep-plan` and `claude-pep-todo` phases, with all 17 implementation steps and a detailed todo checklist. All steps are now checked off (`[x]`).
- **Rationale**: This thread was raised when plan.md was still the template placeholder. It was subsequently filled in and the implementation was completed.

### Q11: HTMX "Progress Feedback" — Result Swap vs Real-Time Progress Bar
- **Resolved**: 2026-02-27
- **Answer**: HTMX provides post-upload result swapping, not a real-time byte-level progress bar during upload. This is correct and intentional.
- **Rationale**: The summary states "HTMX provides progress feedback without full-page reloads." The implementation uses HTMX `hx-post` with `hx-target="#upload-results"` and `hx-swap="innerHTML"` to swap upload results (per-file status indicators) into the page after the server finishes processing — no full-page reload needed. This is not a real-time progress bar during the upload itself. A real-time progress bar would require JavaScript `XMLHttpRequest` progress events or `fetch` with `ReadableStream`, which is outside HTMX's capabilities. For files ≤50 MB (the `FILE_UPLOAD_MAX_SIZE` limit), the browser's native upload progress indication is sufficient, and the HTMX result swap provides immediate feedback on success/failure without navigation. The term "progress feedback" in the summary refers to the overall UX improvement (no full-page reload), not a specific progress bar widget.

### Q12: Event Payload `url` Field — Dev vs Production Format
- **Resolved**: 2026-02-27
- **Answer**: Accept the environment-dependent URL format. `upload.file.url` delegates to Django's configured storage backend, producing the appropriate URL for each environment.
- **Rationale**: The `file.stored` and `file.expiring` event payloads include `"url": upload.file.url`. In dev mode (`FileSystemStorage`), this produces a relative URL like `/media/uploads/2026/02/file.pdf`. In production (`S3Boto3Storage`), this produces a presigned S3 URL or a direct S3 URL depending on `AWS_QUERYSTRING_AUTH`. The external webhook consumer (the AI agent sharing the S3 bucket) operates in the production environment and receives the S3 URL it needs. In dev mode, the URL is useful only for local testing — an external consumer wouldn't be configured in dev anyway (no `WebhookEndpoint` records by default). This is the standard Django storage abstraction working as designed: the same code produces environment-appropriate URLs without conditional logic.

---

## Design Decisions

### Decision: Upload view returns HTMX partial or full redirect based on request type
- **Date**: 2026-02-27
- **Context**: The upload page uses HTMX for progress feedback (per summary.md). The view needs to handle both HTMX POST requests (from the drag-and-drop interface with JavaScript enabled) and standard form POST requests (non-JS fallback). The response format differs: HTMX expects an HTML fragment to swap into the page; standard POST expects a redirect or full-page render.
- **Decision**: Use `request.htmx` (from `django-htmx` middleware, already installed) to detect HTMX requests. On HTMX POST success, return an HTML fragment with upload results (file list, status indicators) that is swapped into the upload zone via `hx-swap`. On standard POST success, redirect back to the upload page with a success message via Django messages framework. On validation error (both paths), return the error in the appropriate format. This matches the pattern in `auth.py` where POST handling returns either a redirect or re-renders the form with errors.
- **Alternatives rejected**:
  - **HTMX-only (no non-JS fallback)**: Would break the upload page for users with JavaScript disabled. The existing frontend (login, register) works without JS.
  - **JSON API responses**: Inconsistent with the server-rendered HTMX pattern used throughout the frontend app.

### Decision: Admin `retry_failed_events` action must reset `attempts` to 0
- **Date**: 2026-02-27
- **Context**: The existing `retry_failed_events` admin action (`common/admin.py:40-48`) resets `status` to PENDING, sets `next_attempt_at` to now, and clears `error_message` — but does NOT reset `attempts` to 0. When PEP 0007 implements retry logic that transitions events to FAILED when `attempts >= max_attempts`, a manually retried event would start with its existing attempt count. If the event was at `max_attempts` (5), the delivery task would immediately re-fail it.
- **Decision**: PEP 0007's implementation must also update the `retry_failed_events` admin action to reset `attempts=0` alongside the existing field resets. This is a one-line addition to the `.update()` call. Without this fix, the admin retry feature becomes non-functional after PEP 0007 adds real retry logic.
- **Alternatives rejected**:
  - **Leave `attempts` as-is**: Breaks the admin retry feature silently. Admin users would click "Retry" and the event would immediately fail again.

### Decision: Use synchronous `httpx.Client` in a shared context manager per batch
- **Date**: 2026-02-27
- **Context**: `httpx` can be used with `httpx.post()` (creates a new connection per call) or `httpx.Client()` (connection pooling, reuses connections). Since events may be delivered to the same endpoint URL repeatedly within a batch, connection reuse improves throughput.
- **Decision**: Create a single `httpx.Client(timeout=httpx.Timeout(connect=10.0, read=30.0))` instance per `process_pending_events()` call using a `with` statement. This pools connections across events targeting the same endpoint within the batch. The client is closed at the end of the batch. Async `httpx.AsyncClient` is NOT used because Celery prefork workers run synchronous code.
- **Alternatives rejected**:
  - **Per-request `httpx.post()`**: No connection reuse. Higher latency per call. Acceptable but suboptimal.
  - **Module-level global client**: Connection pool persists across task invocations, but hard to manage lifecycle in Celery workers. Client could hold stale connections.
  - **Async httpx with `asyncio.run()`**: Adds complexity, incompatible with Celery's prefork pool, and provides no benefit since we're not making concurrent requests within a single event delivery.

### Decision: `file.expiring` event avoids duplicates via outbox idempotency constraint
- **Date**: 2026-02-27
- **Context**: If the pre-expiry sweep task runs hourly and a file is within the notification window for multiple consecutive hours, the sweep could attempt to emit duplicate `file.expiring` events for the same file.
- **Decision**: Rely on the existing `OutboxEvent` unique constraint on `(event_type, idempotency_key)`. The `emit_event()` call uses `idempotency_key="UploadFile:{pk}"` by default. The first sweep emits `(event_type="file.expiring", idempotency_key="UploadFile:{pk}")` successfully. Subsequent sweeps for the same file hit an `IntegrityError` on the unique constraint. The sweep task should catch `IntegrityError` per-file and log a debug message (not warning — it's expected behavior), then continue to the next file.
- **Alternatives rejected**:
  - **Add a `notified_at` timestamp to `UploadFile`**: New migration, new field, couples the upload model to the notification concern. Over-engineered.
  - **Query outbox to check for existing events before emitting**: Extra database query per file. The unique constraint is more efficient and race-condition-proof.

### Decision: Webhook delivery happens outside `select_for_update` transaction
- **Date**: 2026-02-27
- **Context**: The current `process_pending_events()` holds `select_for_update` row locks while iterating through events (all within a single `transaction.atomic()` block). When PEP 0007 adds real HTTP calls, holding locks during network I/O would block concurrent workers and risk lock timeouts on slow webhook endpoints.
- **Decision**: Split `process_pending_events()` into three phases:
  1. **Fetch phase** (`transaction.atomic` + `select_for_update`): Lock and fetch up to `batch_size` pending events. Collect their PKs and data. Transaction commits, releasing locks.
  2. **Delivery phase** (no transaction): For each event, find matching `WebhookEndpoint` records, POST to each, collect results.
  3. **Update phase** (`transaction.atomic`): For each event, update status based on delivery results (DELIVERED, retry with backoff, or FAILED).
  Phases 1 and 3 are short transactions. Phase 2 is the long operation (network I/O) and holds no database locks. This prevents lock contention between concurrent workers.
- **Alternatives rejected**:
  - **Keep single transaction**: Holds row locks during HTTP calls. Blocks other workers. Risks exceeding lock timeout on slow endpoints.
  - **Process events one at a time in separate transactions**: More transaction overhead, but simpler. Acceptable alternative but less efficient for batched processing.

### Decision: Sidebar upload link uses JavaScript-based active state detection
- **Date**: 2026-02-27
- **Context**: The plan (Step 12) specified using `{% block sidebar_active %}` (Django template block comparison) for the upload link's active state, matching the Dashboard link pattern. The implementation instead uses `window.location.pathname.startsWith('/app/upload')` in Alpine.js `:class` binding.
- **Decision**: The implementation deviated from the plan. The JavaScript-based approach works correctly — the upload link shows active styling only on the upload page. However, it's inconsistent with the Dashboard link (line 32) which uses `'{% block sidebar_active %}' === 'dashboard'`. The functional impact is negligible: both approaches produce the correct active state. The JavaScript approach is arguably more robust (works for nested routes like `/app/upload/foo/`) but breaks the established convention.
- **Note**: The mobile sidebar (line 98) has a separate issue — the Dashboard link has hardcoded `bg-neutral-800 text-white` classes, making it always appear active regardless of the current page. The upload mobile link (line 103) has only hover styles. This means on the upload page, the Dashboard link still appears active in mobile.

### Decision: `WebhookEndpoint.secret` stored as plaintext CharField
- **Date**: 2026-02-27
- **Context**: The `WebhookEndpoint.secret` field is a `CharField(max_length=255)` storing the HMAC signing key as plaintext. This means anyone with database read access or Django admin access can see the shared secret. The question is whether secrets should be encrypted at rest or hashed.
- **Decision**: Store as plaintext. This is the industry standard for webhook HMAC signing secrets. The server needs the raw secret value at runtime to compute `hmac.new(secret.encode(), payload, sha256)` — hashing would make it unusable. Encryption at rest (e.g., `django-encrypted-model-fields`) adds a dependency and key management complexity for minimal security benefit: an attacker with database access could also read the `OutboxEvent` payloads directly. The threat model for webhook signing is request authenticity verification (consumer confirms requests come from Doorito), not secret confidentiality at rest.
- **Alternatives rejected**:
  - **Encrypted field**: Adds dependency, key management, and complexity. The secret isn't a credential (it doesn't grant access to anything) — it's a signing key for payload integrity verification.
  - **Hashed field**: Incompatible with HMAC computation, which requires the raw secret.

---

## Open Threads

### Thread: Stale docstring in `deliver_outbox_events_task`
- **Raised**: 2026-02-27
- **Context**: `common/tasks.py:17-24` has a stale docstring that says "Processes at most DELIVERY_BATCH_SIZE (100) pending events per run" (actual is 20) and documents the return type as `{"processed": int, "remaining": int}` (actual is `{"processed": int, "delivered": int, "failed": int, "remaining": int}`). The logging at lines 29-36 was correctly updated but the docstring was not.
- **Impact**: Low — code comments only. No runtime effect. Could mislead developers reading the source.
- **Recommendation**: Update docstring to match actual behavior: batch size 20, return format with `delivered` and `failed` fields.
- **Status**: Fix during finalization
<!-- Review: Update docstring to match actual  -->

### Thread: Unused `WEBHOOK_TIMEOUT` in `common/services/webhook.py`
- **Raised**: 2026-02-27
- **Context**: `WEBHOOK_TIMEOUT` is defined in both `common/services/outbox.py:19` and `common/services/webhook.py:12`. The `process_pending_events()` function in `outbox.py` creates its own `httpx.Client(timeout=WEBHOOK_TIMEOUT)` using its local constant. The `deliver_to_endpoint()` function in `webhook.py` receives a pre-configured `client` parameter and never references `webhook.py`'s `WEBHOOK_TIMEOUT`. The constant in `webhook.py:12` is dead code.
- **Impact**: Low — dead code. No runtime effect. Minor confusion if a developer assumes `webhook.py`'s timeout is being used.
- **Recommendation**: Remove `WEBHOOK_TIMEOUT` from `common/services/webhook.py`. The canonical timeout is in `common/services/outbox.py` where `httpx.Client` is instantiated.
- **Status**: Fix during finalization
<!-- Review: Follow recommendations -->

### Thread: httpx.Timeout constructor semantics — plan vs implementation
- **Raised**: 2026-02-27
- **Context**: The plan (Step 5) specifies `httpx.Timeout(connect=10.0, read=30.0)` while the actual implementation at `common/services/outbox.py:19` uses `httpx.Timeout(30.0, connect=10.0)`. These produce different timeout configurations:
  - Plan: `pool=5s, connect=10s, read=30s, write=5s` (keyword-only args, defaults for pool/write)
  - Implementation: `pool=30s, connect=10s, read=30s, write=30s` (positional arg sets all defaults, connect overridden)
  Both result in the critical timeouts being identical: connect=10s, read=30s. The difference is in pool and write timeouts (5s vs 30s), which are unlikely to matter for webhook delivery.
- **Impact**: Very low — both configurations produce the desired connect=10s, read=30s behavior. The 30s pool/write timeouts in the implementation are more lenient than the plan's 5s defaults.
- **Recommendation**: Accept the implementation as-is. The `httpx.Timeout(30.0, connect=10.0)` form is clearer about intent ("everything is 30s except connect at 10s") than the keyword-only form. No change needed.
- **Status**: Resolved — no action required

### Thread: Mobile sidebar Dashboard link always appears active
- **Raised**: 2026-02-27
- **Context**: In the mobile sidebar (`sidebar.html:97-101`), the Dashboard link has hardcoded `bg-neutral-800 text-white` class — it always displays as active regardless of the current page. The Upload link (line 102-106) has only `hover:bg-neutral-800 hover:text-white` (hover styles, never active). When a user is on the upload page in mobile view, the Dashboard link still appears active and the Upload link does not.
- **Impact**: Low — visual inconsistency in mobile view only. Not a functional bug.
- **Recommendation**: Either apply the same `window.location.pathname` JavaScript approach used for the desktop upload link, or refactor both mobile nav links to use the `sidebar_active` block pattern. This is a cosmetic issue that can be addressed in finalization or a follow-up.
- **Status**: Fix during finalization (cosmetic)

### Thread: Race condition in three-phase delivery (multi-worker production)
- **Raised**: 2026-02-27
- **Context**: Between Phase 1 (fetch + release locks) and Phase 3 (update), events remain in PENDING status with their original `next_attempt_at`. If another Celery worker runs `process_pending_events()` during Phase 2 (delivery), it could fetch the same events because `skip_locked=True` only helps while locks are held — after Phase 1 commits, locks are released. This could result in duplicate webhook deliveries for the same event.
- **Options**:
  1. **Accept with consumer-side deduplication** — `X-Webhook-Delivery` header (event UUID) enables consumers to dedup. The 5-minute sweep interval makes concurrent execution unlikely in practice. Duplicate delivery is benign for idempotent consumers.
  2. **Update status to IN_PROGRESS in Phase 1** — Add an intermediate status to prevent re-fetch. Requires model migration to add the status choice.
  3. **Update `next_attempt_at` to far future in Phase 1** — Set `next_attempt_at` to a time far enough in the future to prevent re-fetch during delivery. Reset in Phase 3 on failure.
- **Analysis**: Option 1 was implicitly chosen during implementation. The sweep interval (5 min default), batch size (20), and typical delivery speed (<1s per event) make concurrent duplicate delivery extremely unlikely. When it does happen, consumers handle it via the `X-Webhook-Delivery` header. Option 3 would be a low-cost improvement but adds complexity for a theoretical issue.
- **Recommendation**: Option 1 is acceptable for the current single-consumer use case. Document the behavior. If multi-worker production deployments encounter duplicate deliveries, Option 3 is the simplest fix.
- **Status**: Accepted — no change needed for current scope. Document as known behavior.

### Thread: Tailwind CSS compilation required for upload page visual correctness
- **Raised**: 2026-02-27
- **Context**: Plan Step 17 notes that the `tailwindcss` standalone CLI is not installed locally, so `make css` fails. The upload templates (`upload/index.html`, `upload/partials/results.html`) introduce Tailwind utility classes that may not be in the compiled `static/css/main.css`. Classes include: `border-dashed`, `bg-primary-50`, `border-primary-500`, `bg-success-50`, `text-success-700`, `bg-danger-50`, `text-danger-700`, `bg-warning-50`, `text-warning-700`, and Alpine.js-related `x-cloak`. The existing `static/css/main.css` was compiled before the upload templates existed.
- **Impact**: Medium for visual correctness — the upload page may render without proper styling (missing borders, colors, spacing). No functional impact (uploads still work, HTMX still swaps content).
- **Options**:
  1. **Install tailwindcss CLI and rebuild** — `make tailwind-install && make css`. One-time setup, ~40 MB download. Resolves the issue permanently.
  2. **Defer to deployment** — The Docker build or CI pipeline likely runs `make css` as part of the build process. The dev environment is for functional testing, not pixel-perfect styling.
  3. **Add inline styles as fallback** — Add critical inline styles to the upload templates so they render acceptably without Tailwind. Over-engineered.
- **Recommendation**: Option 1 (install and rebuild) during finalization if the dev environment is used for visual testing. Option 2 is acceptable if styling review happens in staging/production.
- **Status**: Awaiting finalization — needs human decision on whether to install tailwindcss CLI locally

### Thread: Plan's Detailed Todo List unchecked despite completed implementation
- **Raised**: 2026-02-27
- **Context**: The plan contains two parallel tracking structures: (a) **Implementation Steps** (Steps 1–17, lines 62–1021) — all checked off (`[x]`), and (b) **Detailed Todo List** (Phases 1–6, lines 1185–1399) — all unchecked (`[ ]`). The Todo List was generated by `claude-pep-todo` as a more granular breakdown of the same work. During implementation (`claude-pep-implement`), only the Implementation Steps were checked. The Todo List was never updated.
- **Impact**: Very low — documentation hygiene only. Could confuse a reader who sees unchecked items and thinks work is incomplete. The Implementation Steps are the authoritative tracking structure.
- **Recommendation**: Either check off the Detailed Todo List items to match completed work, or add a note at the top of the Todo List section stating it was superseded by the Implementation Steps. Alternatively, remove the Todo List entirely since the Implementation Steps are more detailed and already contain verification commands.
- **Status**: Fix during finalization (documentation cleanup)
