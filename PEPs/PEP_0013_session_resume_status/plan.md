# PEP 0013: Session Resume and Status Endpoint — Implementation Plan

| Field | Value |
|-------|-------|
| **PEP** | 0013 |
| **Summary** | [summary.md](summary.md) |
| **Estimated Effort** | S |

---

## Context Files

- `aikb/models.md` — UploadSession, UploadPart model definitions (from PEP 0008)
- `aikb/services.md` — Service layer conventions
- Portal app `views/` — Existing endpoint patterns (from PEP 0011)

## Prerequisites

- PEP 0008 (Canonical Domain Model) implemented
- PEP 0010 (Authentication and API Access) implemented
- PEP 0011 (Upload Session Creation) implemented

## Implementation Steps

- [ ] **Step 1**: Create session status service
  - Files: Portal app `services/sessions.py`
  - Details: `get_session_status()` function — query session and received parts, format compact ranges
  - Verify: Unit tests pass

- [ ] **Step 2**: Implement compact range formatter
  - Files: Portal app `utils.py` or `services/sessions.py`
  - Details: Convert list of part numbers to compact range representation (e.g., [1,2,3,5,6] → "1-3,5-6")
  - Verify: Unit tests for range formatting

- [ ] **Step 3**: Create status endpoint
  - Files: Portal app `views/sessions.py`, portal `urls.py`
  - Details: `GET /uploads/sessions/{session_id}` — call service, return JSON response
  - Verify: `curl http://localhost:8000/uploads/sessions/<id>`

## Testing

- [ ] Unit tests for range formatter (empty, contiguous, gaps, single parts)
- [ ] Unit tests for session status service
- [ ] Integration test for endpoint with auth

## Rollback Plan

- Remove endpoint
- Revert URL configuration

## aikb Impact Map

- [ ] `aikb/models.md` — N/A
- [ ] `aikb/services.md` — Add session status service documentation
- [ ] `aikb/tasks.md` — N/A
- [ ] `aikb/signals.md` — N/A
- [ ] `aikb/admin.md` — N/A
- [ ] `aikb/cli.md` — N/A
- [ ] `aikb/architecture.md` — Add status URL pattern
- [ ] `aikb/conventions.md` — N/A
- [ ] `aikb/dependencies.md` — N/A
- [ ] `aikb/specs-roadmap.md` — Update
- [ ] `CLAUDE.md` — Update URL structure

## Final Verification

### Acceptance Criteria

- [ ] **Accurate parts**: Received parts match DB state after partial upload
  - Verify: Upload 3 of 5 parts, query status, verify received_parts
- [ ] **Compact ranges**: 1000-part session returns ranges, not individual numbers
  - Verify: Unit test with large part list

### Regression Checks

- [ ] `python manage.py check` passes
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check`
- [ ] `ruff check .` passes
  - Verify: `ruff check .`

## Completion

- [ ] **Update `PEPs/IMPLEMENTED/LATEST.md`**
- [ ] **Update `PEPs/INDEX.md`** — Remove the PEP row
- [ ] **Remove PEP directory** — Delete `PEPs/PEP_0013_session_resume_status/`
