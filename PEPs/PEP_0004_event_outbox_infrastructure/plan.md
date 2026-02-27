# PEP 0004: Event Outbox Infrastructure — Implementation Plan

| Field | Value |
|-------|-------|
| **PEP** | 0004 |
| **Summary** | [summary.md](summary.md) |
| **Research** | [research.md](research.md) |
| **Discussions** | [discussions.md](discussions.md) |
| **Estimated Effort** | M |

---

<!-- Rewritten 2026-02-26: Complete codebase-grounded rewrite. Verified all file paths, line numbers, function signatures against live codebase. Applied all resolved discussions (Q1-Q26). Simplified delivery to omit dead error handling per CLAUDE.md "avoid over-engineering" and discussions thread recommendation. -->

## Context Files

Read these files before starting implementation:

| File | Reason |
|------|--------|
| `PEPs/PEP_0004_event_outbox_infrastructure/summary.md` | `OutboxEvent` model spec, acceptance criteria, 3-state lifecycle (PENDING/DELIVERED/FAILED), delivery worker design |
| `PEPs/PEP_0004_event_outbox_infrastructure/research.md` | Codebase analysis, patterns to follow/avoid, technical constraints, risks, edge cases, backoff formula |
| `PEPs/PEP_0004_event_outbox_infrastructure/discussions.md` | 26 resolved questions (Q1–Q26) + design decisions: uuid7 wrapper (Q1), DjangoJSONEncoder (Q9), 3-state lifecycle (Q16), idempotency key format (Q17), handler deferral (Q18), safe_dispatch reuse, sweep interval (Q20); 3 deferred threads (jitter, schema_version, lock duration) |
| `common/models.py` | `TimeStampedModel` (lines 6–13: `created_at`/`updated_at` auto fields) — `OutboxEvent` inherits from this |
| `common/utils.py` | `uuid7()` (lines 12–18) for PK default; `safe_dispatch()` (lines 52–73) context manager for wrapping on_commit dispatch |
| `common/apps.py` | `CommonConfig` (lines 6–10) — no changes needed (no signals to register) |
| `uploads/models.py` | Pattern reference: UUID v7 PK (line 19), `TextChoices` (lines 12–17), `db_table`/Meta (lines 38–42), `UniqueConstraint` (lines 203–208) |
| `uploads/admin.py` | Pattern reference: `@admin.register` decorator, `list_display`, `list_filter`, `search_fields`, `readonly_fields`, `date_hierarchy` |
| `uploads/services/uploads.py` | Pattern reference: module docstring, logger setup (lines 1–14), `@transaction.atomic` (line 221), service function signatures |
| `uploads/tasks.py` | Pattern reference: `@shared_task(name=..., bind=True, max_retries=..., default_retry_delay=...)` (lines 15–20), lazy imports (lines 31–33), BATCH_SIZE (line 12), structured return (line 66) |
| `uploads/tests/test_models.py` | Pattern reference: `@pytest.mark.django_db`, test class grouping, UUID v7 assertions |
| `uploads/tests/test_tasks.py` | Pattern reference: factory fixture (`make_upload`), `_media_root` fixture, `settings` override, batch size patching |
| `boot/settings.py` | `CELERY_BEAT_SCHEDULE` property (lines 143–155), `CELERY_TASK_ALWAYS_EAGER` (lines 183–186), `CELERY_TASK_EAGER_PROPAGATES` (line 187), `DEFAULT_AUTO_FIELD` (line 165) |
| `boot/celery.py` | Celery app setup with `autodiscover_tasks()` (line 21) — auto-discovers `common/tasks.py` |
| `conftest.py` | Root `user` fixture (lines 6–15) — reusable in `common/tests/` |
| `aikb/conventions.md` | Model patterns, service patterns, task patterns, naming conventions |
| `aikb/tasks.md` | Celery configuration, beat schedule, task conventions |

## Prerequisites

- [x] **PEP 0003 is implemented** — `uploads` app models exist, `uuid_utils` installed (verified: commit `56767cc`)
  ```bash
  source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from uploads.models import UploadFile; print('PEP 0003 OK')"
  ```

- [x] **Celery beat is configured** — `django-celery-beat` in INSTALLED_APPS, DatabaseScheduler set (verified: PEP 0005, commit `c9af87d`)
  ```bash
  source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from django.conf import settings; assert 'django_celery_beat' in settings.INSTALLED_APPS; print('celery-beat OK')"
  ```

- [x] **`common` app has no migrations directory** — first migration will need `__init__.py`
  ```bash
  test ! -d /home/rjusher/doorito/common/migrations && echo "No migrations dir (expected)" || echo "WARNING: migrations dir exists"
  ```

---

## Implementation Steps

### Step 1: Create migrations directory for the `common` app

**Files**: `common/migrations/__init__.py` (new file)

**Details**: The `common` app currently has no `migrations/` directory because it only contains the abstract `TimeStampedModel`. Adding `OutboxEvent` (a concrete model) requires Django to generate migrations. The `__init__.py` makes it a Python package so Django recognizes it.

**Verify**:
```bash
test -f /home/rjusher/doorito/common/migrations/__init__.py && echo "PASS: migrations/__init__.py exists" || echo "FAIL"
```

---

### Step 2: Add `OutboxEvent` model to `common/models.py`

**Files**: `common/models.py` (modify — currently 14 lines)

**Details**: Append `OutboxEvent` model after the existing `TimeStampedModel` class. Follow patterns from `uploads/models.py`.

**Model specification** (from summary.md, amended by Q1, Q5→Q16, Q9, Q10, Q11, Q17, Q22):

