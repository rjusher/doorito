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

### Q9: Should the `payload` JSONField use `DjangoJSONEncoder`?

- **Resolved**: 2026-02-26
- **Answer**: Yes. Use `encoder=DjangoJSONEncoder` on the `payload` field.
- **Rationale**: Django's default `json.JSONEncoder` cannot serialize `UUID`, `Decimal`, `datetime`, or `date` objects — it raises `TypeError`. Callers of `emit_event()` will naturally pass payloads containing UUIDs (aggregate IDs, related object PKs) and datetimes (timestamps). Requiring callers to pre-serialize everything to strings is error-prone and adds friction. `DjangoJSONEncoder` (from `django.core.serializers.json`) handles all these types transparently. The trade-off is that round-tripping loses type info (`UUID` → string, `Decimal` → string), but consumers already need to parse the JSON payload so this is expected. The `uploads/models.py:83` `metadata = JSONField(default=dict, blank=True)` field uses the default encoder, but that field stores user-provided metadata, not system-generated events — different use case.

### Q10: Should the model include database indexes for poll query performance?

- **Resolved**: 2026-02-26
- **Answer**: Yes. Add a partial index on `(next_attempt_at)` where `status='pending'` in the model's `Meta.indexes`.
- **Rationale**: The delivery task's primary query filters `status='pending'` and `next_attempt_at <= now()`. Without an index, this is a full table scan. As delivered events accumulate (the majority of rows over time), the scan cost grows linearly while the result set stays small. A partial index `Index(fields=["next_attempt_at"], condition=Q(status="pending"))` covers only the rows that matter and is maintained only for pending events — negligible write overhead. The project already uses `Meta.indexes` in `uploads/models.py:96-99` (indexes on `uploaded_by/-created_at` and `status`). Django supports partial indexes via `Index(condition=Q(...))` which maps to PostgreSQL `WHERE` clause. Convention for index naming: `"idx_outbox_event_pending_next_attempt"`.

### Q11: What should `next_attempt_at` be for newly created events?

- **Resolved**: 2026-02-26
- **Answer**: Set `next_attempt_at = timezone.now()` when creating the event in `emit_event()`. The field remains `null=True` on the model for events that are delivered/expired and no longer eligible for processing.
- **Rationale**: The polling query filters `next_attempt_at <= now()`. Setting it to `now()` makes the event immediately eligible for the periodic sweep. The on-demand dispatch via `transaction.on_commit()` handles the fast path regardless, but if that dispatch fails, the sweep needs to find the event. Using `null` to mean "process immediately" would complicate the query (`WHERE next_attempt_at IS NULL OR next_attempt_at <= now()`). Using `now()` keeps the query simple and the partial index effective.

### Q12: Should `emit_event()` accept an `idempotency_key` parameter?

- **Resolved**: 2026-02-26
- **Answer**: Yes. The function signature should be `emit_event(aggregate_type, aggregate_id, event_type, payload, *, idempotency_key=None)`. When `idempotency_key` is `None`, the service auto-generates it as `f"{aggregate_type}:{aggregate_id}:{event_type}"`.
- **Rationale**: The summary lists `idempotency_key` as a model field with a `UniqueConstraint(fields=["event_type", "idempotency_key"])`, but the proposed service signature `emit_event(aggregate_type, aggregate_id, event_type, payload)` omits it. Someone must generate the key. Options considered:
  - **Always caller-provided (required arg)**: Forces every caller to think about idempotency, which is good, but adds friction for the common case where the aggregate ID is the natural idempotency key.
  - **Always auto-generated**: Simple, but some callers may need custom keys (e.g., a retry operation that should be deduplicated against the original).
  - **Optional with auto-generation default**: Best of both worlds — simple for common cases, extensible for special ones.
  The default `f"{aggregate_type}:{aggregate_id}:{event_type}"` means: for a given aggregate, only one event of each type can be pending. This prevents duplicate events when `emit_event()` is called multiple times for the same state change (e.g., due to request retries). Callers needing finer granularity (e.g., multiple `file.chunk_received` events for the same file) can pass a custom key.

### Q13: What should the Celery task name be for the delivery task?

- **Resolved**: 2026-02-26
- **Answer**: `name="common.tasks.deliver_outbox_events_task"`, following the convention `app.tasks.task_name_task`.
- **Rationale**: The existing task uses `name="uploads.tasks.cleanup_expired_upload_files_task"` (`uploads/tasks.py:16`). The convention is `{app}.tasks.{function_name}`. The function will be `deliver_outbox_events_task` in `common/tasks.py`, so the name is `common.tasks.deliver_outbox_events_task`.

