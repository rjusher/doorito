# PEP 0012: Chunk Upload Endpoint — Implementation Plan

| Field | Value |
|-------|-------|
| **PEP** | 0012 |
| **Summary** | [summary.md](summary.md) |
| **Estimated Effort** | L |

---

## Context Files

- `aikb/models.md` — UploadSession, UploadPart model definitions (from PEP 0008)
- `aikb/services.md` — Service layer conventions
- Portal app `storage/` — Storage adapter interface (from PEP 0009)
- Portal app `services/sessions.py` — Session creation service (from PEP 0011)

## Prerequisites

- PEP 0008 (Canonical Domain Model) implemented
- PEP 0009 (Storage Backend Abstraction) implemented
- PEP 0010 (Authentication and API Access) implemented
- PEP 0011 (Upload Session Creation) implemented

## Implementation Steps

- [ ] **Step 1**: Create chunk upload service
  - Files: Portal app `services/chunks.py`
  - Details: `upload_chunk()` function — validates session/part, stores in temp storage, upserts UploadPart, updates counters
  - Verify: Unit tests pass

- [ ] **Step 2**: Implement idempotency detection
  - Files: Portal app `services/chunks.py`
  - Details: Compare incoming chunk hash with stored part. Same content → success; different content → Conflict
  - Verify: Unit tests for both cases

- [ ] **Step 3**: Implement atomic counter updates
  - Files: Portal app `services/chunks.py`
  - Details: Use `F()` expressions for `received_parts_count` to avoid race conditions
  - Verify: Unit test with concurrent simulated uploads

- [ ] **Step 4**: Create chunk upload endpoint
  - Files: Portal app `views/chunks.py`, portal `urls.py`
  - Details: `PUT /uploads/sessions/{session_id}/parts/{part_number}` — read binary body, call service
  - Verify: `curl -X PUT http://localhost:8000/uploads/sessions/<id>/parts/1 --data-binary @chunk`

- [ ] **Step 5**: Add validation (size, range, session status)
  - Files: Portal app `services/chunks.py`
  - Details: Validate chunk size bounds, part_number in [1, total_parts], session in INIT/IN_PROGRESS
  - Verify: Unit tests for each rejection case

## Testing

- [ ] Unit tests for chunk upload service (happy path, idempotent retry, conflict, out-of-order)
- [ ] Unit tests for validation (wrong size, out of range, wrong session status)
- [ ] Integration test for endpoint with auth

## Rollback Plan

- Remove endpoint and service
- Revert URL configuration

## aikb Impact Map

- [ ] `aikb/models.md` — N/A
- [ ] `aikb/services.md` — Add chunk upload service documentation
- [ ] `aikb/tasks.md` — N/A
- [ ] `aikb/signals.md` — N/A
- [ ] `aikb/admin.md` — N/A
- [ ] `aikb/cli.md` — N/A
- [ ] `aikb/architecture.md` — Add chunk upload URL pattern
- [ ] `aikb/conventions.md` — N/A
- [ ] `aikb/dependencies.md` — N/A
- [ ] `aikb/specs-roadmap.md` — Update
- [ ] `CLAUDE.md` — Update URL structure

## Final Verification

### Acceptance Criteria

- [ ] **Idempotent retry**: Same part, same content → success without double-count
  - Verify: Unit test
- [ ] **Conflict detection**: Same part, different content → 409
  - Verify: Unit test
- [ ] **Out-of-order**: Parts accepted in any order
  - Verify: Unit test uploading part 5 before part 1

### Regression Checks

- [ ] `python manage.py check` passes
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check`
- [ ] `ruff check .` passes
  - Verify: `ruff check .`

## Completion

- [ ] **Update `PEPs/IMPLEMENTED/LATEST.md`**
- [ ] **Update `PEPs/INDEX.md`** — Remove the PEP row
- [ ] **Remove PEP directory** — Delete `PEPs/PEP_0012_chunk_upload_endpoint/`
