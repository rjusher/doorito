# PEP 0004: Event Outbox Infrastructure — Research

| Field | Value |
|-------|-------|
| **PEP** | 0004 |
| **Summary** | [summary.md](summary.md) |
| **Plan** | [plan.md](plan.md) |

---

## Current State Analysis

### No Event Infrastructure Exists

The codebase has no event emission, event handling, or event storage mechanism. Domain state changes (e.g., file upload completion, user creation) happen in service functions with no way to notify other parts of the system. The `aikb/signals.md` confirms: "No signal handlers are defined yet."

### The `common` App Is Minimal

The `common` app (`common/`) serves as a shared utilities layer. Its current contents:

- `models.py` — `TimeStampedModel` (abstract base, 14 lines)
- `fields.py` — `MoneyField` (custom DecimalField, 26 lines)
- `utils.py` — `uuid7()`, `generate_reference()`, `apply_date_range()`, `safe_dispatch()` (73 lines)
- `apps.py` — `CommonConfig` (bare-minimum AppConfig, 11 lines)
- `management/base.py` — `DooritoBaseCommand`

**Missing directories/files that PEP 0004 needs to create:**
- `common/admin.py` — does not exist (confirmed in discussions.md Q4)
- `common/services/` — does not exist (confirmed in discussions.md Q3)
- `common/tasks.py` — does not exist
- `common/tests/` — does not exist
- `common/migrations/` — does not exist (the app has only abstract models, so Django never generated migrations)

### Service Layer Pattern Is Established

The `uploads` app has a mature service layer (`uploads/services/uploads.py` — 8 functions, `uploads/services/sessions.py` — 3 functions) that demonstrates the project's service conventions:
- Plain functions, not classes
- Logging with `logger.info` for success, `logger.warning` for failures
- `@transaction.atomic` for multi-step operations
- Atomic `filter().update()` for race-condition-safe status transitions

### Task Pattern Is Established

`uploads/tasks.py` provides the sole existing Celery task (`cleanup_expired_upload_files_task`):
- `@shared_task(bind=True, max_retries=2, default_retry_delay=60)`
- Lazy imports inside the task body
- Structured return value (`{"deleted": int, "remaining": int}`)
- Batch processing with a configurable limit

### Celery Beat Is Configured

Contrary to the discussions.md "Design Decision" statement that "there is no Celery Beat infrastructure configured anywhere," the project **does** have celery-beat fully configured (added by PEP 0005):
- `django-celery-beat` is in `INSTALLED_APPS` (`boot/settings.py:34`)
- `CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"` (`boot/settings.py:140`)
- `CELERY_BEAT_SCHEDULE` property defines the cleanup task on a crontab schedule (`boot/settings.py:143-155`)
- `celery-beat` service exists in Docker Compose and Procfile.dev

This means the plan's "Design Decision" about avoiding celery-beat is based on outdated information. A periodic sweep task via celery-beat is now feasible as a complement to on-demand dispatch.

### Upload Models as First Consumer Context

The `uploads` app (`uploads/models.py`) provides the first concrete use case for outbox events. The `create_upload_file()` service in `uploads/services/uploads.py:76-129` creates files with `status=STORED`, which is where a `file.stored` event would naturally be emitted. However, wiring specific event emission into upload services is explicitly out of scope for this PEP.

---

## Key Files & Functions

### Files to Create

| File | Purpose |
|------|---------|
| `common/models.py` | Add `OutboxEvent` model (extend existing file) |
| `common/admin.py` | New file: `OutboxEventAdmin` |
| `common/services/__init__.py` | New file: empty package init |
| `common/services/outbox.py` | New file: `emit_event()` function |
| `common/tasks.py` | New file: `deliver_outbox_events_task` |
| `common/tests/__init__.py` | New file: empty package init |
| `common/tests/test_models.py` | New file: `OutboxEvent` model tests |
| `common/tests/test_services.py` | New file: `emit_event` service tests |
| `common/tests/test_tasks.py` | New file: delivery task tests |
| `common/migrations/__init__.py` | New file: empty package init |
| `common/migrations/0001_initial.py` | Generated: initial migration for `OutboxEvent` |

### Files to Modify

| File | Change |
|------|--------|
| `common/apps.py:6-10` | No change needed — `CommonConfig` doesn't need `ready()` since there are no signals to register |
| `boot/settings.py:143-155` | Optionally add a periodic sweep task to `CELERY_BEAT_SCHEDULE` |

### Pattern Reference Files