### Q14: What are the event ordering semantics for delivery?

- **Resolved**: 2026-02-26 (promoted from Open Thread)
- **Answer**: No ordering guarantee. The delivery task processes pending events in `next_attempt_at` order (ascending), but does not enforce per-aggregate ordering. Handlers must be idempotent and order-independent.
- **Rationale**: Per-aggregate FIFO ordering requires tracking per-aggregate head-of-line state, blocking delivery of later events until earlier ones succeed — this significantly increases complexity and reduces throughput. The outbox pattern inherently provides at-least-once semantics, not exactly-once-in-order. UUID v7 PKs provide a natural creation-time ordering if consumers need to reconstruct order after the fact. `select_for_update(skip_locked=True)` means different workers will process different events concurrently with no ordering. This is the standard approach in production outbox implementations (Debezium, Axon). If a future consumer requires strict ordering, it can maintain its own sequence tracking — that complexity belongs in the consumer, not the infrastructure.

### Q15: What is the interaction between eager mode and `CELERY_TASK_EAGER_PROPAGATES`?

- **Resolved**: 2026-02-26 (promoted from Open Thread)
- **Answer**: No special handling needed. Eager mode + `on_commit` = synchronous delivery after commit. Delivery errors are suppressed by wrapping the `on_commit` dispatch in a try/except.
- **Rationale**: In Dev mode, `CELERY_TASK_ALWAYS_EAGER = True` and `CELERY_TASK_EAGER_PROPAGATES = True` (`boot/settings.py:183-187`). This means: (1) tasks run synchronously in the calling thread, and (2) task exceptions propagate to the caller. If `emit_event()` uses `transaction.on_commit(lambda: deliver_outbox_events_task.delay())` and the delivery task raises an exception during eager execution, that exception propagates through `on_commit` back up the call stack. This would break the caller for a non-critical side effect.
  **Mitigation**: The `on_commit` callback should catch exceptions from the `.delay()` call (which in eager mode includes the entire task execution). Pattern: `transaction.on_commit(lambda: _safe_dispatch_delivery())` where `_safe_dispatch_delivery` wraps the `.delay()` in a try/except and logs errors. This is consistent with the `safe_dispatch()` pattern in `common/utils.py:52-73`. In production (non-eager mode), `.delay()` only enqueues the task — it doesn't run it — so exceptions are limited to broker connectivity issues.

### Q16: Status lifecycle bug — FAILED events are orphaned by the poll query

- **Resolved**: 2026-02-26
- **Answer**: Simplify from 4 states to 3. Events stay `PENDING` during retries. Only terminal states are `DELIVERED` (success) and `FAILED` (max retries exhausted). Drop `EXPIRED`.
- **Rationale**: The plan's `process_pending_events()` polls with `status=OutboxEvent.Status.PENDING, next_attempt_at__lte=timezone.now()`. On a processing error, the plan sets `status=FAILED` and updates `next_attempt_at` with exponential backoff. **Bug**: since the poll query only selects `status=PENDING`, events that transition to `FAILED` will never be picked up again — they are permanently orphaned despite having retries remaining. The partial index on `Q(status="pending")` reinforces this: `FAILED` rows are excluded from the index entirely.
  **Fix**: Events remain in `PENDING` status throughout their retry lifecycle. On error, only `attempts`, `error_message`, and `next_attempt_at` are updated — status stays `PENDING`. When `attempts >= max_attempts`, transition to `FAILED` (terminal). This means:
  - `PENDING`: initial + retrying (eligible for processing). `attempts` field tracks how many times delivery has been attempted. `error_message` stores the last failure reason.
  - `DELIVERED`: success (terminal). `delivered_at` is set, `next_attempt_at` is `None`.
  - `FAILED`: max retries exhausted (terminal). `next_attempt_at` is `None`.
  The poll query, partial index, and admin retry action all work correctly with this 3-state model. Q5's `EXPIRED` state was meant to distinguish "retriable failure" from "exhausted retries," but the FAILED→EXPIRED distinction added complexity without behavioral difference — both are terminal in the cleanup task, and both get the same admin retry action. See Design Decision: "Simplified 3-state lifecycle."

### Q17: Idempotency key default format — correction to Q12

