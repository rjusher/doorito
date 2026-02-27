# PEP 0017: Durable Outbox Dispatcher — Implementation Plan

| Field | Value |
|-------|-------|
| **PEP** | 0017 |
| **Summary** | [summary.md](summary.md) |
| **Estimated Effort** | L |

---

## Context Files

- `aikb/models.md` — PortalEventOutbox model (from PEP 0008)
- `aikb/tasks.md` — Celery task conventions, periodic task configuration
- `aikb/services.md` — Service conventions, existing outbox delivery pattern
- `common/services/outbox.py` — Existing outbox process/delivery pattern for reference
- `common/tasks.py` — Existing outbox delivery task for reference
- `boot/settings.py` — Celery beat schedule configuration

## Prerequisites

- PEP 0008 (Canonical Domain Model) implemented
- PEP 0014 (Finalize Upload) implemented
- PEP 0016 (Event Schema) implemented

## Implementation Steps

- [ ] **Step 1**: Create dispatcher service
  - Files: Portal app `services/dispatcher.py`
  - Details: `dispatch_pending_events()` — select eligible rows with SKIP LOCKED, POST to runner, update status
  - Verify: Unit tests with mocked HTTP

- [ ] **Step 2**: Implement backoff logic
  - Files: Portal app `services/dispatcher.py`
  - Details: Exponential backoff with cap and optional jitter for `next_attempt_at` calculation
  - Verify: Unit tests for backoff timing

- [ ] **Step 3**: Create Celery periodic task
  - Files: Portal app `tasks.py`
  - Details: `dispatch_portal_events_task` — shared_task wrapping dispatcher service
  - Verify: Task registered in Celery

- [ ] **Step 4**: Add to celery-beat schedule
  - Files: `boot/settings.py`
  - Details: Add periodic schedule entry for dispatch task
  - Verify: `python manage.py check`

- [ ] **Step 5**: Add configuration settings
  - Files: `boot/settings.py`
  - Details: Runner endpoint URL, auth secret, base delay, max delay, sweep interval
  - Verify: Settings accessible in Dev configuration

- [ ] **Step 6**: Wire on-commit trigger from finalization
  - Files: Portal app `services/finalize.py`
  - Details: `transaction.on_commit` calls `dispatch_portal_events_task.delay()`
  - Verify: Integration test verifying task enqueued after finalization

## Testing

- [ ] Unit tests for dispatcher service (success, failure, backoff, concurrent locking)
- [ ] Unit tests for backoff calculation
- [ ] Integration test for full flow (finalize → outbox → dispatch → delivered)

## Rollback Plan

- Remove periodic task from beat schedule
- Remove dispatcher service and task
- Remove on-commit trigger from finalization

## aikb Impact Map

- [ ] `aikb/models.md` — N/A
- [ ] `aikb/services.md` — Add dispatcher service documentation
- [ ] `aikb/tasks.md` — Add dispatch_portal_events_task documentation
- [ ] `aikb/signals.md` — N/A
- [ ] `aikb/admin.md` — N/A
- [ ] `aikb/cli.md` — N/A
- [ ] `aikb/architecture.md` — Document outbox dispatch flow
- [ ] `aikb/conventions.md` — N/A
- [ ] `aikb/dependencies.md` — N/A
- [ ] `aikb/specs-roadmap.md` — Update
- [ ] `CLAUDE.md` — Add runner endpoint configuration, update Celery section

## Final Verification

### Acceptance Criteria

- [ ] **Durability**: Stop runner, finalize file, restart runner → event delivered
  - Verify: Integration test with mocked runner downtime
- [ ] **No double-send**: Run 2 dispatchers concurrently → each event delivered once
  - Verify: Concurrent test with SKIP LOCKED verification
- [ ] **Backoff**: Failed event has increasing next_attempt_at
  - Verify: Unit test checking timestamps after repeated failures

### Regression Checks

- [ ] `python manage.py check` passes
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check`
- [ ] `ruff check .` passes
  - Verify: `ruff check .`

## Completion

- [ ] **Update `PEPs/IMPLEMENTED/LATEST.md`**
- [ ] **Update `PEPs/INDEX.md`** — Remove the PEP row
- [ ] **Remove PEP directory** — Delete `PEPs/PEP_0017_durable_outbox_dispatcher/`