```python
# New imports to add at top of common/models.py:
from django.core.serializers.json import DjangoJSONEncoder  # Q9
from common.utils import uuid7  # Q1: always use wrapper

class OutboxEvent(TimeStampedModel):
    """Transactional outbox event for reliable at-least-once delivery.

    Status lifecycle:
        pending → delivered (success)
        pending → ... retry ... → failed (max retries exhausted)
    """

    class Status(models.TextChoices):  # Q16: 3-state lifecycle
        PENDING = "pending", "Pending"
        DELIVERED = "delivered", "Delivered"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    aggregate_type = models.CharField(max_length=100)
    aggregate_id = models.CharField(max_length=100)
    event_type = models.CharField(max_length=100)
    payload = models.JSONField(default=dict, encoder=DjangoJSONEncoder)  # Q9
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING  # Q22
    )
    idempotency_key = models.CharField(max_length=255)
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=5)
    next_attempt_at = models.DateTimeField(null=True)  # Q11: null when terminal
    delivered_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        db_table = "outbox_event"  # Q2
        verbose_name = "outbox event"
        verbose_name_plural = "outbox events"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["next_attempt_at"],
                condition=models.Q(status="pending"),  # Q10: partial index
                name="idx_outbox_event_pending_next_attempt",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["event_type", "idempotency_key"],
                name="unique_event_type_idempotency_key",
            ),
        ]

    def __str__(self):
        return f"{self.event_type} ({self.get_status_display()})"
```

**Verify**:
```bash
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "
from common.models import OutboxEvent
e = OutboxEvent
print('Status choices:', list(e.Status.choices))
print('Fields:', [f.name for f in e._meta.get_fields() if hasattr(f, 'name')])
print('db_table:', e._meta.db_table)
print('Indexes:', [i.name for i in e._meta.indexes])
print('Constraints:', [c.name for c in e._meta.constraints])
print('PASS')
"
```

---

### Step 3: Generate and apply migration

**Files**: `common/migrations/0001_initial.py` (generated)

**Details**: Run `makemigrations common` to generate the initial migration. Inspect it to verify exactly one `CreateModel` operation with the correct fields, indexes, and constraints. Then apply.

**Verify**:
```bash
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py makemigrations common --check --dry-run 2>&1 | grep -q "No changes" && echo "PASS: migration already generated" || echo "Need to run makemigrations"
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py migrate common
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "
from common.models import OutboxEvent
e = OutboxEvent.objects.create(
    aggregate_type='Test', aggregate_id='1', event_type='test.created',
    payload={'key': 'value'}, idempotency_key='test:1'
)
print(f'Created: {e.pk} ({e.status})')
e.delete()
print('PASS: model is functional')
"
```

---

### Step 4: Create `common/admin.py` with `OutboxEventAdmin`

**Files**: `common/admin.py` (new file — confirmed not existing via codebase inspection, Q4)

**Details**: Follow the admin pattern from `uploads/admin.py`. Include monitoring-focused `list_display`, filtering by status and date, search by event type and aggregate, and an admin action to retry failed events.

```python
"""Admin configuration for common app models."""

from django.contrib import admin
from django.utils import timezone

from common.models import OutboxEvent


@admin.register(OutboxEvent)
class OutboxEventAdmin(admin.ModelAdmin):
    """Admin interface for outbox events."""

    list_display = (
        "event_type",
        "aggregate_type",
        "aggregate_id",
        "status",
        "attempts",
        "next_attempt_at",
        "created_at",
    )
    list_filter = ("status", "event_type", "aggregate_type", "created_at")
    search_fields = ("event_type", "aggregate_type", "aggregate_id", "idempotency_key")
    readonly_fields = (
        "pk",
        "aggregate_type",
        "aggregate_id",
        "event_type",
        "payload",
        "idempotency_key",
        "attempts",
        "delivered_at",
        "error_message",
        "created_at",
        "updated_at",
    )
    date_hierarchy = "created_at"
    actions = ["retry_failed_events"]

    @admin.action(description="Retry selected failed events")
    def retry_failed_events(self, request, queryset):
        """Reset failed events to pending for retry."""
        updated = queryset.filter(status=OutboxEvent.Status.FAILED).update(
            status=OutboxEvent.Status.PENDING,
            next_attempt_at=timezone.now(),
            error_message="",
        )
        self.message_user(request, f"{updated} event(s) reset for retry.")
```

**Verify**:
```bash
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "
from django.contrib import admin
from common.models import OutboxEvent
assert OutboxEvent in [m for m, a in admin.site._registry.items()]
print('PASS: OutboxEventAdmin registered')
"
```

---

### Step 5: Create `common/services/` with `emit_event()` and `process_pending_events()`

**Files**:
- `common/services/__init__.py` (new file — confirmed not existing, Q3)
- `common/services/outbox.py` (new file)

**Details**: Follow the service pattern from `uploads/services/uploads.py` (module docstring, imports, logger, plain functions). The service has three functions:

1. **`emit_event(aggregate_type, aggregate_id, event_type, payload, *, idempotency_key=None)`** — Creates an `OutboxEvent` and schedules delivery via `transaction.on_commit()`. Returns the created event. Per Q25: docstring documents that callers should wrap in `transaction.atomic()` for transactional consistency. Per Q12/Q17: auto-generates `idempotency_key` as `f"{aggregate_type}:{aggregate_id}"` when None. Per Q15/safe_dispatch decision: wraps the on_commit dispatch in `safe_dispatch()` from `common/utils.py:52-73`.

