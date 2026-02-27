# PEP 0014: Finalize Upload — Implementation Plan

| Field | Value |
|-------|-------|
| **PEP** | 0014 |
| **Summary** | [summary.md](summary.md) |
| **Estimated Effort** | L |

---

## Context Files

- `aikb/models.md` — IngestFile, UploadSession, UploadPart, PortalEventOutbox (from PEP 0008)
- `aikb/services.md` — Service conventions, outbox emit_event pattern
- Portal app `storage/` — Storage adapter (from PEP 0009)
- Portal app `services/sessions.py` — Session service (from PEP 0011)
- Portal app `services/chunks.py` — Chunk service (from PEP 0012)

## Prerequisites

- PEP 0008 through PEP 0012 implemented

## Implementation Steps

- [ ] **Step 1**: Create finalization service
  - Files: Portal app `services/finalize.py`
  - Details: `finalize_session()` function — lock session, verify parts, stream-assemble, compute SHA256, update IngestFile, mark COMPLETE, create outbox event
  - Verify: Unit tests pass

- [ ] **Step 2**: Implement streaming assembly with inline SHA256
  - Files: Portal app `services/finalize.py`
  - Details: Read parts in order from temp storage, pipe through hashlib.sha256, write to final storage
  - Verify: Unit test comparing hash of assembled file vs expected

- [ ] **Step 3**: Implement idempotency (duplicate finalize)
  - Files: Portal app `services/finalize.py`
  - Details: If session COMPLETE and file STORED → return success without creating new event
  - Verify: Unit test calling finalize twice

- [ ] **Step 4**: Create finalize endpoint
  - Files: Portal app `views/finalize.py`, portal `urls.py`
  - Details: `POST /uploads/sessions/{session_id}/finalize` — call service, return JSON
  - Verify: Integration test

- [ ] **Step 5**: Wire outbox dispatcher trigger
  - Files: Portal app `services/finalize.py`
  - Details: Use `transaction.on_commit` to enqueue dispatcher task after successful finalization
  - Verify: Verify task enqueued in test (mock)

## Testing

- [ ] Unit tests for finalization service (happy path, missing parts, duplicate finalize)
- [ ] Unit test for SHA256 correctness
- [ ] Unit test for transaction.on_commit behavior
- [ ] Integration test for endpoint with auth

## Rollback Plan

- Remove endpoint and service
- Revert URL configuration

## aikb Impact Map

- [ ] `aikb/models.md` — N/A
- [ ] `aikb/services.md` — Add finalization service documentation
- [ ] `aikb/tasks.md` — Document outbox dispatcher trigger
- [ ] `aikb/signals.md` — N/A
- [ ] `aikb/admin.md` — N/A
- [ ] `aikb/cli.md` — N/A
- [ ] `aikb/architecture.md` — Add finalize URL pattern
- [ ] `aikb/conventions.md` — N/A
- [ ] `aikb/dependencies.md` — N/A
- [ ] `aikb/specs-roadmap.md` — Update
- [ ] `CLAUDE.md` — Update URL structure

## Final Verification

### Acceptance Criteria

- [ ] **Missing part rejection**: Upload 4 of 5 parts, finalize → 400 error
  - Verify: Integration test
- [ ] **Idempotent finalize**: Finalize twice → same result, one outbox event
  - Verify: Unit test counting outbox entries
- [ ] **SHA256 correctness**: Hash matches known test file
  - Verify: Unit test with deterministic input

### Regression Checks

- [ ] `python manage.py check` passes
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check`
- [ ] `ruff check .` passes
  - Verify: `ruff check .`

## Completion

- [ ] **Update `PEPs/IMPLEMENTED/LATEST.md`**
- [ ] **Update `PEPs/INDEX.md`** — Remove the PEP row
- [ ] **Remove PEP directory** — Delete `PEPs/PEP_0014_finalize_upload/`