- **Resolved**: 2026-02-26
- **Answer**: The correct default format is `f"{aggregate_type}:{aggregate_id}"` (without `:{event_type}`), as stated in the Design Decision "Default idempotency_key derived from aggregate identity."
- **Rationale**: Q12's answer states the auto-generated key is `f"{aggregate_type}:{aggregate_id}:{event_type}"`, but the Design Decision (written after Q12 and representing the authoritative resolution) says `f"{aggregate_type}:{aggregate_id}"`. The plan (Step 5, line 155) also uses the shorter format. Including `event_type` in the key is redundant because `event_type` is already part of the `UniqueConstraint(fields=["event_type", "idempotency_key"])`. The constraint uniqueness is on the *pair* `(event_type, idempotency_key)`, so the key only needs to identify the aggregate instance — `event_type` is covered by the first constraint field. The Design Decision and plan are correct; Q12's answer text contains a typo.

### Q18: Should handlers be deferred entirely? (promoted from Open Thread)

- **Resolved**: 2026-02-26 (promoted from Open Thread "Handler registration mechanism")
- **Answer**: Yes — Option 4 (defer handlers entirely). The delivery task marks events as `DELIVERED` without calling any handler. Handler registration mechanism is designed when the first consumer PEP needs it.
- **Rationale**: The plan already implements this (Step 5: "Since handlers are deferred... mark as `status=DELIVERED`"). The summary's "Out of Scope" section explicitly states handlers are for consumer PEPs. Designing a handler registry without a concrete consumer is speculative — the first consumer will reveal requirements (sync vs async, error semantics, fan-out). The summary has been amended (line 30) to soften handler language.

### Q19: Should delivered events be automatically cleaned up? (promoted from Open Thread)

- **Resolved**: 2026-02-26 (promoted from Open Thread "Should delivered events be automatically cleaned up?")
- **Answer**: Yes — Option 1 (include cleanup task in this PEP). Add `cleanup_delivered_outbox_events_task` that deletes events in terminal states (`DELIVERED`, `FAILED`) older than `OUTBOX_RETENTION_HOURS` (default 168 = 7 days).
- **Rationale**: The plan already includes this (Step 5: `cleanup_delivered_events()` service, Step 6: `cleanup_delivered_outbox_events_task`, Step 7: beat schedule entry and `OUTBOX_RETENTION_HOURS` setting). The infrastructure is in place, the pattern is established (`uploads/tasks.py`), and the scope is minimal (~30 lines). Without cleanup, `outbox_event` grows without bound, affecting backups and VACUUM. Note: with the 3-state lifecycle (Q16), cleanup targets `DELIVERED` and `FAILED` (not `EXPIRED`, which no longer exists).

### Q20: Celery-beat sweep interval (promoted from Open Thread)

- **Resolved**: 2026-02-26 (promoted from Open Thread "Celery-beat sweep interval and configuration")
- **Answer**: Option 2 — configurable via `OUTBOX_SWEEP_INTERVAL_MINUTES = 5` (default), using `timedelta(minutes=self.OUTBOX_SWEEP_INTERVAL_MINUTES)` in the beat schedule.
- **Rationale**: The plan already implements this (Step 7: `OUTBOX_SWEEP_INTERVAL_MINUTES = 5` setting, `deliver-outbox-events-sweep` beat entry). 5 minutes is short enough to limit delivery lag when on-commit dispatch fails, but not so frequent as to generate excessive empty-result task runs. Follows the `CLEANUP_UPLOADS_INTERVAL_HOURS` naming convention.

### Q21: Plan completeness (promoted from Open Thread)

- **Resolved**: 2026-02-26 (promoted from Open Thread "Plan completeness for implementation")
- **Answer**: The plan has been fully refined. All implementation steps have inline verification commands, acceptance criteria are mapped to concrete test/check commands, and all resolved questions and design decisions have been incorporated.
- **Rationale**: The plan now contains 11 detailed steps, each with file lists, implementation details, pattern references, and verification commands. The Final Verification section includes acceptance criteria checks, integration checks, regression checks, and an end-to-end smoke test. The only remaining action items are amendments from Q16 (3-state lifecycle) which should be applied before implementation.

## Design Decisions

### Decision: On-demand dispatch via `transaction.on_commit()` + periodic sweep via celery-beat