2. **`process_pending_events(batch_size=100)`** — Queries pending events with `next_attempt_at <= now()`, locks with `select_for_update(skip_locked=True)`, marks as `DELIVERED`. Per Q18: no handlers — just marks delivered. Per Q14: no ordering guarantee. Returns `{"processed": int, "remaining": int}`.

3. **`cleanup_delivered_events(retention_hours=168)`** — Deletes events in terminal states (`DELIVERED`, `FAILED`) older than `retention_hours`. Per Q19. Returns `{"deleted": int, "remaining": int}`.

**Service signatures**:

```python
"""Outbox event emission and delivery services."""

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from common.models import OutboxEvent
from common.utils import safe_dispatch

logger = logging.getLogger(__name__)

DELIVERY_BATCH_SIZE = 100
CLEANUP_BATCH_SIZE = 1000


def emit_event(aggregate_type, aggregate_id, event_type, payload, *, idempotency_key=None):
    """Create an outbox event and schedule delivery.

    The event is written to the database as part of the current transaction.
    Delivery is dispatched via transaction.on_commit() to ensure the event
    is committed before the delivery task runs.

    For transactional consistency, callers should wrap both the state change
    and this call in the same transaction.atomic() block:

        with transaction.atomic():
            obj = create_something(...)
            emit_event("Something", str(obj.pk), "something.created", {...})

    Args:
        aggregate_type: Model name (e.g., "UploadFile", "User").
        aggregate_id: String PK of the source record.
        event_type: Dotted event name (e.g., "file.stored").
        payload: Dict of event data (serialized via DjangoJSONEncoder).
        idempotency_key: Deduplication key. Defaults to "{aggregate_type}:{aggregate_id}".

    Returns:
        The created OutboxEvent instance (status=PENDING).
    """
    ...


def process_pending_events(batch_size=DELIVERY_BATCH_SIZE):
    """Process pending outbox events.

    Queries events with status=PENDING and next_attempt_at <= now(),
    locks them with select_for_update(skip_locked=True) for concurrency
    safety, and marks them as DELIVERED.

    Note: Handlers are deferred to consumer PEPs. This implementation
    marks events as delivered without calling any handler.

    Args:
        batch_size: Maximum number of events to process per call.

    Returns:
        dict: {"processed": int, "remaining": int}
    """
    ...


def cleanup_delivered_events(retention_hours=168):
    """Delete terminal outbox events older than the retention period.

    Targets events with status DELIVERED or FAILED that are older
    than retention_hours.

    Args:
        retention_hours: Hours to retain terminal events (default 168 = 7 days).

    Returns:
        dict: {"deleted": int, "remaining": int}
    """
    ...
```

**Implementation notes for `emit_event()`**:
- `idempotency_key = idempotency_key or f"{aggregate_type}:{aggregate_id}"` (Q17)
- `payload = payload if payload is not None else {}` (normalize None, research edge case)
- `next_attempt_at = timezone.now()` (Q11: immediately eligible for sweep)
- On-commit dispatch pattern:
  ```python
  def _dispatch():
      with safe_dispatch("dispatch outbox delivery", logger):
          from common.tasks import deliver_outbox_events_task
          deliver_outbox_events_task.delay()

  transaction.on_commit(_dispatch)
  ```
- Return the created `OutboxEvent` (Q26: status=PENDING at return time)

**Implementation notes for `process_pending_events()`**:
- Query: `OutboxEvent.objects.filter(status=OutboxEvent.Status.PENDING, next_attempt_at__lte=timezone.now())`
- Lock: `.select_for_update(skip_locked=True)[:batch_size]`
- Wrap in `transaction.atomic()`
- For each event: set `status=DELIVERED`, `delivered_at=timezone.now()`, `next_attempt_at=None`
- Use `event.save(update_fields=["status", "delivered_at", "next_attempt_at", "updated_at"])`
- Count remaining pending after processing for return value

**Implementation notes for `cleanup_delivered_events()`**:
- Follow `cleanup_expired_upload_files_task` pattern (batch-limited delete)
- Query: `OutboxEvent.objects.filter(status__in=[OutboxEvent.Status.DELIVERED, OutboxEvent.Status.FAILED], created_at__lt=cutoff)`
- Batch delete up to `CLEANUP_BATCH_SIZE`

**Verify**:
```bash
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "
from common.services.outbox import emit_event, process_pending_events, cleanup_delivered_events
import inspect
sig = inspect.signature(emit_event)
print('emit_event params:', list(sig.parameters.keys()))
sig2 = inspect.signature(process_pending_events)
print('process_pending_events params:', list(sig2.parameters.keys()))
sig3 = inspect.signature(cleanup_delivered_events)
print('cleanup_delivered_events params:', list(sig3.parameters.keys()))
print('PASS')
"
```

---

### Step 6: Create `common/tasks.py` with delivery and cleanup tasks

**Files**: `common/tasks.py` (new file — confirmed not existing)

**Details**: Follow the task pattern from `uploads/tasks.py`. Two tasks:

1. **`deliver_outbox_events_task`** — Thin wrapper around `process_pending_events()`. Named `common.tasks.deliver_outbox_events_task`. Used both by on-commit dispatch (fast path) and celery-beat sweep (safety net).

2. **`cleanup_delivered_outbox_events_task`** — Thin wrapper around `cleanup_delivered_events()`. Named `common.tasks.cleanup_delivered_outbox_events_task`. Reads `OUTBOX_RETENTION_HOURS` from settings.