| File | Pattern |
|------|---------|
| `uploads/models.py:1-46` | UUID v7 PK, TextChoices status, `db_table`, Meta class, `__str__` |
| `uploads/models.py:163-211` | `UniqueConstraint` definition (UploadPart) |
| `uploads/admin.py:1-91` | Admin registration with `list_display`, `list_filter`, `search_fields`, `readonly_fields` |
| `uploads/services/uploads.py:1-14` | Service module structure (imports, logger) |
| `uploads/services/uploads.py:76-129` | `create_upload_file()` — service function with logging, error handling |
| `uploads/services/uploads.py:221-254` | `finalize_batch()` — `@transaction.atomic` usage |
| `uploads/tasks.py:1-67` | Task conventions (`@shared_task`, lazy imports, structured return, batch processing) |
| `uploads/tests/test_models.py` | Test class structure, `@pytest.mark.django_db`, fixture usage |
| `uploads/tests/test_tasks.py` | Task test pattern, factory fixtures, settings override |
| `common/utils.py:52-73` | `safe_dispatch()` context manager (relevant for wrapping delivery errors) |
| `conftest.py:1-15` | Root-level `user` fixture |

---

## Technical Constraints

### Database / Migrations

1. **The `common` app has never had migrations.** It has no `migrations/` directory. Adding `OutboxEvent` requires creating `common/migrations/__init__.py` and generating the first migration. Django will handle this with `makemigrations common`.

2. **UUID v7 primary key** uses `common.utils.uuid7` (wraps `uuid_utils.uuid7()` to stdlib `uuid.UUID`). All existing UUID models use this pattern. The `uuid_utils` package is already installed (added by PEP 0003).

3. **`DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"`** is set globally in `boot/settings.py:165`. Since `OutboxEvent` uses an explicit `UUIDField(primary_key=True)`, this is overridden and won't affect the migration.

4. **`UniqueConstraint` naming convention**: Existing constraint uses descriptive names (e.g., `"unique_session_part_number"` in `UploadPart`). The outbox constraint should follow: `"unique_event_type_idempotency_key"`.

5. **PostgreSQL partial indexes**: For efficient polling of pending events, a partial index on `(next_attempt_at) WHERE status = 'pending'` would significantly improve query performance as the table grows. This can be added as a Django `Index` with a `condition` parameter.

### Celery Configuration

1. **Serialization is JSON-only**: `CELERY_TASK_SERIALIZER = "json"` and `CELERY_ACCEPT_CONTENT = ["json"]` (`boot/settings.py:129-130`). Task arguments must be JSON-serializable — no Python objects, UUIDs, or datetimes as task args. Pass UUIDs as strings.

2. **Time limits**: `CELERY_TASK_TIME_LIMIT = 300` (5 min hard) and `CELERY_TASK_SOFT_TIME_LIMIT = 240` (4 min soft). The delivery task must process batches within this window.

3. **Eager mode in Dev**: `CELERY_TASK_ALWAYS_EAGER = True` in `Dev` config (`boot/settings.py:183-186`). Tasks run synchronously. `transaction.on_commit()` + `task.delay()` will fire synchronously after the outermost transaction commits. This is correct for development but must be tested.

4. **Broker is PostgreSQL**: `CELERY_BROKER_URL = "sqla+postgresql://..."`. Broker availability is tied to database availability — if the database is up, the broker is up. This eliminates the common "broker down after commit" failure mode seen with Redis/RabbitMQ brokers.

### JSONField Payload

1. **Django's `JSONField` uses PostgreSQL `jsonb`**: Supports native querying (`payload__key`), indexing (GIN), and containment operators. No need for manual serialization.

2. **Default encoder limitation**: `JSONField` defaults to `json.JSONEncoder`, which doesn't handle `UUID`, `Decimal`, `datetime`, or `date`. Either:
   - Set `encoder=DjangoJSONEncoder` on the field, or
   - Require callers to pass pre-serialized payloads (strings for UUIDs, ISO format for datetimes)

   The former is more robust; the latter is more explicit.

### Performance Considerations

1. **`select_for_update(skip_locked=True)`** is PostgreSQL-specific (supported since PostgreSQL 9.5). This is fine since the project requires PostgreSQL 16+.

2. **Batch size for delivery**: The existing cleanup task uses `BATCH_SIZE = 1000`. The delivery task should similarly limit the number of events processed per invocation to stay within `CELERY_TASK_TIME_LIMIT`.

3. **Index on `(status, next_attempt_at)`**: The primary polling query filters by `status='pending'` and `next_attempt_at <= now()`. A composite index on these two fields is essential for performance. A partial index (`WHERE status = 'pending'`) is even better.

