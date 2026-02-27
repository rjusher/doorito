# PEP 0015: Batch Upload Support — Implementation Plan

| Field | Value |
|-------|-------|
| **PEP** | 0015 |
| **Summary** | [summary.md](summary.md) |
| **Estimated Effort** | M |

---

## Context Files

- `aikb/models.md` — UploadBatch, IngestFile model definitions (from PEP 0008)
- `aikb/services.md` — Service layer conventions
- Portal app `services/finalize.py` — Finalization service (from PEP 0014) for counter integration

## Prerequisites

- PEP 0008 (Canonical Domain Model) implemented
- PEP 0010 (Authentication and API Access) implemented

## Implementation Steps

- [ ] **Step 1**: Create batch service
  - Files: Portal app `services/batches.py`
  - Details: `create_batch()`, `get_batch()`, `list_batch_files()`, `update_batch_counters()`
  - Verify: Unit tests pass

- [ ] **Step 2**: Implement atomic counter updates
  - Files: Portal app `services/batches.py`
  - Details: `update_batch_counters()` using F() expressions, called from finalization service when file status changes
  - Verify: Unit test for concurrent counter updates

- [ ] **Step 3**: Create batch endpoints
  - Files: Portal app `views/batches.py`, portal `urls.py`
  - Details: `POST /batches`, `GET /batches/{id}`, `GET /batches/{id}/files`
  - Verify: `curl` tests for all three endpoints

- [ ] **Step 4**: Integrate with finalization service
  - Files: Portal app `services/finalize.py`
  - Details: After file is STORED, call `update_batch_counters()` if file has a batch
  - Verify: Integration test: create batch → upload file → finalize → verify counter

## Testing

- [ ] Unit tests for batch service (create, get, list files)
- [ ] Concurrency test for counter updates
- [ ] Integration test for full flow (batch → session → upload → finalize → batch counters)

## Rollback Plan

- Remove batch endpoints and service
- Remove counter update integration from finalization service
- Revert URL configuration

## aikb Impact Map

- [ ] `aikb/models.md` — N/A (models from PEP 0008)
- [ ] `aikb/services.md` — Add batch service documentation
- [ ] `aikb/tasks.md` — N/A
- [ ] `aikb/signals.md` — N/A
- [ ] `aikb/admin.md` — N/A
- [ ] `aikb/cli.md` — N/A
- [ ] `aikb/architecture.md` — Add batch URL patterns
- [ ] `aikb/conventions.md` — N/A
- [ ] `aikb/dependencies.md` — N/A
- [ ] `aikb/specs-roadmap.md` — Update
- [ ] `CLAUDE.md` — Update URL structure

## Final Verification

### Acceptance Criteria

- [ ] **Counter accuracy**: Finalize 3 of 5 files in a batch → stored_count = 3
  - Verify: Integration test
- [ ] **Concurrent safety**: Finalize 2 files simultaneously → counters correct
  - Verify: Concurrent test with threading

### Regression Checks

- [ ] `python manage.py check` passes
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check`
- [ ] `ruff check .` passes
  - Verify: `ruff check .`

## Completion

- [ ] **Update `PEPs/IMPLEMENTED/LATEST.md`**
- [ ] **Update `PEPs/INDEX.md`** — Remove the PEP row
- [ ] **Remove PEP directory** — Delete `PEPs/PEP_0015_batch_upload_support/`