- **Date**: 2026-02-26 (amended 2026-02-26)
- **Context**: The plan originally said "Register periodic task in Celery beat schedule" (Step 6). An earlier review concluded celery-beat was not configured, but **this was incorrect** — PEP 0005 (commit `c9af87d`) added full celery-beat infrastructure: `django-celery-beat` is in `INSTALLED_APPS`, `CELERY_BEAT_SCHEDULER` is set to `DatabaseScheduler`, and `CELERY_BEAT_SCHEDULE` defines the upload cleanup crontab. The beat process is in Docker Compose and Procfile.dev.
- **Decision**: Use **both** on-demand dispatch and periodic sweep:
  1. **On-demand (fast path)**: `emit_event()` registers `deliver_outbox_events_task.delay()` via `transaction.on_commit()` for near-instant delivery.
  2. **Periodic sweep (safety net)**: A celery-beat entry runs the same delivery task on a configurable interval (e.g., every 5 minutes) to catch events missed if the on-commit dispatch failed (worker down, task lost).
- **Alternatives rejected**:
  - **On-demand only (no sweep)**: If the Celery broker is unreachable when `on_commit` fires, the task is silently lost. Since the broker is PostgreSQL (same as the database), this is unlikely but possible during connection pool exhaustion or transient errors.
  - **Periodic polling only (no on-commit)**: Adds unnecessary latency. Events wait until the next poll interval.
  - **Django management command on cron**: External scheduling dependency, harder to configure in Docker environments.

### Decision: `error_message` stores only the last error, not error history

- **Date**: 2026-02-26
- **Context**: The `error_message` field is a `TextField`. It could store a cumulative log of all errors across attempts, or just the latest error.
- **Decision**: Store only the latest error message. Each retry overwrites the previous `error_message`.
- **Alternatives rejected**: - **Accumulating error log**: Adds complexity, grows unboundedly, and duplicates information available in application logs. The outbox is an infrastructure table, not an audit log. If detailed error history is needed, it belongs in structured logging or a dedicated error-tracking system.

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

### Decision: Use `DjangoJSONEncoder` for the `payload` JSONField

- **Date**: 2026-02-26
- **Context**: The `payload` field will contain event data including UUIDs, datetimes, and potentially Decimals. Django's default `json.JSONEncoder` rejects these types.
- **Decision**: Define the field as `payload = JSONField(default=dict, encoder=DjangoJSONEncoder)` using `from django.core.serializers.json import DjangoJSONEncoder`. This transparently serializes `UUID`, `datetime`, `date`, `time`, `timedelta`, and `Decimal` objects.
- **Alternatives rejected**:
  - **Require callers to pre-serialize**: Fragile — any caller forgetting to `str()` a UUID gets a `TypeError` at runtime. The encoder is a one-line addition with no downside.
  - **Custom encoder**: Unnecessary — `DjangoJSONEncoder` already handles all Django/Python types.

### Decision: Default `idempotency_key` derived from aggregate identity

- **Date**: 2026-02-26
- **Context**: The `emit_event()` function needs an idempotency key for the `UniqueConstraint(fields=["event_type", "idempotency_key"])`. The key must be provided or generated.
- **Decision**: Accept optional `idempotency_key` keyword argument. When `None`, auto-generate as `f"{aggregate_type}:{aggregate_id}"`. Combined with `event_type` in the constraint, this means one event per type per aggregate instance. Callers can pass a custom key for finer-grained deduplication.
- **Alternatives rejected**:
  - **Random UUID as key**: Defeats the purpose of idempotency — every call generates a unique key, so duplicates are never caught.
  - **Always required**: Adds friction for the common case where the aggregate identity is the natural deduplication key.

### Decision: Simplified 3-state lifecycle (PENDING, DELIVERED, FAILED)

- **Date**: 2026-02-26
- **Context**: The original 4-state model (PENDING, DELIVERED, FAILED, EXPIRED) had a critical bug: the poll query filters `status='pending'` only, so events set to `status='failed'` during error handling would never be re-polled for retry. The partial index on `Q(status="pending")` reinforced this — FAILED rows were excluded. Additionally, FAILED (intermediate, retryable) vs EXPIRED (terminal, max retries exhausted) had no behavioral difference: both were targeted by the same cleanup query and the same admin retry action.
- **Decision**: Use 3 states: `PENDING`, `DELIVERED`, `FAILED`.
  - `PENDING` — event awaiting delivery (initial or retrying). `attempts > 0` with `error_message` set indicates a retry-in-progress. `next_attempt_at` controls when the event is eligible for the next attempt.
  - `DELIVERED` — successfully processed (terminal). `delivered_at` is set, `next_attempt_at` is `None`.
  - `FAILED` — max retries exhausted (terminal). `next_attempt_at` is `None`.
  On error: `attempts` is incremented, `error_message` is set, `next_attempt_at` is pushed back with exponential backoff, **status stays `PENDING`**. Only when `attempts >= max_attempts` does the event transition to `FAILED`.