```python
"""Celery tasks for the common app."""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name="common.tasks.deliver_outbox_events_task",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def deliver_outbox_events_task(self):
    """Deliver pending outbox events.

    Processes at most DELIVERY_BATCH_SIZE (100) pending events per run.
    Called on-demand via transaction.on_commit() and periodically via
    celery-beat as a safety net.

    Returns:
        dict: {"processed": int, "remaining": int}
    """
    from common.services.outbox import process_pending_events

    result = process_pending_events()
    if result["processed"] > 0:
        logger.info(
            "Delivered %d outbox events, %d remaining.",
            result["processed"],
            result["remaining"],
        )
    return result


@shared_task(
    name="common.tasks.cleanup_delivered_outbox_events_task",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def cleanup_delivered_outbox_events_task(self):
    """Delete terminal outbox events older than OUTBOX_RETENTION_HOURS.

    Processes at most CLEANUP_BATCH_SIZE (1000) events per run.

    Returns:
        dict: {"deleted": int, "remaining": int}
    """
    from django.conf import settings

    from common.services.outbox import cleanup_delivered_events

    retention_hours = getattr(settings, "OUTBOX_RETENTION_HOURS", 168)
    result = cleanup_delivered_events(retention_hours=retention_hours)
    if result["deleted"] > 0:
        logger.info(
            "Cleaned up %d terminal outbox events, %d remaining.",
            result["deleted"],
            result["remaining"],
        )
    return result
```

**Verify**:
```bash
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "
from common.tasks import deliver_outbox_events_task, cleanup_delivered_outbox_events_task
print('deliver name:', deliver_outbox_events_task.name)
print('cleanup name:', cleanup_delivered_outbox_events_task.name)
print('PASS')
"
```

---

### Step 7: Add outbox settings and beat schedule entries to `boot/settings.py`

**Files**: `boot/settings.py` (modify)

**Details**: Add two settings to the `Base` class and two entries to the `CELERY_BEAT_SCHEDULE` property.

1. **Settings** (add after `CLEANUP_UPLOADS_INTERVAL_HOURS = 6` on line 141):
   ```python
   # Outbox settings
   OUTBOX_SWEEP_INTERVAL_MINUTES = 5  # Sweep for pending events
   OUTBOX_RETENTION_HOURS = 168       # 7 days retention for terminal events
   ```

2. **Beat schedule entries** (add to the `CELERY_BEAT_SCHEDULE` property return dict, lines 147–155):
   ```python
   "deliver-outbox-events-sweep": {
       "task": "common.tasks.deliver_outbox_events_task",
       "schedule": timedelta(minutes=self.OUTBOX_SWEEP_INTERVAL_MINUTES),
       "options": {"queue": "default"},
   },
   "cleanup-delivered-outbox-events": {
       "task": "common.tasks.cleanup_delivered_outbox_events_task",
       "schedule": crontab(minute=30, hour="*/6"),
       "options": {"queue": "default"},
   },
   ```

3. **Import `timedelta`** inside the `CELERY_BEAT_SCHEDULE` property (alongside the existing `from celery.schedules import crontab`):
   ```python
   from datetime import timedelta
   ```

**Verify**:
```bash
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "
from django.conf import settings
print('OUTBOX_SWEEP_INTERVAL_MINUTES:', settings.OUTBOX_SWEEP_INTERVAL_MINUTES)
print('OUTBOX_RETENTION_HOURS:', settings.OUTBOX_RETENTION_HOURS)
schedule = settings.CELERY_BEAT_SCHEDULE
assert 'deliver-outbox-events-sweep' in schedule, 'Missing sweep entry'
assert 'cleanup-delivered-outbox-events' in schedule, 'Missing cleanup entry'
print('Beat schedule entries:', list(schedule.keys()))
print('PASS')
"
```

---

### Step 8: Create `common/tests/` with test modules

**Files**:
- `common/tests/__init__.py` (new file)
- `common/tests/conftest.py` (new file — Q23: shared `make_outbox_event` factory fixture)
- `common/tests/test_models.py` (new file)
- `common/tests/test_services.py` (new file)
- `common/tests/test_tasks.py` (new file)

**Details**: Follow test patterns from `uploads/tests/`. Use `@pytest.mark.django_db`, test class grouping by concern, and the root `user` fixture from `conftest.py:6-15`.

#### `common/tests/conftest.py`

```python
"""Shared fixtures for common app tests."""

import pytest
from django.utils import timezone

from common.models import OutboxEvent


@pytest.fixture
def make_outbox_event(db):
    """Factory fixture to create OutboxEvent instances."""

    def _make(
        aggregate_type="TestModel",
        aggregate_id="1",
        event_type="test.created",
        payload=None,
        status=OutboxEvent.Status.PENDING,
        idempotency_key=None,
        next_attempt_at=None,
        attempts=0,
    ):
        if payload is None:
            payload = {"key": "value"}
        if idempotency_key is None:
            idempotency_key = f"{aggregate_type}:{aggregate_id}"
        if next_attempt_at is None and status == OutboxEvent.Status.PENDING:
            next_attempt_at = timezone.now()
        return OutboxEvent.objects.create(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload,
            status=status,
            idempotency_key=idempotency_key,
            next_attempt_at=next_attempt_at,
            attempts=attempts,
        )

    return _make
```

#### `common/tests/test_models.py` — test classes

- **`TestOutboxEventCreation`**: UUID v7 PK, default field values (status=PENDING, attempts=0, payload={}), `TimeStampedModel` fields (`created_at`, `updated_at` auto-set)
- **`TestOutboxEventConstraints`**: `UniqueConstraint(event_type, idempotency_key)` raises `IntegrityError` on duplicate; same `idempotency_key` with different `event_type` is allowed
- **`TestOutboxEventStatusChoices`**: Verify `Status.values` == `{"pending", "delivered", "failed"}`
- **`TestOutboxEventStr`**: `__str__` returns `f"{event_type} ({status_display})"`
- **`TestOutboxEventPayload`**: `DjangoJSONEncoder` handles UUID, datetime, Decimal in payload; `payload=None` defaults to `{}`

