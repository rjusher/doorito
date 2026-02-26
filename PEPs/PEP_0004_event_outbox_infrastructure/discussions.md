# PEP 0004: Event Outbox Infrastructure — Discussions

| Field | Value |
|-------|-------|
| **PEP** | 0004 |
| **Summary** | [summary.md](summary.md) |

---

## Resolved Questions

### Q1: Should the model use `uuid_utils.uuid7` directly or the `common.utils.uuid7` wrapper?

- **Resolved**: 2026-02-26
- **Answer**: Use `common.utils.uuid7` (the wrapper), not `uuid_utils.uuid7` directly.
- **Rationale**: The summary's model definition shows `default=uuid_utils.uuid7`, but all existing models in the project (`UploadBatch`, `UploadFile`, `UploadSession`, `UploadPart`) use `from common.utils import uuid7` and `default=uuid7`. Per `aikb/conventions.md`: "`uuid_utils.UUID` is NOT a subclass of `uuid.UUID` — always use the wrapper, never call `uuid_utils.uuid7()` directly in model defaults." The summary's example code is inconsistent with established conventions.

### Q2: What should the `db_table` be for `OutboxEvent`?

- **Resolved**: 2026-02-26
- **Answer**: `db_table = "outbox_event"`
- **Rationale**: Project convention uses lowercase snake_case matching the model name. All existing models follow this pattern: `UploadBatch` → `"upload_batch"`, `UploadFile` → `"upload_file"`, etc. `OutboxEvent` → `"outbox_event"` is consistent.

### Q3: Does `common/services/` exist yet?

- **Resolved**: 2026-02-26
- **Answer**: No. The `common` app has no `services/` directory. The plan needs to create `common/services/__init__.py` before creating `common/services/outbox.py`.
- **Rationale**: Verified via codebase inspection. The `uploads` app has `uploads/services/` with `__init__.py`, `uploads.py`, and `sessions.py`. The `common` app currently only has `__init__.py`, `apps.py`, `fields.py`, `models.py`, and `utils.py`. This is a minor but necessary prerequisite step missing from the plan.

### Q4: Does `common/admin.py` exist yet?

- **Resolved**: 2026-02-26
- **Answer**: No. The `common` app has no `admin.py`. The plan needs to create this file.
- **Rationale**: Verified via codebase inspection. The file does not exist. The `uploads` app has `uploads/admin.py` which serves as the pattern reference for admin class structure.

### Q5: What are the full `Status` TextChoices values?

- **Resolved**: 2026-02-26
- **Answer**: Four statuses: `PENDING`, `DELIVERED`, `FAILED`, `EXPIRED`. Drop the `SENDING` status.
- **Rationale**: The summary shows `# pending → sending → delivered / failed` in a comment, but `SENDING` is unnecessary complexity for a polling-based system. The delivery task processes events one at a time within a single task execution — there's no meaningful window where an event is "being sent" that would need to be tracked. If the task crashes mid-processing, the event should remain `PENDING` and be retried, not stuck in `SENDING` forever (which would require a separate cleanup mechanism). `EXPIRED` covers events that exceeded `max_attempts` (clearer than overloading `FAILED` for both transient and permanent failures). Lifecycle: `pending → delivered` (success) or `pending → failed → ... → expired` (exhausted retries).

### Q6: What is the relationship between PEP 0003's status ("Implemented") and PEP 0004's dependency on it?

- **Resolved**: 2026-02-26
- **Answer**: The dependency is satisfied. PEP 0003 is fully implemented (commit `56767cc`).
- **Rationale**: The uploads app models are in place, `uuid_utils` is installed, and the first consumer context (emitting `file.stored` events) is ready. The prerequisite checkbox in the plan can be considered met.

### Q7: Where should tests go for the `common` app?

- **Resolved**: 2026-02-26
- **Answer**: Create `common/tests/` directory with `__init__.py`, `test_models.py`, `test_services.py`, and `test_tasks.py`, following the `uploads/tests/` pattern.
- **Rationale**: The `uploads` app uses a `tests/` package (directory with `__init__.py` and separate test modules per concern). The `common` app has no tests directory yet. Following the same structure ensures consistency. Test modules should use `pytest` with `@pytest.mark.django_db`, matching the existing `uploads/tests/` style.

### Q8: What backoff algorithm should the delivery worker use?