- **Alternatives rejected**:
  - **4-state model (PENDING → FAILED → ... → EXPIRED)**: Required the poll query to include `status__in=['pending', 'failed']` and the partial index to cover both states. More complex for no behavioral gain.
  - **Query both PENDING and FAILED**: Fixes the bug but keeps a state distinction with no practical difference. Added complexity in the partial index condition and cleanup queries.

### Decision: Reuse `safe_dispatch()` context manager for on-commit delivery

- **Date**: 2026-02-26
- **Context**: The plan defines `_safe_dispatch_delivery()` as a helper to wrap the `deliver_outbox_events_task.delay()` call in try/except. `common/utils.py:52-73` already provides `safe_dispatch()`, a context manager that does exactly this pattern: wraps an operation in try/except, logs errors, and prevents exceptions from propagating.
- **Decision**: Use the existing `safe_dispatch()` context manager in the `on_commit` callback instead of creating a new `_safe_dispatch_delivery()` function. Pattern: `transaction.on_commit(lambda: _dispatch_delivery())` where `_dispatch_delivery` uses `with safe_dispatch("dispatch outbox delivery", logger): deliver_outbox_events_task.delay()`. This is simpler (no new helper function) and consistent with the utility's documented purpose ("Use around notification dispatch, event emission, audit logging").
- **Alternatives rejected**:
  - **New `_safe_dispatch_delivery()` helper**: Duplicates the safe_dispatch pattern. Works but adds unnecessary code.

## Open Threads

### ~~Thread: Handler registration mechanism~~ → Resolved as Q18

- **Raised**: 2026-02-26
- **Resolved**: 2026-02-26
- **Status**: Resolved — see Q18 in Resolved Questions. Decision: Option 4 (defer handlers entirely). Delivery task marks events as DELIVERED without calling any handler. Handler registration designed when first consumer PEP needs it.

### ~~Thread: Should delivered events be automatically cleaned up?~~ → Resolved as Q19

- **Raised**: 2026-02-26
- **Resolved**: 2026-02-26
- **Status**: Resolved — see Q19 in Resolved Questions. Decision: Option 1 (include cleanup task). Deletes DELIVERED and FAILED events older than `OUTBOX_RETENTION_HOURS` (7 days).

### ~~Thread: Event ordering guarantees per aggregate~~ → Resolved as Q14

- **Raised**: 2026-02-26
- **Resolved**: 2026-02-26
- **Status**: Resolved — see Q14 in Resolved Questions. Decision: No ordering guarantee. Process events in `next_attempt_at` order. Handlers must be idempotent and order-independent.

### ~~Thread: Eager mode behavior for the delivery task~~ → Resolved as Q15

- **Raised**: 2026-02-26
- **Resolved**: 2026-02-26
- **Status**: Resolved — see Q15 in Resolved Questions. Decision: No special handling. Eager mode + `on_commit` = synchronous delivery. Wrap the dispatch in try/except to prevent `CELERY_TASK_EAGER_PROPAGATES` from breaking callers.

### ~~Thread: Celery-beat sweep interval and configuration~~ → Resolved as Q20

- **Raised**: 2026-02-26
- **Resolved**: 2026-02-26
- **Status**: Resolved — see Q20 in Resolved Questions. Decision: Option 2 — configurable `OUTBOX_SWEEP_INTERVAL_MINUTES = 5` default, using `timedelta` in beat schedule.

### ~~Thread: Plan completeness for implementation~~ → Resolved as Q21

- **Raised**: 2026-02-26
- **Resolved**: 2026-02-26
- **Status**: Resolved — see Q21 in Resolved Questions. Plan is fully detailed with 11 steps, verification commands, and final verification section.

### Q22: `choices=Status` (summary) vs `choices=Status.choices` (plan) — which to use?