---

## Pattern Analysis

### Patterns to Follow

**Model definition pattern** (from `uploads/models.py`):
- Inherit from `TimeStampedModel`
- UUID v7 PK via `from common.utils import uuid7`; `id = models.UUIDField(primary_key=True, default=uuid7, editable=False)`
- Status via `TextChoices` inner class
- Explicit `db_table` in Meta
- `verbose_name` and `verbose_name_plural` in Meta
- `ordering` in Meta
- `__str__` returning a human-readable representation

**UniqueConstraint pattern** (from `uploads/models.py:203-208`):
```python
constraints = [
    models.UniqueConstraint(
        fields=["session", "part_number"],
        name="unique_session_part_number",
    ),
]
```

**Service function pattern** (from `uploads/services/uploads.py`):
- Module-level docstring
- Standard imports → Django imports → third-party → local app
- `logger = logging.getLogger(__name__)`
- Functions take model instances or primitive args, return model instances
- Use `@transaction.atomic` for multi-step operations
- Log success with `logger.info`, failures with `logger.warning`

**Task pattern** (from `uploads/tasks.py`):
- `@shared_task(name="app.tasks.task_name", bind=True, max_retries=2, default_retry_delay=60)`
- Lazy imports at top of function body
- Structured dict return values
- Batch processing with configurable limit

**Admin pattern** (from `uploads/admin.py`):
- `@admin.register(Model)` decorator
- `list_display` with key identifying fields + status + `created_at`
- `list_filter` with status + date
- `search_fields` for lookup-friendly fields
- `readonly_fields` for computed/auto fields
- `list_select_related` for FK optimization
- `date_hierarchy = "created_at"` for date navigation

**Test pattern** (from `uploads/tests/`):
- `@pytest.mark.django_db` on classes that touch the database
- Test classes grouped by concern (e.g., `TestUUIDv7PrimaryKeys`, `TestCascadeRules`, `TestConstraints`)
- Factory fixtures (e.g., `make_upload`) for repeated object creation
- Settings override via `settings` fixture parameter or `@override_settings`
- `pytest.raises` for expected exceptions

### Patterns to Avoid

1. **Do not use `uuid_utils.uuid7` directly in model defaults.** Always use the `common.utils.uuid7` wrapper. This is called out explicitly in `aikb/conventions.md`.

2. **Do not use `IntegerChoices` for status fields.** The project convention is `TextChoices` (string-based), not `IntegerChoices`.

3. **Do not put business logic in models.** The service layer pattern is strictly followed — all logic goes in `{app}/services/`.

4. **Do not put business logic in tasks.** Tasks are thin wrappers that delegate to services (per `aikb/tasks.md` and `aikb/conventions.md`).

5. **Do not use `post_save` signals to trigger delivery.** As noted in discussions.md, `post_save` fires before transaction commit, which would cause the delivery task to not find the event. Use `transaction.on_commit()` instead.

---

## External Research

### Available Third-Party Django Packages

Three packages exist for the transactional outbox pattern in Django. None are a fit for this project's stack:

- **django-outbox-pattern** (58 GitHub stars, MIT, Sept 2025): Built exclusively for STOMP-compatible brokers (RabbitMQ). Not usable with Celery/PostgreSQL.
- **django-jaiminho** (35 stars, Nov 2024): Broker-agnostic, uses `@save_to_outbox` decorator. Requires its own relay worker process alongside Celery. Persistence stores serialized function references (renaming functions breaks replay).
- **django-y-message**: Very low adoption, minimal documentation.

**Verdict**: A custom lightweight implementation is the practical path. The existing codebase already has all the building blocks (Celery, PostgreSQL, `transaction.atomic`, `uuid7`).

### Best Practices for PostgreSQL + Celery Outbox

1. **Single atomic write**: Write the business entity and outbox row in the same `transaction.atomic()` block. The outbox row is committed if and only if the state change succeeds.

2. **Polling with `select_for_update(skip_locked=True)`**: Concurrent workers skip rows locked by others — prevents deadlocks, enables safe parallelism. PostgreSQL-specific but perfectly fine for this project (requires PostgreSQL 9.5+, project targets 16+).

3. **Partial index for poll queries**: `Index(fields=["next_attempt_at"], condition=Q(status="pending"))` avoids full table scans as delivered events accumulate.