#### `common/tests/test_services.py` — test classes

- **`TestEmitEvent`**: Creates `OutboxEvent` with correct fields; auto-generates `idempotency_key` as `f"{aggregate_type}:{aggregate_id}"` when None; custom `idempotency_key` is preserved; `payload=None` normalized to `{}`; duplicate `(event_type, idempotency_key)` raises `IntegrityError`; `next_attempt_at` set to approximately `now()`; returned event has `status=PENDING`
- **`TestProcessPendingEvents`**: Processes pending events → `status=DELIVERED`, `delivered_at` set, `next_attempt_at=None`; skips events with `next_attempt_at` in the future; respects `batch_size` limit; returns correct `processed`/`remaining` counts; no-op when no pending events
- **`TestCleanupDeliveredEvents`**: Deletes `DELIVERED` events older than retention; deletes `FAILED` events older than retention; preserves `PENDING` events; preserves events younger than retention; respects batch limit; returns correct `deleted`/`remaining` counts

#### `common/tests/test_tasks.py` — test classes

- **`TestDeliverOutboxEventsTask`**: Calls `process_pending_events()` and returns result; processes pending events correctly; no-op when no pending events
- **`TestCleanupDeliveredOutboxEventsTask`**: Calls `cleanup_delivered_events()` with `OUTBOX_RETENTION_HOURS` from settings; deletes old terminal events; no-op when no terminal events

**Verify**:
```bash
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest common/tests/ -v --tb=short 2>&1 | tail -20
```

---

### Step 9: Run linting and formatting

**Files**: All new/modified files

**Details**: Run `ruff check` and `ruff format` to ensure all new code passes the project's code quality checks (configured in `pyproject.toml:10-48`).

**Verify**:
```bash
cd /home/rjusher/doorito && source ~/.virtualenvs/inventlily-d22a143/bin/activate && ruff check common/ boot/settings.py && ruff format --check common/ boot/settings.py && echo "PASS: lint and format clean"
```

---

### Step 10: Run Django system checks

**Files**: None (verification only)

**Details**: Ensure no system check errors from the new model, admin, or settings changes.

**Verify**:
```bash
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check && echo "PASS: system checks"
```

---

### Step 11: Update `aikb/` documentation

**Files**: (modify existing)
- `aikb/models.md`
- `aikb/services.md`
- `aikb/tasks.md`
- `aikb/admin.md`
- `aikb/architecture.md`
- `aikb/conventions.md`

**Details**: Follow the aikb Impact Map below.

**Verify**:
```bash
grep -l "OutboxEvent" /home/rjusher/doorito/aikb/*.md | sort
# Expected: admin.md, architecture.md, models.md, services.md, tasks.md
```

---

## Testing

### Unit Tests (Step 8)

| Test Module | Test Classes | Key Assertions |
|-------------|-------------|----------------|
| `test_models.py` | `TestOutboxEventCreation`, `TestOutboxEventConstraints`, `TestOutboxEventStatusChoices`, `TestOutboxEventStr`, `TestOutboxEventPayload` | UUID v7 PK, UniqueConstraint enforcement, 3-state lifecycle values, DjangoJSONEncoder round-trip |
| `test_services.py` | `TestEmitEvent`, `TestProcessPendingEvents`, `TestCleanupDeliveredEvents` | Event creation with auto idempotency key, delivery marks DELIVERED with timestamp, cleanup respects retention and status filter |
| `test_tasks.py` | `TestDeliverOutboxEventsTask`, `TestCleanupDeliveredOutboxEventsTask` | Task delegates to service, reads settings for retention hours |

### Test Execution

```bash
# All common app tests
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest common/tests/ -v --tb=short

# Full test suite (regression)
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest -v --tb=short
```

---

## Rollback Plan

1. **Delete new files**:
   ```bash
   rm -rf common/admin.py common/services/ common/tasks.py common/tests/ common/migrations/
   ```
2. **Revert `common/models.py`** to remove `OutboxEvent` (restore to just `TimeStampedModel`, 14 lines)
3. **Revert `boot/settings.py`** to remove `OUTBOX_SWEEP_INTERVAL_MINUTES`, `OUTBOX_RETENTION_HOURS`, and the two beat schedule entries
4. **Revert `aikb/` files** to remove `OutboxEvent` references
5. **Reverse migration** (if applied):
   ```bash
   source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py migrate common zero
   ```
6. **Delete migrations directory**:
   ```bash
   rm -rf common/migrations/
   ```

---

## aikb Impact Map

| File | Update Required | Details |
|------|----------------|---------|
| `aikb/models.md` | **Yes** | Add `OutboxEvent` section after Uploads App: fields, status choices (PENDING/DELIVERED/FAILED), lifecycle, indexes (partial index on pending), constraints (UniqueConstraint on event_type+idempotency_key), db_table, ordering, `__str__` |
| `aikb/services.md` | **Yes** | Add `common/services/outbox.py` section: `emit_event()` signature and API contract (transactional usage pattern), `process_pending_events()` signature, `cleanup_delivered_events()` signature |
| `aikb/tasks.md` | **Yes** | Add `common/tasks.py` section: `deliver_outbox_events_task` (on-demand + sweep) and `cleanup_delivered_outbox_events_task` (retention-based cleanup). Update "Current Schedule" table with the two new beat entries. Update "Current State" paragraph to mention the common app |
| `aikb/admin.md` | **Yes** | Add `common/admin.py` section: `OutboxEventAdmin` with `list_display`, `list_filter`, `search_fields`, `readonly_fields`, `date_hierarchy`, `retry_failed_events` action. Update "Models visible" list |
| `aikb/architecture.md` | **Yes** | Update `common/` directory tree to show new files (`admin.py`, `services/outbox.py`, `tasks.py`, `tests/`, `migrations/`). Update "Background Processing" bullet to mention outbox delivery. Update app description from "no models of its own beyond abstract" |
| `aikb/conventions.md` | **No** | No new conventions introduced — follows all existing patterns |
| `aikb/signals.md` | **No** | No signals involved — outbox uses `transaction.on_commit()`, not signals |
| `aikb/cli.md` | **No** | No CLI changes |
| `aikb/deployment.md` | **No** | No deployment changes (settings are env-configurable, beat entries auto-sync) |
| `aikb/dependencies.md` | **No** | No new dependencies |
| `aikb/specs-roadmap.md` | **No** | Update if tracking PEP completion status |