- **Resolved**: 2026-02-26
- **Answer**: Use `choices=Status.choices` per codebase convention.
- **Rationale**: The summary model definition (line 45) shows `choices=Status` while the plan (Step 2, line 80) shows `choices=Status.choices`. Both are valid Django — since Django 3.0, passing the `TextChoices` class directly works. However, all existing models in the codebase consistently use `.choices`: `uploads/models.py:29` (`choices=Status.choices`), line 87, line 126, line 189. The plan is correct; the summary's model snippet should use `.choices` for consistency. This is cosmetic — the generated migration and runtime behavior are identical either way.

### Q23: Should `common/tests/conftest.py` be in Step 8's file list?

- **Resolved**: 2026-02-26
- **Answer**: Yes. Add `common/tests/conftest.py` to Step 8's file list with the `make_outbox_event` factory fixture.
- **Rationale**: Step 8 lists 4 files (`__init__.py`, `test_models.py`, `test_services.py`, `test_tasks.py`) but the note at the bottom says "If `make_outbox_event` is needed across test modules, create `common/tests/conftest.py`". Since the fixture IS used across all three test modules, conftest.py is required, not optional. Omitting it from the file list risks the implementer missing it.

### Q24: Verification command bug — `e._meta` should be `OutboxEvent._meta`

- **Resolved**: 2026-02-26
- **Answer**: Fix the verification command in the Final Verification table (plan line 691).
- **Rationale**: The acceptance criteria check for "OutboxEvent model exists" contains: `from common.models import OutboxEvent; print('Fields:', [f.name for f in e._meta.get_fields() if hasattr(f, 'name')])`. The variable `e` is undefined — should be `OutboxEvent`. The second half of the same command correctly uses `E` as an alias. Should be `OutboxEvent._meta.get_fields()`.

### Q25: Should `emit_event()` document the transactional API contract?

- **Resolved**: 2026-02-26
- **Answer**: Yes. The function's docstring should explicitly state that callers should wrap both the state change and the `emit_event()` call in the same `transaction.atomic()` block for transactional consistency.
- **Rationale**: The summary (line 29) says the service "creates outbox entries within the same database transaction as the state change." But the service itself doesn't enforce this — it relies on the caller's transaction context. If `emit_event()` is called outside any `atomic()` block, `create()` auto-commits immediately, and `on_commit` fires right after — the event is independently committed, potentially before the caller's state change succeeds. The correct usage pattern is:
  ```python
  with transaction.atomic():
      upload_file = create_upload_file(...)  # state change
      emit_event("UploadFile", str(upload_file.pk), "file.stored", {...})  # outbox entry
  # on_commit fires here — delivery dispatched after both writes are committed
  ```
  This is an API contract, not enforced by code. Documenting it in `emit_event()`'s docstring and in `aikb/services.md` prevents misuse. If `emit_event()` is called outside `atomic()`, it still works (event is emitted and delivered), but the transactional guarantee is lost.

### Q26: Should `emit_event()` return value be documented for `on_commit` timing?

- **Resolved**: 2026-02-26
- **Answer**: Yes. Document that the returned `OutboxEvent` instance has `status=PENDING` — the `on_commit` delivery dispatch hasn't fired yet at return time (it fires after the outermost transaction commits).
- **Rationale**: In eager mode (Dev), if `emit_event()` is called outside `atomic()`, the auto-committed `create()` triggers `on_commit` immediately, and eager mode runs the delivery task synchronously. The event may already be `DELIVERED` by the time the caller inspects it. But inside `atomic()`, the event is `PENDING` at return time. Callers should not depend on the event being delivered immediately — the return value is always the freshly-created `PENDING` event.

### Thread: Jitter in exponential backoff formula

- **Raised**: 2026-02-26
- **Context**: `research.md` explicitly warns: "No jitter → retry storms after broker recovery. Add `random.uniform(0, base_delay * 0.1)` jitter." However, Q8's resolution and the plan's backoff formula (`min(60 * (2 ** event.attempts), 3600)`) include no jitter. After a broker recovery or mass transient failure, all failed events would have identical `next_attempt_at` values, causing a retry storm where the sweep processes them all simultaneously.
- **Options**:
  1. **Add jitter now**: `next_attempt_at = now() + timedelta(seconds=min(60 * (2 ** attempts), 3600) + random.uniform(0, 6))` — adds 0-6 seconds of random jitter. Cheap, prevents retry storms, standard practice.
  2. **Defer jitter**: The initial implementation has no handlers (events are just marked DELIVERED), so there's no external call that could fail, meaning no retry storms are possible. Add jitter when handlers are introduced.
  3. **Add jitter with larger range**: Use `random.uniform(0, 0.1 * base_delay * (2 ** attempts))` — jitter proportional to the backoff delay. More spread, but also more variable.
