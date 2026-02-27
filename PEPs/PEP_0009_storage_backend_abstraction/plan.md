# PEP 0009: Storage Backend Abstraction — Implementation Plan

| Field | Value |
|-------|-------|
| **PEP** | 0009 |
| **Summary** | [summary.md](summary.md) |
| **Estimated Effort** | M |

---

## Context Files

- `aikb/models.md` — Storage pointer fields on IngestFile (from PEP 0008)
- `aikb/services.md` — Service layer conventions
- `boot/settings.py` — Configuration patterns with django-configurations
- `uploads/services/` — Existing upload service patterns for reference

## Prerequisites

- PEP 0008 (Canonical Domain Model) must be implemented

## Implementation Steps

- [ ] **Step 1**: Define the storage adapter interface (abstract base class)
  - Files: Portal app `storage/base.py`
  - Details: ABC with methods for temp part and final object operations, all streaming-based
  - Verify: `ruff check .`

- [ ] **Step 2**: Implement LocalStorageAdapter
  - Files: Portal app `storage/local.py`
  - Details: Uses local filesystem with configurable base directories for temp and final storage
  - Verify: Unit tests pass

- [ ] **Step 3**: Implement S3StorageAdapter
  - Files: Portal app `storage/s3.py`
  - Details: Uses boto3 for S3-compatible APIs, streaming uploads/downloads, multipart for large files
  - Verify: Unit tests pass (with mocked S3)

- [ ] **Step 4**: Add storage configuration to settings
  - Files: `boot/settings.py`
  - Details: Add adapter selection setting, S3 credentials, temp/final prefix configuration
  - Verify: `python manage.py check`

- [ ] **Step 5**: Add adapter factory/registry
  - Files: Portal app `storage/__init__.py`
  - Details: `get_storage_adapter()` function that returns configured adapter instance
  - Verify: Unit tests pass

## Testing

- [ ] Unit tests for LocalStorageAdapter (write, read, delete for both temp and final)
- [ ] Unit tests for S3StorageAdapter with mocked boto3
- [ ] Integration test: stream large file through adapter without exceeding memory

## Rollback Plan

- Remove storage module from portal app
- Revert settings changes

## aikb Impact Map

- [ ] `aikb/models.md` — N/A
- [ ] `aikb/services.md` — Add storage adapter documentation
- [ ] `aikb/tasks.md` — N/A
- [ ] `aikb/signals.md` — N/A
- [ ] `aikb/admin.md` — N/A
- [ ] `aikb/cli.md` — N/A
- [ ] `aikb/architecture.md` — Add storage layer to architecture description
- [ ] `aikb/conventions.md` — N/A
- [ ] `aikb/dependencies.md` — Add boto3 if new
- [ ] `aikb/specs-roadmap.md` — Update
- [ ] `CLAUDE.md` — Add storage configuration section

## Final Verification

### Acceptance Criteria

- [ ] **Streaming**: Large file upload does not exceed memory limits
  - Verify: Memory profiling test with large file
- [ ] **Temp lifecycle**: Parts written, read, and deleted successfully
  - Verify: Unit test exercising full temp part lifecycle
- [ ] **Final storage**: Object streamed and hashed correctly
  - Verify: Unit test comparing SHA256 of input vs stored object

### Regression Checks

- [ ] `python manage.py check` passes
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check`
- [ ] `ruff check .` passes
  - Verify: `ruff check .`

## Completion

- [ ] **Update `PEPs/IMPLEMENTED/LATEST.md`**
- [ ] **Update `PEPs/INDEX.md`** — Remove the PEP row
- [ ] **Remove PEP directory** — Delete `PEPs/PEP_0009_storage_backend_abstraction/`