- **Resolved**: 2026-02-26
- **Answer**: Exponential backoff: `next_attempt_at = now() + base_delay * (2 ** attempts)`, with `base_delay = 60 seconds` and a cap at 1 hour.
- **Rationale**: Exponential backoff is standard for retry mechanisms. With base 60s and max 5 attempts: retry 1 at +1m, retry 2 at +2m, retry 3 at +4m, retry 4 at +8m, retry 5 at +16m. Capping at 1 hour prevents extremely long delays if `max_attempts` is increased. This is simple, well-understood, and avoids thundering herd problems.

## Design Decisions

### Decision: No Celery Beat — delivery task invoked on-demand via `apply_async` after emission

- **Date**: 2026-02-26
- **Context**: The plan says "Register periodic task in Celery beat schedule" (Step 6), but there is no Celery Beat infrastructure configured anywhere in the project. `settings.py` has no `CELERY_BEAT_SCHEDULE`, and `celery-beat` is not in `Procfile.dev` or `docker-compose.yml`. Additionally, the existing cleanup task is documented as "Not scheduled — must be invoked manually or via celery-beat (to be configured in a future PEP)." Setting up Celery Beat is infrastructure work that goes beyond this PEP's scope.
- **Decision**: Use on-demand task dispatch instead of periodic polling. After `emit_event()` creates an outbox entry, it schedules the delivery task via `deliver_outbox_events_task.apply_async()` (or `transaction.on_commit()` to ensure the event is committed first). This eliminates the need for a beat schedule and provides lower-latency delivery. A "sweep" management command or manual task invocation can catch any missed events.
- **Future enhancement**: The project already uses PostgreSQL as the Celery broker (`sqla+postgresql://`), making `django-celery-beat` with its database scheduler a natural fit for periodic task scheduling. A future PEP should introduce celery-beat infrastructure (add `django-celery-beat` dependency, `CELERY_BEAT_SCHEDULE` in settings, beat process in Docker/Procfile) and register a periodic sweep task that catches any outbox events missed by on-demand dispatch (e.g., worker down when `on_commit` fired). This PEP focuses on the on-demand path; celery-beat complements it rather than replaces it.
- **Alternatives rejected**:
  - **Celery Beat as sole delivery mechanism (periodic polling only)**: Adds latency (events wait until the next poll interval) and requires setting up beat infrastructure. On-demand dispatch provides near-instant delivery.
  - **Django management command on cron**: External scheduling dependency, harder to configure in Docker environments.

### Decision: `error_message` stores only the last error, not error history

- **Date**: 2026-02-26
- **Context**: The `error_message` field is a `TextField`. It could store a cumulative log of all errors across attempts, or just the latest error.
- **Decision**: Store only the latest error message. Each retry overwrites the previous `error_message`.
- **Alternatives rejected**:
  - **Accumulating error log**: Adds complexity, grows unboundedly, and duplicates information available in application logs. The outbox is an infrastructure table, not an audit log. If detailed error history is needed, it belongs in structured logging or a dedicated error-tracking system.

### Decision: Concurrency-safe processing with `select_for_update(skip_locked=True)`

- **Date**: 2026-02-26
- **Context**: Multiple Celery workers could pick up the same pending event simultaneously. The plan doesn't address concurrent processing.
- **Decision**: The delivery task should use `select_for_update(skip_locked=True)` when querying pending events. This PostgreSQL feature allows workers to skip rows already locked by another worker, enabling safe concurrent processing without deadlocks. Events are processed one at a time within the `select_for_update` block, status updated atomically.
- **Alternatives rejected**:
  - **Single-worker constraint**: Limits throughput and creates a single point of failure.
  - **Advisory locks**: More complex, harder to reason about, and PostgreSQL row-level locking is sufficient.
  - **Optimistic locking (version field)**: Adds a field and retry-on-conflict logic unnecessarily.

### Decision: `emit_event()` should use `transaction.on_commit()` to schedule delivery