- **Recommendation**: Option 2 (defer). Since the initial implementation defers handlers (Q18), there is no error path in `process_pending_events()` — events are immediately marked DELIVERED. Retry logic exists in the code for future use but won't fire. When the first consumer PEP adds handlers and introduces a real failure mode, that PEP should add jitter to the backoff formula. Adding it now would be dead code.
- **Status**: **Low priority** — deferred to first consumer PEP. No action needed for this PEP.

### Thread: `schema_version` in event payloads

- **Raised**: 2026-02-26
- **Context**: `research.md` recommends: "Include a `schema_version` key in payloads for forward compatibility as event schemas evolve." This is not addressed in the plan, summary, or any other discussion. As event schemas evolve over time (e.g., `file.stored` v1 adds `size`, v2 adds `checksum`), consumers need to know which version they're handling.
- **Options**:
  1. **Enforce in `emit_event()`**: Require or auto-add a `schema_version` key in every payload. E.g., `emit_event(..., schema_version=1)` or `payload.setdefault("schema_version", 1)`.
  2. **Document as a convention**: Don't enforce, but document in `aikb/conventions.md` that payloads should include `schema_version`.
  3. **Defer entirely**: Schema versioning is a concern for consumer PEPs that define specific event schemas. The outbox infrastructure treats payload as opaque JSON.
- **Recommendation**: Option 3 (defer). The outbox infrastructure treats `payload` as an opaque `JSONField`. Schema versioning is a concern of the event schema, not the transport layer. When the first consumer PEP defines a specific event type (e.g., `file.stored`), it should define the payload schema including any versioning. Embedding schema concerns in the generic `emit_event()` function conflates transport and schema.
- **Status**: **Low priority** — deferred to consumer PEPs. No action needed for this PEP.

### Thread: Lock duration in batch processing with `select_for_update`

