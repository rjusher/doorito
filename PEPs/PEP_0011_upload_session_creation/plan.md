# PEP 0011: Upload Session Creation — Implementation Plan

| Field | Value |
|-------|-------|
| **PEP** | 0011 |
| **Summary** | [summary.md](summary.md) |
| **Estimated Effort** | M |

---

## Context Files

- `aikb/models.md` — IngestFile, UploadSession model definitions (from PEP 0008)
- `aikb/services.md` — Service layer conventions
- `aikb/architecture.md` — URL structure, app layout
- `boot/settings.py` — FILE_UPLOAD_MAX_SIZE and related settings

## Prerequisites

- PEP 0008 (Canonical Domain Model) implemented
- PEP 0009 (Storage Backend Abstraction) implemented
- PEP 0010 (Authentication and API Access) implemented

## Implementation Steps

- [ ] **Step 1**: Create session creation service
  - Files: Portal app `services/sessions.py`
  - Details: `create_upload_session()` function — validates input, creates IngestFile + UploadSession, computes total_parts, handles idempotency
  - Verify: Unit tests pass

- [ ] **Step 2**: Create session creation endpoint
  - Files: Portal app `views/sessions.py`, portal `urls.py`
  - Details: `POST /uploads/sessions` — parse JSON body, call service, return JSON response
  - Verify: `curl -X POST http://localhost:8000/uploads/sessions -d '...'`

- [ ] **Step 3**: Add input validation
  - Files: Portal app `services/sessions.py`
  - Details: Validate total_size_bytes against max file size, validate content_type if allowlist configured
  - Verify: Unit tests for rejection cases

- [ ] **Step 4**: Add idempotency handling
  - Files: Portal app `services/sessions.py`
  - Details: If idempotency_key matches existing session, return it instead of creating new
  - Verify: Unit test for duplicate key

- [ ] **Step 5**: Wire URL configuration
  - Files: `boot/urls.py` or portal app `urls.py`
  - Details: Add URL pattern for session creation endpoint
  - Verify: `python manage.py check`

## Testing

- [ ] Unit tests for session creation service (happy path, oversized file, idempotency)
- [ ] Integration test for endpoint (auth required, JSON response format)

## Rollback Plan

- Remove endpoint and service
- Revert URL configuration

## aikb Impact Map

- [ ] `aikb/models.md` — N/A
- [ ] `aikb/services.md` — Add session creation service documentation
- [ ] `aikb/tasks.md` — N/A
- [ ] `aikb/signals.md` — N/A
- [ ] `aikb/admin.md` — N/A
- [ ] `aikb/cli.md` — N/A
- [ ] `aikb/architecture.md` — Add upload API URL patterns
- [ ] `aikb/conventions.md` — N/A
- [ ] `aikb/dependencies.md` — N/A
- [ ] `aikb/specs-roadmap.md` — Update
- [ ] `CLAUDE.md` — Add upload API URLs to URL structure section

## Final Verification

### Acceptance Criteria

- [ ] **total_parts computation**: `ceil(100 / 10) == 10`
  - Verify: Unit test
- [ ] **Oversized rejection**: File exceeding max returns 413
  - Verify: `curl` test with oversized total_size_bytes
- [ ] **Idempotency**: Same key returns same session
  - Verify: Unit test sending same key twice

### Regression Checks

- [ ] `python manage.py check` passes
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check`
- [ ] `ruff check .` passes
  - Verify: `ruff check .`

## Completion

- [ ] **Update `PEPs/IMPLEMENTED/LATEST.md`**
- [ ] **Update `PEPs/INDEX.md`** — Remove the PEP row
- [ ] **Remove PEP directory** — Delete `PEPs/PEP_0011_upload_session_creation/`
