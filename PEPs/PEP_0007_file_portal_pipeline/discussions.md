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

---

## Open Threads

### Thread: PEP 0006 Dependency — How to Handle?
- **Raised**: 2026-02-27
- **Context**: PEP 0007 depends on PEP 0006 (S3 Upload Storage), which is still Proposed. PEP 0006 introduces two things PEP 0007 needs: (a) S3 storage backend for Production, and (b) `file.stored` outbox event emission in `create_upload_file()`.
- **Options**:
  1. **Implement PEP 0006 first** — cleanest separation, but delays PEP 0007
  2. **Include `file.stored` emission in PEP 0007** — PEP 0007 adds the ~10-line `emit_event()` call to `create_upload_file()` itself, wrapped in `transaction.atomic`. PEP 0006 then only needs to add S3 storage config. Upload page works in Dev with FileSystemStorage.
  3. **Merge relevant parts** — PEP 0007 subsumes the outbox emission from PEP 0006
- **Analysis** (2026-02-27): Reviewing PEP 0006's scope, the `file.stored` event emission is a secondary feature (the primary goal is S3 storage backend). PEP 0006's discussions.md already resolved the event payload format (`file_id`, `original_filename`, `content_type`, `size_bytes`, `sha256`, `url`). Including the emission in PEP 0007 means: (a) PEP 0007 can be implemented before PEP 0006 (useful since the upload page and webhook delivery are the portal's core value), (b) PEP 0006 becomes purely a storage backend PEP (simpler scope), (c) the `file.stored` event is tested end-to-end with the webhook delivery (better integration coverage). Risk: if PEP 0006 is later implemented, it might add the same `emit_event` call, creating a conflict. Mitigation: PEP 0006's plan would need to check if the event emission already exists and skip it.
- **Recommendation**: **Option 2** — Include `file.stored` emission in PEP 0007. Amend PEP 0006's summary to remove the outbox event emission from its scope.
- **Status**: Awaiting input — decide implementation order

### Thread: Pre-Expiry Notification Architecture
- **Raised**: 2026-02-27
- **Context**: Files need a `file.expiring` event before TTL cleanup. The timing of notification vs deletion needs to be coordinated.
- **Options**:
  1. **Separate sweep task** — `notify_expiring_files_task` runs hourly, emits `file.expiring` for files within `FILE_UPLOAD_EXPIRY_NOTIFY_HOURS` of their TTL. Cleanup task runs independently.
  2. **Integrated in cleanup task** — Cleanup task checks if notification was sent; if not, emit event and skip deletion until next run.
  3. **Two-phase cleanup** — First run marks files as "expiring" and emits event. Second run (next interval) deletes them.
- **Analysis** (2026-02-27): Option 1 is cleanest for separation of concerns. The sweep query is straightforward: `UploadFile.objects.filter(status="stored", created_at__lt=cutoff_notify)` where `cutoff_notify = now - timedelta(hours=TTL - NOTIFY_HOURS)`. With defaults (TTL=24h, notify=1h), this queries files older than 23 hours. The outbox idempotency constraint prevents duplicate notifications (see design decision above). The sweep needs a celery-beat schedule entry running hourly. The cleanup task at `uploads/tasks.py` remains unchanged — it deletes files older than 24h regardless of notification status. This means: a file is notified at ~23h, then deleted at ~24h. If the notification sweep misses a run, the file is still deleted on schedule (the notification is best-effort, not a gate). Options 2-3 couple notification to deletion, creating edge cases: what if the task that emitted the event crashes before deletion? The file lingers in a "notified but not deleted" state until the next run. Option 1 avoids this coupling entirely.
- **Recommendation**: **Option 1** — Separate `notify_expiring_files_task` sweep task. Add a celery-beat schedule entry running every hour. The notification is best-effort and independent of the cleanup task.
- **Status**: Awaiting input — confirm separate task approach

### Thread: Celery eager mode and webhook HTTP calls in Dev
- **Raised**: 2026-02-27
- **Context**: In Dev, `CELERY_TASK_ALWAYS_EAGER=True` means tasks run synchronously in the same process. The flow after upload is: `create_upload_file()` → `emit_event()` → `transaction.on_commit()` → `deliver_outbox_events_task.delay()` (runs immediately) → `process_pending_events()` → HTTP POST to webhook endpoints. If a developer has configured a `WebhookEndpoint` for local testing, the HTTP call blocks the upload response.
- **Options**:
  1. **Accept and document** — With no `WebhookEndpoint` configured (the default), `process_pending_events()` finds no matching endpoints and marks the event as DELIVERED immediately (no HTTP calls). The delay only occurs if the developer has explicitly configured a webhook endpoint. This is the expected behavior for testing webhooks locally.
  2. **Skip HTTP delivery in eager mode** — Check `settings.CELERY_TASK_ALWAYS_EAGER` in `process_pending_events()` and skip real HTTP delivery. Mark events as DELIVERED immediately (current no-op behavior).
  3. **Make webhook delivery optional via setting** — Add `WEBHOOK_DELIVERY_ENABLED = False` in Dev, `True` in Production. `process_pending_events()` skips HTTP calls when disabled.
- **Analysis** (2026-02-27): Option 1 is correct. With no configured `WebhookEndpoint`, behavior is identical to today (events marked DELIVERED immediately). A developer who adds a webhook endpoint for testing *wants* the HTTP call to fire — that's the whole point of testing. The `httpx` timeout (10s connect, 30s read) bounds the worst case. Option 2 would make local webhook testing impossible without switching to non-eager Celery. Option 3 adds a setting that duplicates the "no endpoints configured" default.
- **Recommendation**: **Option 1** — Accept and document. When no `WebhookEndpoint` is configured, delivery is a no-op. When endpoints are configured, HTTP calls execute synchronously in Dev (desired for testing).
- **Status**: Awaiting input — confirm this is acceptable

### Thread: Upload view — single-file or multi-file, and max count?
- **Raised**: 2026-02-27
- **Context**: The summary describes "drag files" (plural) onto the upload zone, and the research mentions "max 10 files per request" as a suggested limit. The acceptance criteria do not specify whether the upload view accepts single or multiple files, or what the maximum count per request should be.
- **Options**:
  1. **Multi-file with max 10 per request** — `<input type="file" multiple>`, loop over `request.FILES.getlist('files')`, reject if count > 10
  2. **Multi-file with no limit** — Trust `FILE_UPLOAD_MAX_SIZE` per file and `DATA_UPLOAD_MAX_MEMORY_SIZE` per request
  3. **Single-file only** — Simpler view, loop over files client-side with separate HTMX requests
- **Analysis** (2026-02-27): The summary says "files" (plural) and the `UploadBatch` model exists specifically to group multiple files. The service layer supports batches via `create_batch()` + `create_upload_file(user, file, batch=batch)`. The view should create a batch, loop over uploaded files, create each via `create_upload_file`, then `finalize_batch`. A max count prevents abuse (e.g., uploading 1000 tiny files to overload the server). 10 is a reasonable default. This could be a setting (`FILE_UPLOAD_MAX_FILES_PER_REQUEST`) or a hardcoded constant.
- **Recommendation**: **Option 1** — Multi-file with a max of 10 per request. Add a `FILE_UPLOAD_MAX_FILES_PER_REQUEST = 10` constant in the view (not a setting — it's a guard against abuse, not a configurable business rule). Acceptance criteria should be updated to include this.
- **Status**: Awaiting input — confirm multi-file approach and max count

### Thread: Plan.md is still the template — needs planning phase
- **Raised**: 2026-02-27
- **Context**: The `plan.md` file contains only the template placeholders (context files, implementation steps, testing, rollback, aikb impact map, etc.) — none of the sections are filled in. The summary and research are detailed and complete, but there is no actionable implementation plan. The PEP workflow requires `make claude-pep-plan PEP=0007` to generate the plan from the research, followed by `make claude-pep-todo PEP=0007` to break it into granular steps.
- **Status**: Blocked — plan.md must be completed before implementation can begin. Run `make claude-pep-plan PEP=0007` to generate the implementation plan from the research findings and resolved discussions.