- **Raised**: 2026-02-26
- **Context**: The plan wraps the entire batch in a single `transaction.atomic()` with `select_for_update(skip_locked=True)[:batch_size]`. This means all events in the batch (up to 100) are row-locked for the entire processing duration. Currently fine because processing is just a status transition (fast, no I/O). But when handlers are added (by consumer PEPs), long-running handlers would hold locks on all 100 rows for the duration of the slowest handler in the batch.
- **Options**:
  1. **Keep current design**: Single transaction, batch lock. Acceptable for the initial implementation (no handlers, fast status transitions). Note the limitation for consumer PEPs.
  2. **Per-event transactions**: Process each event in its own `transaction.atomic()` block. More robust but requires a different query pattern (can't use `select_for_update` across the loop since locks are released per transaction).
  3. **Hybrid**: Query batch IDs in outer transaction, process each in inner transaction. Complex but optimal lock duration.
- **Recommendation**: Option 1 for this PEP. The initial implementation has no handlers — processing is a trivial status update that completes in microseconds per event. Document that consumer PEPs adding handlers should evaluate whether per-event transactions are needed based on handler execution time. This is a known limitation, not a bug.
- **Status**: **Low priority** — informational for consumer PEPs. No action needed for this PEP.

### Thread: Dead error handling code in `process_pending_events()` and savepoint correctness

- **Raised**: 2026-02-26
- **Context**: The plan (Step 5) includes per-event error handling with exponential backoff in `process_pending_events()`, even though the initial implementation has no handlers (Q18) — making the error path unreachable dead code. The plan justifies this: "included for correctness so consumer PEPs only need to add handler dispatch logic, not retry infrastructure." Two concerns:
  1. **Over-engineering**: CLAUDE.md says "Don't add error handling, fallbacks, or validation for scenarios that can't happen." The retry infrastructure is dead code in this PEP. Including it adds ~15 lines of untestable code.
  2. **Savepoint correctness**: The error handling code catches exceptions and does `event.save()` inside the same `transaction.atomic()` block that holds the `select_for_update` lock. If the exception is a **database error** (e.g., `IntegrityError` from a handler), Django marks the transaction as needing rollback — all subsequent `event.save()` calls in the same atomic block will fail with `TransactionManagementError`. For non-database exceptions (HTTP errors, validation errors, etc.), the code works correctly. But without savepoints (nested `atomic()` per event), database errors from handlers will poison the entire batch.
- **Options**:
  1. **Include error handling with savepoints**: Wrap each event's processing in `with transaction.atomic():` (savepoint). Correct for all failure modes, but more complex dead code (~20 lines untestable).
  2. **Include error handling without savepoints** (current plan): Correct for non-database exceptions only. Simpler but subtly incorrect for database errors from handlers.
  3. **Omit error handling entirely**: Just mark events as `DELIVERED` in a simple loop. Consumer PEPs add both handler dispatch AND error handling (including savepoints) when they add handlers. Simplest, fully testable, follows "avoid over-engineering" principle.
- **Recommendation**: Option 3 (omit). The retry infrastructure is ~15 lines of dead code that can't be tested in this PEP. When the first consumer PEP adds handlers, it will need to add handler dispatch logic anyway — adding error handling and savepoints at the same time is marginal extra effort and can be designed for the specific handler's failure modes. If option 2 is preferred, at minimum add a `# TODO: wrap in savepoint when handlers are added` comment.
- **Status**: **Needs human input** — should dead error handling code be included or omitted?

### Thread: Missing `on_commit` integration test in test plan

- **Raised**: 2026-02-26
- **Context**: The test plan (Step 8) tests `emit_event()` and `process_pending_events()` independently, verifying that events are created and that pending events are delivered. But no test verifies the **`on_commit` → delivery pipeline**: that calling `emit_event()` inside a transaction causes automatic delivery after commit. The end-to-end smoke test (plan line 729) covers this path, but it's a shell script, not a pytest test.
  The research.md (line 259–264) explicitly discusses this gap: "Tests that verify `transaction.on_commit()` behavior require `pytest.mark.django_db(transaction=True)`" and mentions `captureOnCommitCallbacks()`. But neither approach appears in the test plan.
- **Options**:
  1. **Add `transaction=True` integration test**: `@pytest.mark.django_db(transaction=True)` test that calls `emit_event()`, then checks `event.refresh_from_db()` has `status=DELIVERED` (works in eager mode). Slower (uses `TransactionTestCase` semantics — table truncation instead of rollback).
  2. **Mock `transaction.on_commit`**: Patch `transaction.on_commit` and verify it's called with a callable. Fast, but tests implementation details, not behavior.
  3. **Rely on smoke test**: The shell-based smoke test in Final Verification already covers this path. No pytest test needed.
  4. **Use `captureOnCommitCallbacks()`**: Django 4.2+ `TestCase.captureOnCommitCallbacks()` — but requires `unittest.TestCase` subclass, not pytest-native. Can be awkward to integrate.
- **Recommendation**: Option 1. A single `transaction=True` test for the `emit_event() → on_commit → delivery` pipeline provides confidence that the primary delivery path works. The test is ~10 lines and runs once, so the slowdown from `TransactionTestCase` semantics is minimal. This tests the most important user-facing behavior: "emit an event and it gets delivered."
- **Status**: **Low priority** — desirable but not blocking. The smoke test provides equivalent coverage.

### Thread: Acceptance criterion "retry-with-backoff" not exercisable in initial implementation

- **Raised**: 2026-02-26
- **Context**: Acceptance criterion 4 states: "Delivery Celery task polls and processes pending events with retry-with-backoff." But with handlers deferred (Q18), the delivery task always succeeds — events are immediately marked `DELIVERED`. The retry-with-backoff code path is never exercised. This criterion is not falsifiable in the initial implementation.
  If the "dead error handling" thread resolves as Option 3 (omit), this criterion needs rewording since the retry code won't exist yet. If resolved as Option 1 or 2 (include), the code exists but can't be tested via normal execution.
- **Options**:
  1. **Reword criterion**: "Delivery Celery task polls and processes pending events" (remove "with retry-with-backoff"). Add a separate criterion: "Retry-with-backoff infrastructure exists in `process_pending_events()` for future handler use" — or defer it entirely to consumer PEPs.
  2. **Keep as-is**: Accept that the criterion is verified by code inspection rather than test execution. The retry code exists and is structurally correct, even if untestable.
  3. **Add a test that simulates handler failure**: Mock a handler-like code path to exercise the retry logic. But this tests code that doesn't exist yet (handlers are deferred), making it fragile and coupled to future implementation details.
- **Recommendation**: Option 1. Reword to match actual deliverables. The acceptance criterion should be testable against the actual implementation.
- **Status**: **Needs human input** — depends on the "dead error handling" thread resolution.
