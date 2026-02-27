# PEP 0008: Canonical Domain Model for OSS Ingest Portal — Implementation Plan

| Field | Value |
|-------|-------|
| **PEP** | 0008 |
| **Summary** | [summary.md](summary.md) |
| **Estimated Effort** | L |

---

## Context Files

- `aikb/models.md` — Existing model conventions (TimeStampedModel, uuid7, MoneyField)
- `aikb/conventions.md` — Naming conventions, import order, coding patterns
- `aikb/architecture.md` — App structure, URL patterns
- `uploads/models.py` — Existing upload models for reference
- `common/models.py` — TimeStampedModel, OutboxEvent base patterns

## Prerequisites

- None — this is the foundational PEP for the ingest portal

## Implementation Steps

- [ ] **Step 1**: Create the portal app structure
  - Files: New Django app directory for the ingest portal
  - Details: Create app with models, services, admin, tasks modules
  - Verify: `python manage.py check`

- [ ] **Step 2**: Define IngestFile model
  - Files: Portal app `models.py`
  - Details: Status choices (UPLOADING, STORED, FAILED), sha256, size_bytes, storage_backend, storage_bucket, storage_key, original_filename, content_type, uploaded_by FK, optional batch FK
  - Verify: `python manage.py makemigrations --check`

- [ ] **Step 3**: Define UploadSession model
  - Files: Portal app `models.py`
  - Details: Status choices (INIT, IN_PROGRESS, COMPLETE, FAILED, ABORTED), OneToOne to IngestFile, chunk_size_bytes, total_parts, received_parts_count, idempotency_key
  - Verify: `python manage.py makemigrations --check`

- [ ] **Step 4**: Define UploadPart model
  - Files: Portal app `models.py`
  - Details: FK to UploadSession, part_number, status (PENDING, RECEIVED, FAILED), temp_key, size_bytes, unique_together on (session, part_number)
  - Verify: `python manage.py makemigrations --check`

- [ ] **Step 5**: Define UploadBatch model
  - Files: Portal app `models.py`
  - Details: Status, total_files, stored_count, failed_count, created_by FK
  - Verify: `python manage.py makemigrations --check`

- [ ] **Step 6**: Define PortalEventOutbox model
  - Files: Portal app `models.py`
  - Details: event_type, event_id, idempotency_key, payload (JSONField), status (PENDING, SENDING, DELIVERED, FAILED), next_attempt_at, attempt_count, FK to IngestFile, unique constraint on (event_type, idempotency_key)
  - Verify: `python manage.py makemigrations --check`

- [ ] **Step 7**: Generate and apply migrations
  - Verify: `python manage.py migrate`

- [ ] **Step 8**: Register admin classes
  - Files: Portal app `admin.py`
  - Verify: `python manage.py check`

## Testing

- [ ] Unit tests for model creation and constraints
- [ ] Test unique constraint on (session, part_number)
- [ ] Test that IngestFile status transitions are valid

## Rollback Plan

- Reverse migrations: `python manage.py migrate portal zero`
- Remove app from INSTALLED_APPS

## aikb Impact Map

- [ ] `aikb/models.md` — Add IngestFile, UploadSession, UploadPart, UploadBatch, PortalEventOutbox documentation
- [ ] `aikb/services.md` — N/A (services defined in later PEPs)
- [ ] `aikb/tasks.md` — N/A
- [ ] `aikb/signals.md` — N/A
- [ ] `aikb/admin.md` — Add portal admin classes
- [ ] `aikb/cli.md` — N/A
- [ ] `aikb/architecture.md` — Add portal app to app structure table
- [ ] `aikb/conventions.md` — N/A
- [ ] `aikb/dependencies.md` — N/A
- [ ] `aikb/specs-roadmap.md` — Update with portal domain model status
- [ ] `CLAUDE.md` — Add portal app to architecture section

## Final Verification

### Acceptance Criteria

- [ ] **Unique constraint**: `(session, part_number)` enforced at DB level
  - Verify: Attempt duplicate insert, confirm IntegrityError
- [ ] **STORED invariant**: File cannot be STORED without sha256, size_bytes, storage pointer
  - Verify: Service layer test
- [ ] **Outbox guard**: PortalEventOutbox rejects creation for non-STORED files
  - Verify: Service layer test

### Integration Checks

- [ ] **Full model creation workflow**: Create batch → create file → create session → create parts → mark stored
  - Expected: All models created with correct relationships

### Regression Checks

- [ ] `python manage.py check` passes
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check`
- [ ] `ruff check .` passes
  - Verify: `ruff check .`

## Completion

- [ ] **Update `PEPs/IMPLEMENTED/LATEST.md`** — Add entry with PEP number, title, commit hash(es), and summary
- [ ] **Update `PEPs/INDEX.md`** — Remove the PEP row
- [ ] **Remove PEP directory** — Delete `PEPs/PEP_0008_canonical_domain_model/`
