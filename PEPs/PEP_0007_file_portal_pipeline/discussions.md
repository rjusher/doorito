# PEP 0007: File Portal Pipeline — Discussions

| Field | Value |
|-------|-------|
| **PEP** | 0007 |
| **Summary** | [summary.md](summary.md) |
| **Research** | [research.md](research.md) |

---

## Open Questions

### Q1: PEP 0006 Dependency — How to Handle?

**Context**: PEP 0007 depends on PEP 0006 (S3 Upload Storage), which is still Proposed. PEP 0006 introduces two things PEP 0007 needs: (a) S3 storage backend for Production, and (b) `file.stored` outbox event emission in `create_upload_file()`.

**Options**:
1. **Implement PEP 0006 first** — cleanest separation, but delays PEP 0007
2. **Include `file.stored` emission in PEP 0007** — PEP 0007 adds the ~10-line `emit_event()` call to `create_upload_file()` itself. PEP 0006 then only needs to add S3 storage config. Upload page works in Dev with FileSystemStorage.
3. **Merge relevant parts** — PEP 0007 subsumes the outbox emission from PEP 0006

**Status**: OPEN

---

### Q2: Per-Endpoint vs Per-Event Delivery Tracking

**Context**: With multiple `WebhookEndpoint` records, an event might succeed for endpoint A but fail for endpoint B. The `OutboxEvent` model has a single `status` field — there's no per-endpoint tracking.

**Options**:
1. **Per-event tracking (simple)** — Mark DELIVERED only when ALL endpoints succeed. On retry, re-deliver to ALL endpoints. Consumers must be idempotent (use `X-Webhook-Delivery` header for deduplication).
2. **Per-endpoint tracking (precise)** — Add a `WebhookDelivery` join model (`OutboxEvent` × `WebhookEndpoint` → status, attempts, error). More complex but no duplicate deliveries.

**Research finding**: The summary.md describes a single-consumer use case ("external AI agent"). Multiple endpoints are supported but unlikely to be heavily used initially.

**Recommendation**: Option 1 (per-event) for simplicity. The `X-Webhook-Delivery` header enables consumer-side deduplication. Can add a join model later if needed.

**Status**: OPEN

---

### Q3: Delivery Batch Size with Real HTTP Calls

**Context**: Current `DELIVERY_BATCH_SIZE = 100`. With real HTTP calls (up to 30s timeout per endpoint), processing 100 events × N endpoints could exceed `CELERY_TASK_TIME_LIMIT` (300s).

**Options**:
1. **Reduce batch size** — Process 10-20 events per batch run
2. **Per-event task dispatch** — `process_pending_events()` dispatches individual `deliver_single_event_task(event_id)` tasks, one per event. Better parallelism, but more task overhead.
3. **Keep 100 but break early** — Process events one at a time, check remaining time, break if approaching the limit

**Recommendation**: Option 1 (reduce batch size to 20) is simplest. Option 2 is better for scalability but changes the architecture more significantly.

**Status**: OPEN

---

### Q4: Pre-Expiry Notification Architecture

**Context**: Files need a `file.expiring` event before TTL cleanup. The timing of notification vs deletion needs to be coordinated.

**Options**:
1. **Separate sweep task** — `notify_expiring_files_task` runs hourly, emits `file.expiring` for files within `FILE_UPLOAD_EXPIRY_NOTIFY_HOURS` of their TTL. Cleanup task runs independently.
2. **Integrated in cleanup task** — Cleanup task checks if notification was sent; if not, emit event and skip deletion until next run.
3. **Two-phase cleanup** — First run marks files as "expiring" and emits event. Second run (next interval) deletes them.

**Research finding**: Option 1 is cleanest (separation of concerns). Options 2-3 couple notification to deletion timing, which creates edge cases when tasks run at unexpected times.

**Status**: OPEN

---

### Q5: Event Type Matching in WebhookEndpoint

**Context**: `WebhookEndpoint.event_types` is a JSON list. The summary describes it as "event type patterns (e.g., `["file.stored", "file.expiring"]`)."

**Options**:
1. **Exact match only** — `event_types` contains literal event types. Empty list = match all.
2. **Wildcard support** — Support `file.*` patterns using `fnmatch` or simple string prefix matching.

**Recommendation**: Option 1 for initial implementation. Only two event types exist (`file.stored`, `file.expiring`). Wildcard matching adds complexity for no current benefit.

**Status**: OPEN