4. **`transaction.on_commit()` for fast-path dispatch**: Triggers delivery task immediately after commit. **Critical pitfall**: if the Celery broker is down when `on_commit` fires, the task is silently lost. A periodic sweep task via celery-beat is the mandatory safety net. Since this project uses PostgreSQL as the Celery broker, broker downtime implies database downtime — so this failure mode is less likely here than with Redis/RabbitMQ, but a sweep task is still good practice.

5. **At-least-once semantics**: The outbox pattern guarantees at-least-once delivery. All downstream handlers must be idempotent.

### Exponential Backoff Best Practices

Standard formula: `next_attempt_at = now() + base_delay * (2 ** attempts)` with an optional random jitter and a cap.

Pitfalls:
- **No jitter → retry storms** after broker recovery. Add `random.uniform(0, base_delay * 0.1)` jitter.
- **Unbounded retries**: Must set `max_attempts` and transition to `expired` when exhausted.
- **Error classification**: Distinguish transient failures (network, timeout — retry) from permanent failures (invalid payload — expire immediately). For the initial implementation without handlers, this distinction can be deferred.

### JSONField Payload Considerations

- Django's `JSONField` defaults to `json.JSONEncoder`, which rejects `UUID`, `Decimal`, `datetime`. Use `encoder=DjangoJSONEncoder` on the model field to handle these transparently.
- **`DjangoJSONEncoder` round-tripping loses type info**: `Decimal("9.99")` → `"9.99"` (string), `UUID` → string. Consumers must cast explicitly.
- Include a `"schema_version"` key in payloads for forward compatibility as event schemas evolve.

### Testing `transaction.on_commit()` in Tests

Django's `TestCase` wraps each test in a transaction, so `on_commit` callbacks never fire. Solutions:
- Use `pytest.mark.django_db(transaction=True)` for tests that exercise `on_commit` paths.
- Use Django 4.2+'s `TestCase.captureOnCommitCallbacks()` to inspect callbacks without actually firing them.
- For most unit tests of the service itself, verify the `OutboxEvent` record was created — test the delivery dispatch separately.

---

## Risk & Edge Cases

### Risk 1: First Migration for the `common` App

The `common` app has never had a migration. Creating the first migration requires adding `common/migrations/__init__.py`. If `makemigrations` detects other pending changes in the app (e.g., the abstract `TimeStampedModel` somehow), it could generate unexpected migration operations. **Mitigation**: Run `makemigrations common` and inspect the generated migration carefully before applying.

### Risk 2: `on_commit` in Nested Transactions

If `emit_event()` is called inside a nested `transaction.atomic()` block, the `on_commit` callback only fires when the outermost transaction commits. This is correct behavior but means:
- If the outer transaction rolls back, the outbox event is rolled back too (good — consistency maintained).
- The delivery task fires later than expected (after the outermost commit, not the inner one).

**Edge case**: If a caller wraps `emit_event()` in a savepoint that succeeds, but the outer transaction later rolls back, the outbox event is correctly rolled back — no delivery will occur. This is the desired behavior.

### Risk 3: Delivery Task Re-entrancy

If the delivery task is triggered via `on_commit` and runs eagerly (Dev mode), it runs synchronously within the same thread. If the delivery task itself calls `emit_event()` (e.g., a handler emits a follow-on event), this creates recursive task calls. In eager mode, this is synchronous recursion. **Mitigation**: The initial implementation has no handlers (deferred to consumer PEPs), so this can't happen yet. When handlers are added, document that handlers should not call `emit_event()` synchronously — use `apply_async()` with a delay instead.

### Risk 4: Table Growth Without Cleanup

Successfully delivered events remain in the `outbox_event` table indefinitely. In a busy system, this table will grow without bound. The partial index on `status='pending'` keeps the polling query fast, but the table size affects backups, `pg_dump`, and overall database health. **Mitigation**: A cleanup task should be included (or follow shortly) to delete old delivered events.

### Risk 5: Concurrent Delivery of the Same Event

Without `select_for_update(skip_locked=True)`, two workers could pick up the same pending event simultaneously. Both would attempt delivery, potentially causing double-processing. **Mitigation**: The delivery task must use `select_for_update(skip_locked=True)` within a `transaction.atomic()` block, as specified in discussions.md.

### Risk 6: Test Database Isolation

Tests that verify `transaction.on_commit()` behavior require `pytest.mark.django_db(transaction=True)`, which uses `TransactionTestCase` semantics (truncates tables between tests rather than rolling back). This is slower than the default wrapping approach. **Mitigation**: Only mark the specific tests that exercise `on_commit` with `transaction=True`; other tests can use the standard `@pytest.mark.django_db`.

