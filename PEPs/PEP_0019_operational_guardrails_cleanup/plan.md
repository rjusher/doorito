# PEP 0019: Operational Guardrails and Cleanup — Implementation Plan

| Field | Value |
|-------|-------|
| **PEP** | 0019 |
| **Summary** | [summary.md](summary.md) |
| **Estimated Effort** | M |

---

## Context Files

- `aikb/tasks.md` — Celery task conventions, periodic task configuration
- `aikb/architecture.md` — URL structure, healthz endpoint
- `boot/settings.py` — Existing configuration patterns, celery-beat schedule
- `boot/urls.py` — Existing healthz endpoint for reference
- Portal app `storage/` — Storage adapter (from PEP 0009)
- Portal app models — Session, Part, Outbox models (from PEP 0008)

## Prerequisites

- PEP 0008 (Canonical Domain Model) implemented
- PEP 0009 (Storage Backend) implemented
- PEP 0017 (Outbox Dispatcher) implemented

## Implementation Steps

- [ ] **Step 1**: Add portal configuration settings
  - Files: `boot/settings.py`
  - Details: All configurable settings with defaults, using `values.*` wrappers from django-configurations
  - Verify: `python manage.py check`

- [ ] **Step 2**: Create cleanup service
  - Files: Portal app `services/cleanup.py`
  - Details: `cleanup_stale_sessions()`, `cleanup_orphan_temp_parts()`, `prune_old_failed_sessions()`
  - Verify: Unit tests pass

- [ ] **Step 3**: Create cleanup Celery task
  - Files: Portal app `tasks.py`
  - Details: `portal_cleanup_task` — periodic task calling cleanup service functions
  - Verify: Task registered in Celery

- [ ] **Step 4**: Add cleanup task to celery-beat schedule
  - Files: `boot/settings.py`
  - Details: Add periodic schedule entry for cleanup task
  - Verify: Schedule entry visible in beat

- [ ] **Step 5**: Create health and readiness endpoints
  - Files: Portal app `views/health.py` or `boot/urls.py`
  - Details: `/health` (liveness), `/ready` (DB + storage check)
  - Verify: `curl http://localhost:8000/health` and `curl http://localhost:8000/ready`

- [ ] **Step 6**: Add structured logging
  - Files: Portal app services (sessions, chunks, finalize, dispatcher)
  - Details: Add `structlog` or standard logging calls at major transition points
  - Verify: Log output visible during upload flow

## Testing

- [ ] Unit tests for cleanup service (stale sessions, orphan parts)
- [ ] Unit tests for health/readiness endpoints (healthy and unhealthy scenarios)
- [ ] Integration test for full cleanup cycle

## Rollback Plan

- Remove cleanup task from beat schedule
- Remove health/readiness endpoints
- Revert settings additions

## aikb Impact Map

- [ ] `aikb/models.md` — N/A
- [ ] `aikb/services.md` — Add cleanup service documentation
- [ ] `aikb/tasks.md` — Add portal_cleanup_task documentation
- [ ] `aikb/signals.md` — N/A
- [ ] `aikb/admin.md` — N/A
- [ ] `aikb/cli.md` — N/A
- [ ] `aikb/architecture.md` — Add health/ready endpoints, document portal settings
- [ ] `aikb/conventions.md` — Add structured logging conventions
- [ ] `aikb/dependencies.md` — N/A
- [ ] `aikb/specs-roadmap.md` — Update
- [ ] `CLAUDE.md` — Add portal settings documentation, health endpoints

## Final Verification

### Acceptance Criteria

- [ ] **Stale cleanup**: Create session, wait past TTL, run cleanup → session FAILED
  - Verify: Unit test with mocked time
- [ ] **No storage leak**: Complete session, run cleanup → temp parts deleted
  - Verify: Unit test verifying storage adapter delete calls
- [ ] **Readiness failure**: Stop DB → `/ready` returns 503
  - Verify: Integration test

### Regression Checks

- [ ] `python manage.py check` passes
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check`
- [ ] `ruff check .` passes
  - Verify: `ruff check .`

## Completion

- [ ] **Update `PEPs/IMPLEMENTED/LATEST.md`**
- [ ] **Update `PEPs/INDEX.md`** — Remove the PEP row
- [ ] **Remove PEP directory** — Delete `PEPs/PEP_0019_operational_guardrails_cleanup/`