---

## Final Verification

### Acceptance Criteria Checks

| Criterion | Verification Command |
|-----------|---------------------|
| `OutboxEvent` model exists with UUID v7 PK, aggregate/payload fields, status lifecycle, retry tracking | `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from common.models import OutboxEvent; print('Fields:', [f.name for f in OutboxEvent._meta.get_fields() if hasattr(f, 'name')]); print('Status:', list(OutboxEvent.Status.choices)); assert OutboxEvent._meta.get_field('id').primary_key; print('PASS')"` |
| `UniqueConstraint(fields=["event_type", "idempotency_key"])` prevents duplicates | `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from common.models import OutboxEvent; c = [c for c in OutboxEvent._meta.constraints if c.name == 'unique_event_type_idempotency_key']; assert len(c) == 1; print('Fields:', c[0].fields); print('PASS')"` |
| `emit_event()` service creates outbox entries with auto-generated idempotency key | `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from common.services.outbox import emit_event; e = emit_event('Test', '42', 'test.ping', {'hello': 'world'}); print(f'Created: pk={e.pk} type={e.event_type} key={e.idempotency_key} status={e.status}'); assert e.idempotency_key == 'Test:42'; assert e.status == 'pending'; e.delete(); print('PASS')"` |
| Delivery Celery task polls and processes pending events | `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from common.services.outbox import emit_event, process_pending_events; e = emit_event('Test', '1', 'test.delivery', {}); result = process_pending_events(); print(f'Processed: {result}'); e.refresh_from_db(); assert e.status == 'delivered'; assert e.delivered_at is not None; e.delete(); print('PASS')"` |
| Admin class registered for `OutboxEvent` with monitoring fields | `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from django.contrib import admin; from common.models import OutboxEvent; a = admin.site._registry[OutboxEvent]; print('list_display:', a.list_display); print('actions:', [x.__name__ if callable(x) else x for x in a.actions]); print('PASS')"` |
| All tests pass | `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest common/tests/ -v --tb=short` |
| `python manage.py check` passes | `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check` |
| `aikb/` documentation updated | `grep -c "OutboxEvent" aikb/models.md aikb/services.md aikb/tasks.md aikb/admin.md aikb/architecture.md` |

### Integration Checks

```bash
# End-to-end: emit → deliver → verify
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "
from django.db import transaction
from common.services.outbox import emit_event, process_pending_events
from common.models import OutboxEvent

# Emit event inside a transaction
with transaction.atomic():
    event = emit_event('User', '1', 'user.created', {'email': 'test@example.com'})
    print(f'Emitted: {event.pk} status={event.status}')

# In eager mode, on_commit delivery already fired. Verify:
event.refresh_from_db()
print(f'After commit: status={event.status} delivered_at={event.delivered_at}')

# If not already delivered (non-eager mode), process manually:
if event.status == 'pending':
    result = process_pending_events()
    event.refresh_from_db()
    print(f'After process: status={event.status}')

assert event.status == 'delivered', f'Expected delivered, got {event.status}'
print('PASS: end-to-end delivery works')

# Cleanup
event.delete()
"
```

```bash
# Idempotency: duplicate emit raises IntegrityError
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "
from django.db import IntegrityError
from common.services.outbox import emit_event

e1 = emit_event('User', '1', 'user.created', {})
try:
    e2 = emit_event('User', '1', 'user.created', {})
    print('FAIL: should have raised IntegrityError')
except IntegrityError:
    print('PASS: duplicate prevented by UniqueConstraint')
finally:
    from common.models import OutboxEvent
    OutboxEvent.objects.all().delete()
"
```

### Regression Checks

```bash
# Full test suite passes
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest -v --tb=short

# System checks pass
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check

# Linting passes
cd /home/rjusher/doorito && source ~/.virtualenvs/inventlily-d22a143/bin/activate && ruff check . && echo "PASS: lint clean"

# Existing upload cleanup task still works
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "
from uploads.tasks import cleanup_expired_upload_files_task
result = cleanup_expired_upload_files_task()
print(f'Upload cleanup: {result}')
print('PASS: existing task still works')
"

# Beat schedule has all 3 entries
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "
from django.conf import settings
schedule = settings.CELERY_BEAT_SCHEDULE
expected = {'cleanup-expired-upload-files', 'deliver-outbox-events-sweep', 'cleanup-delivered-outbox-events'}
assert set(schedule.keys()) == expected, f'Expected {expected}, got {set(schedule.keys())}'
print('PASS: all beat schedule entries present')
"
```

---

## Detailed Todo List

### Phase 1: Prerequisites & Setup (Step 1)