### Edge Case: Empty Payload

`emit_event()` should accept `payload=None` or `payload={}`. The `JSONField(default=dict)` handles the model default, but the service should normalize `None` to `{}` to avoid storing `null` in the JSON column.

### Edge Case: Very Long Aggregate IDs

`aggregate_id` is `CharField(max_length=100)`. UUID strings are 36 characters, integer PKs are much shorter. But if a model uses a composite PK or a very long natural key, 100 characters might be insufficient. **Mitigation**: 100 characters is generous for current models (all use UUID or integer PKs). Document the limit.

### Edge Case: Idempotency Key Collisions

The `UniqueConstraint(fields=["event_type", "idempotency_key"])` prevents duplicate events of the same type with the same key. If the caller provides a business-derived idempotency key (e.g., `f"{upload_file.pk}"`) for multiple event types on the same aggregate, it won't collide because `event_type` is part of the constraint. But if the caller uses a randomly generated key, duplicate protection is effectively lost (each call produces a unique key). **Mitigation**: Document that idempotency keys should be deterministic and business-derived, not random.

---

## Recommendations

### Implementation Approach

1. **Build model first, then service, then task, then admin, then tests.** This follows dependency order: the task depends on the service, the service depends on the model, admin and tests depend on all of them.

2. **Use `DjangoJSONEncoder` on the `payload` field** to handle `UUID`, `Decimal`, `datetime` serialization transparently. This prevents `TypeError` at emission time when callers include non-primitive types in payloads.

3. **Add a partial index** on `(next_attempt_at) WHERE status = 'pending'` to optimize the delivery poll query. This is a low-cost addition with significant long-term benefit.

4. **Resolve the handler registration thread before implementation.** Recommend Option 4 (defer handlers entirely): the delivery task marks events as `delivered` without calling any handler. This keeps the PEP focused on infrastructure. The handler registration mechanism can be designed when the first consumer PEP needs it.

5. **Include a cleanup task for delivered events.** Follow the `cleanup_expired_upload_files_task` pattern. Use a configurable retention period (e.g., `OUTBOX_RETENTION_HOURS = 168` — 7 days). Register it in `CELERY_BEAT_SCHEDULE` alongside the existing upload cleanup task.

6. **Use on-demand dispatch via `transaction.on_commit()` as the primary delivery mechanism**, complemented by a periodic sweep registered in `CELERY_BEAT_SCHEDULE`. The celery-beat infrastructure is already in place.

### Implementation Order

1. Create `common/migrations/__init__.py` (prerequisite for any migration)
2. Add `OutboxEvent` model to `common/models.py`
3. Generate and apply migration: `makemigrations common && migrate`
4. Create `common/admin.py` with `OutboxEventAdmin`
5. Create `common/services/__init__.py` + `common/services/outbox.py` with `emit_event()`
6. Create `common/tasks.py` with `deliver_outbox_events_task`
7. Optionally add cleanup task and beat schedule entry
8. Create `common/tests/` with test modules
9. Update aikb/ documentation

### Things to Verify During Implementation

- [ ] `makemigrations common` generates exactly one migration with one `CreateModel` operation
- [ ] `python manage.py check` passes after model creation (no system check errors)
- [ ] The `UniqueConstraint` on `(event_type, idempotency_key)` is enforced at the database level
- [ ] `emit_event()` within a `transaction.atomic()` block correctly participates in the caller's transaction
- [ ] `transaction.on_commit()` fires the delivery task after commit in both eager and non-eager modes
- [ ] `select_for_update(skip_locked=True)` works in tests (requires `transaction=True`)
- [ ] Exponential backoff calculation produces the expected `next_attempt_at` values
- [ ] Events exceeding `max_attempts` transition to `expired` status
- [ ] `ruff check .` and `ruff format .` pass on all new files

### Open Questions for Discussions

1. **Handler registration mechanism** (Open Thread in discussions.md): Recommend resolving as Option 4 (defer) before planning begins.
2. **Delivered event cleanup** (Open Thread in discussions.md): Recommend including a cleanup task in this PEP for completeness.
3. **Event ordering** (Open Thread in discussions.md): Recommend Option 1 (no ordering guarantee) for initial implementation.
4. **Eager mode behavior** (Open Thread in discussions.md): Recommend Option 1 (no special handling) — eager mode + `on_commit` is correct and useful.
5. **Celery-beat sweep task**: The discussions.md Design Decision about avoiding celery-beat is based on outdated information. Celery-beat is now fully configured (PEP 0005). Recommend adding a periodic sweep task.