- **Date**: 2026-02-26
- **Context**: The summary says events are created "within the same database transaction as the state change." The delivery task must not fire before the transaction commits (otherwise it would find no event). The service needs to coordinate the outbox write and the async delivery dispatch.
- **Decision**: `emit_event()` writes the `OutboxEvent` row (participates in the caller's transaction) and registers `deliver_outbox_events_task.delay()` via `transaction.on_commit()`. This ensures the delivery task only fires after the event is actually committed. In eager mode (Dev), `on_commit` fires immediately after the outermost atomic block exits, which is correct behavior.
- **Alternatives rejected**:
  - **Caller manually dispatches task**: Error-prone — every caller must remember to trigger delivery.
  - **Signal on `OutboxEvent.post_save`**: Hidden coupling, and `post_save` fires before transaction commit in most cases (same problem).

## Open Threads

### Thread: Handler registration mechanism

- **Raised**: 2026-02-26
- **Context**: The summary says events are delivered "via configurable handler functions (registered per `event_type`)" but provides no design for how handlers are registered. This is the core extensibility mechanism of the outbox and needs a clear interface before implementation.
- **Options**:
  1. **Django setting**: `OUTBOX_HANDLERS = {"file.stored": "uploads.handlers.on_file_stored"}` — handlers are dotted import paths in settings. Simple, familiar Django pattern, but requires imports at settings load time or lazy resolution.
  2. **Registry with decorator**: `@outbox_handler("file.stored") def handle_file_stored(event): ...` — handlers self-register via a decorator. Discoverable, but requires an autodiscovery mechanism (like Django admin's `autodiscover()`).
  3. **Simple dict in the service module**: A `HANDLERS` dict in `common/services/outbox.py` that apps populate in their `AppConfig.ready()`. Minimal infrastructure.
  4. **Defer handlers entirely**: Since handlers are explicitly out of scope ("consumer PEPs implement specific handlers"), the delivery task could initially just mark events as delivered without calling any handler. The handler registration mechanism is designed when the first consumer PEP needs it.
- **Status**: Awaiting input — this significantly affects the service API design and the delivery task implementation. Option 4 (defer) is recommended since this PEP's scope is infrastructure, not consumption.

### Thread: Should delivered events be automatically cleaned up?

- **Raised**: 2026-02-26
- **Context**: The "Out of Scope" section defers DLQ for failed events, but doesn't mention cleanup of successfully delivered events. In a busy system, delivered events will accumulate indefinitely. The existing `cleanup_expired_upload_files_task` provides a pattern for batch cleanup tasks.
- **Options**:
  1. **Include a cleanup task in this PEP**: Add a `cleanup_delivered_outbox_events_task` that deletes events with `status=delivered` and `delivered_at` older than a configurable TTL (e.g., `OUTBOX_RETENTION_HOURS = 168` — 7 days). Follows the existing cleanup task pattern.
  2. **Defer cleanup to a future PEP**: Keep the table simple for now. Cleanup can be added once there's production data showing growth patterns.
  3. **Soft delete (mark as archived)**: Add an `archived_at` field. Preserves audit trail but adds complexity.
- **Status**: Awaiting input — Option 1 is straightforward and follows the existing cleanup task pattern. Option 2 is simpler but risks table growth becoming a problem before it's addressed.

### Thread: Event ordering guarantees per aggregate

- **Raised**: 2026-02-26
- **Context**: The delivery task processes pending events, but the plan doesn't specify ordering. For some use cases, processing events out of order for the same aggregate (e.g., `file.stored` before `file.created`) could cause issues. UUID v7 PKs are time-ordered, so ordering by PK would approximate creation order.
- **Options**:
  1. **No ordering guarantee**: Process events in whatever order the query returns. Simplest implementation. Handlers must be idempotent and order-independent.
  2. **FIFO per aggregate**: Process events in PK order (UUID v7 = time-ordered) and only process the next event for an aggregate after the previous one is delivered. Guarantees in-order delivery but reduces throughput and adds complexity.
  3. **Global FIFO**: Process all events in PK order. Simple but limits parallelism.
- **Status**: Awaiting input — Option 1 (no ordering) is recommended for the initial implementation. The outbox pattern inherently provides at-least-once delivery, not exactly-once-in-order. Order-dependent consumers can handle ordering in their handlers. The `idempotency_key` + unique constraint already prevents duplicates.

### Thread: Eager mode behavior for the delivery task

- **Raised**: 2026-02-26
- **Context**: In Dev mode, `CELERY_TASK_ALWAYS_EAGER=True` makes tasks run synchronously. If `emit_event()` uses `transaction.on_commit()` to schedule the delivery task, and the task runs eagerly, the delivery will happen synchronously right after the transaction commits. This is actually desirable for development (immediate feedback), but it means the delivery task must handle the case where it processes the event that was just emitted (which it will find since the transaction is committed). This should work correctly but should be explicitly tested.
- **Options**:
  1. **No special handling**: Eager mode + `on_commit` = synchronous delivery after commit. This is correct and useful for development.
  2. **Skip delivery dispatch in eager mode**: Only write the outbox row, don't trigger delivery. Requires manual invocation for testing.
- **Status**: Awaiting input — Option 1 is recommended. Eager mode behavior is correct and useful. The only caveat is that delivery errors in eager mode will be visible to the caller (since the task runs synchronously), but `safe_dispatch()` from `common/utils.py` could wrap the delivery call if this is undesirable.