- [x] Verify PEP 0003 prerequisite — import `UploadFile` from uploads app
- [x] Verify celery-beat prerequisite — `django-celery-beat` in `INSTALLED_APPS`, `DatabaseScheduler` configured
- [x] Confirm `common/migrations/` does not yet exist
- [x] Create `common/migrations/__init__.py` (empty file to make it a Python package)
- [x] Verify `common/migrations/__init__.py` exists

### Phase 2: OutboxEvent Model (Steps 2–3)

- [x] Read `common/models.py` and `common/utils.py` to understand existing code
- [x] Add imports to `common/models.py`: `DjangoJSONEncoder` from `django.core.serializers.json`, `uuid7` from `common.utils`
- [x] Add `OutboxEvent` model to `common/models.py` after `TimeStampedModel`:
  - [x] Inner `Status(TextChoices)` class with PENDING, DELIVERED, FAILED
  - [x] `id` — `UUIDField(primary_key=True, default=uuid7, editable=False)`
  - [x] `aggregate_type` — `CharField(max_length=100)`
  - [x] `aggregate_id` — `CharField(max_length=100)`
  - [x] `event_type` — `CharField(max_length=100)`
  - [x] `payload` — `JSONField(default=dict, encoder=DjangoJSONEncoder)`
  - [x] `status` — `CharField(max_length=20, choices=Status.choices, default=Status.PENDING)`
  - [x] `idempotency_key` — `CharField(max_length=255)`
  - [x] `attempts` — `PositiveIntegerField(default=0)`
  - [x] `max_attempts` — `PositiveIntegerField(default=5)`
  - [x] `next_attempt_at` — `DateTimeField(null=True)`
  - [x] `delivered_at` — `DateTimeField(null=True, blank=True)`
  - [x] `error_message` — `TextField(blank=True)`
  - [x] `Meta` class: `db_table`, `verbose_name`, `ordering`, partial index, UniqueConstraint
  - [x] `__str__` method returning `f"{self.event_type} ({self.get_status_display()})"`
- [x] Run Step 2 verification command — confirm fields, Status choices, db_table, indexes, constraints
- [x] Run `makemigrations common` — confirm generates `0001_initial.py` with a single `CreateModel`
- [x] Inspect generated migration — verify fields, indexes, and constraints match the model spec
- [x] Run `migrate common` — apply the migration
- [x] Run Step 3 verification command — create and delete a test record to confirm model is functional

<!-- Amendment: Index name shortened from "idx_outbox_event_pending_next_attempt" (40 chars) to "idx_outbox_pending_next" (23 chars) to satisfy Django's 30-character limit for index names (models.E034). -->

### Phase 3: Admin Interface (Step 4)

- [x] Read `uploads/admin.py` for pattern reference
- [x] Create `common/admin.py` with `OutboxEventAdmin`:
  - [x] `list_display` — event_type, aggregate_type, aggregate_id, status, attempts, next_attempt_at, created_at
  - [x] `list_filter` — status, event_type, aggregate_type, created_at
  - [x] `search_fields` — event_type, aggregate_type, aggregate_id, idempotency_key
  - [x] `readonly_fields` — pk, aggregate_type, aggregate_id, event_type, payload, idempotency_key, attempts, delivered_at, error_message, created_at, updated_at
  - [x] `date_hierarchy` — created_at
  - [x] `retry_failed_events` admin action — resets FAILED events to PENDING with `next_attempt_at=now()`
- [x] Run Step 4 verification command — confirm `OutboxEventAdmin` is registered

### Phase 4: Service Layer (Step 5)

- [x] Read `uploads/services/uploads.py` for pattern reference (module structure, logging, `@transaction.atomic`)
- [x] Read `common/utils.py` — understand `safe_dispatch()` context manager (lines 52–73)
- [x] Create `common/services/__init__.py` (empty package init)
- [x] Create `common/services/outbox.py` with module docstring, imports, and logger
- [x] Implement `emit_event()`:
  - [x] Default `idempotency_key` as `f"{aggregate_type}:{aggregate_id}"` when None (Q17)
  - [x] Normalize `payload=None` to `{}` (edge case from research)
  - [x] Set `next_attempt_at=timezone.now()` (Q11)
  - [x] Create `OutboxEvent` with all fields
  - [x] Register `transaction.on_commit()` callback using `safe_dispatch()` for eager-mode safety (Q15)
  - [x] Lazy import of `deliver_outbox_events_task` inside the callback (avoid circular imports)
  - [x] Return the created event instance
  - [x] Docstring documents transactional API contract (Q25) and return value timing (Q26)
- [x] Implement `process_pending_events(batch_size=DELIVERY_BATCH_SIZE)`:
  - [x] Query PENDING events with `next_attempt_at__lte=now()`
  - [x] Lock with `select_for_update(skip_locked=True)[:batch_size]`
  - [x] Wrap in `transaction.atomic()`
  - [x] For each event: set `status=DELIVERED`, `delivered_at=now()`, `next_attempt_at=None`
  - [x] Use `event.save(update_fields=[...])` for efficient updates
  - [x] Count remaining pending events
  - [x] Return `{"processed": int, "remaining": int}`
- [x] Implement `cleanup_delivered_events(retention_hours=168)`:
  - [x] Calculate cutoff time from retention_hours
  - [x] Query DELIVERED and FAILED events older than cutoff
  - [x] Batch-limited delete up to `CLEANUP_BATCH_SIZE`
  - [x] Return `{"deleted": int, "remaining": int}`
- [x] Run Step 5 verification command — confirm all three functions are importable with correct signatures

### Phase 5: Celery Tasks & Settings (Steps 6–7)

