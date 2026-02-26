# PEP 0004: Event Outbox Infrastructure — Implementation Plan

| Field | Value |
|-------|-------|
| **PEP** | 0004 |
| **Summary** | [summary.md](summary.md) |
| **Estimated Effort** | M |

---

## Context Files

Read these files before starting implementation:

| File | Reason |
|------|--------|
| `PEPs/PEP_0004_event_outbox_infrastructure/summary.md` | Model definition, acceptance criteria, delivery worker design |
| `PEPs/PEP_0003_extend_data_models/discussions.md` | Q9 decision (outbox deferred), section 7 analysis (naming, placement, FK decoupling, delivery worker) |
| `common/models.py` | `TimeStampedModel` — base class for `OutboxEvent` |
| `common/fields.py` | `MoneyField` — pattern reference for custom fields |
| `uploads/models.py` | Upload models — first consumers of the outbox (emit `file.stored` events) |
| `boot/settings.py` | Celery configuration, `INSTALLED_APPS`, `DEFAULT_AUTO_FIELD` |
| `boot/celery.py` | Celery app setup — periodic task registration |
| `aikb/models.md` | Current model documentation — add OutboxEvent section |
| `aikb/tasks.md` | Current task documentation — add delivery worker task |
| `aikb/services.md` | Current service documentation — add emit_event service |
| `aikb/conventions.md` | Coding patterns: TextChoices, db_table, services, tasks |

## Prerequisites

- [ ] **PEP 0003 is implemented** — Upload models are in place (first consumers of the outbox)
- [ ] **`uuid_utils` is installed** — Required for UUID v7 PKs (already added by PEP 0003)

## Implementation Steps

*To be detailed during the planning phase (`make claude-pep-plan PEP=0004`). High-level outline:*

- [ ] **Step 1**: Add `OutboxEvent` model to `common/models.py`
- [ ] **Step 2**: Generate and apply migration
- [ ] **Step 3**: Add `OutboxEventAdmin` to `common/admin.py`
- [ ] **Step 4**: Create `common/services/outbox.py` with `emit_event()` function
- [ ] **Step 5**: Create delivery Celery task in `common/tasks.py`
- [ ] **Step 6**: Register periodic task in Celery beat schedule
- [ ] **Step 7**: Write tests (model, service, task)
- [ ] **Step 8**: Update aikb/ documentation
- [ ] **Step 9**: Run system checks and lint

## Testing

- [ ] Model tests: creation, unique constraint, status transitions
- [ ] Service tests: `emit_event` creates correct outbox entries
- [ ] Task tests: delivery worker processes pending events, handles failures, respects backoff

## Rollback Plan

1. Revert code changes: `git checkout -- common/ boot/ aikb/ CLAUDE.md`
2. Drop the outbox table: `DROP TABLE IF EXISTS outbox_event CASCADE;`
3. Re-apply old migration state

## aikb Impact Map

- [ ] `aikb/models.md` — Add §Common App section with `OutboxEvent` model documentation
- [ ] `aikb/services.md` — Add §Common App section with `emit_event` service documentation
- [ ] `aikb/tasks.md` — Add delivery worker task documentation
- [ ] `aikb/signals.md` — N/A
- [ ] `aikb/admin.md` — Add `OutboxEventAdmin` documentation
- [ ] `aikb/cli.md` — N/A
- [ ] `aikb/architecture.md` — Update common app in structure tree, add event outbox to background processing
- [ ] `aikb/conventions.md` — N/A (follows existing patterns)
- [ ] `aikb/dependencies.md` — N/A (uuid_utils already added by PEP 0003)
- [ ] `aikb/specs-roadmap.md` — N/A
- [ ] `CLAUDE.md` — Update common app description, add outbox to Celery section

## Final Verification

### Acceptance Criteria

*To be mapped to concrete verifications during the planning phase.*

### Regression Checks

- [ ] `python manage.py check` passes
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check`
- [ ] `ruff check .` passes
  - Verify: `ruff check .`