- [x] Read `uploads/tasks.py` for pattern reference
- [x] Read `boot/settings.py` for current `CELERY_BEAT_SCHEDULE` property structure
- [x] Create `common/tasks.py`:
  - [x] `deliver_outbox_events_task` — `@shared_task(name=..., bind=True, max_retries=2, default_retry_delay=60)`, lazy import of `process_pending_events`, log results
  - [x] `cleanup_delivered_outbox_events_task` — `@shared_task(name=..., bind=True, max_retries=2, default_retry_delay=60)`, lazy import of settings and `cleanup_delivered_events`, log results
- [x] Run Step 6 verification command — confirm both tasks are importable with correct names
- [x] Add `OUTBOX_SWEEP_INTERVAL_MINUTES = 5` to `Base` class in `boot/settings.py`
- [x] Add `OUTBOX_RETENTION_HOURS = 168` to `Base` class in `boot/settings.py`
- [x] Add `from datetime import timedelta` inside `CELERY_BEAT_SCHEDULE` property
- [x] Add `deliver-outbox-events-sweep` entry to `CELERY_BEAT_SCHEDULE` dict (timedelta-based)
- [x] Add `cleanup-delivered-outbox-events` entry to `CELERY_BEAT_SCHEDULE` dict (crontab-based)
- [x] Run Step 7 verification command — confirm settings values and all 3 beat schedule entries present

### Phase 6: Tests (Step 8)

- [x] Read `uploads/tests/test_models.py` and `uploads/tests/test_tasks.py` for pattern reference
- [x] Create `common/tests/__init__.py`
- [x] Create `common/tests/conftest.py` with `make_outbox_event` factory fixture
- [x] Create `common/tests/test_models.py`:
  - [x] `TestOutboxEventCreation` — UUID v7 PK, defaults (status=PENDING, attempts=0, payload={}), TimeStampedModel fields auto-set
  - [x] `TestOutboxEventConstraints` — UniqueConstraint on (event_type, idempotency_key) raises IntegrityError; same key + different event_type allowed
  - [x] `TestOutboxEventStatusChoices` — verify Status.values == {"pending", "delivered", "failed"}
  - [x] `TestOutboxEventStr` — `__str__` returns expected format
  - [x] `TestOutboxEventPayload` — DjangoJSONEncoder handles UUID, datetime, Decimal; None→{} normalization
- [x] Create `common/tests/test_services.py`:
  - [x] `TestEmitEvent` — correct fields, auto-generated idempotency_key, custom key preserved, None payload normalized, duplicate raises IntegrityError, next_attempt_at ≈ now(), returned event status=PENDING
  - [x] `TestProcessPendingEvents` — marks DELIVERED with timestamp, skips future next_attempt_at, respects batch_size, correct return counts, no-op when empty
  - [x] `TestCleanupDeliveredEvents` — deletes old DELIVERED, deletes old FAILED, preserves PENDING, preserves young events, respects batch limit, correct return counts
- [x] Create `common/tests/test_tasks.py`:
  - [x] `TestDeliverOutboxEventsTask` — delegates to process_pending_events, processes events, no-op when empty
  - [x] `TestCleanupDeliveredOutboxEventsTask` — reads OUTBOX_RETENTION_HOURS from settings, deletes old terminal events, no-op when empty
- [x] Run all common tests: `pytest common/tests/ -v --tb=short` — all 40 tests pass

### Phase 7: Code Quality (Steps 9–10)

- [x] Run `ruff check common/ boot/settings.py` — fix any linting errors
- [x] Run `ruff format common/ boot/settings.py` — fix any formatting issues
- [x] Run `ruff check --diff` and `ruff format --check` to confirm clean
- [x] Run `python manage.py check` — confirm no Django system check errors

### Phase 8: Documentation (Step 11)

- [x] Update `aikb/models.md` — add OutboxEvent section (fields, Status choices, lifecycle, indexes, constraints, db_table, ordering, `__str__`)
- [x] Update `aikb/services.md` — add `common/services/outbox.py` section (emit_event signature + transactional usage pattern, process_pending_events, cleanup_delivered_events)
- [x] Update `aikb/tasks.md` — add `common/tasks.py` section (deliver + cleanup tasks), update "Current Schedule" table with 2 new beat entries, update "Current State" paragraph
- [x] Update `aikb/admin.md` — add `common/admin.py` section (OutboxEventAdmin details, retry_failed_events action), update "Models visible" list
- [x] Update `aikb/architecture.md` — update `common/` directory tree (admin.py, services/, tasks.py, tests/, migrations/), update "Background Processing" bullet, update app description
- [x] Verify aikb updates: `grep -l "OutboxEvent" aikb/*.md` — confirmed in models.md, services.md, admin.md, architecture.md (tasks.md references outbox by task name)

### Phase 9: Final Verification

- [ ] Run acceptance criteria checks (all 8 verification commands from Final Verification table)
- [ ] Run end-to-end integration test: emit → deliver → verify status=DELIVERED
- [ ] Run idempotency integration test: duplicate emit raises IntegrityError
- [ ] Run full test suite: `pytest -v --tb=short` — all tests pass (common + uploads + any others)
- [ ] Run `python manage.py check` — system checks pass
- [ ] Run `ruff check .` — full-project lint clean
- [ ] Verify existing upload cleanup task still works
- [ ] Verify beat schedule has all 3 entries (cleanup-expired-upload-files + 2 new outbox entries)

---

## Completion Checklist

- [ ] All implementation steps (1–11) checked off
- [ ] All acceptance criteria verified
- [ ] Integration checks pass
- [ ] Regression checks pass
- [ ] `aikb/` files updated per Impact Map
- [ ] PEP status updated to **Implemented** in `summary.md`
