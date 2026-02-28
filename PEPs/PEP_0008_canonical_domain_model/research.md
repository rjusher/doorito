# PEP 0008: Canonical Domain Model for OSS Ingest Portal — Research

| Field | Value |
|-------|-------|
| **PEP** | 0008 |
| **Summary** | [summary.md](summary.md) |
| **Plan** | [plan.md](plan.md) |

---

## Current State Analysis

### Existing Upload Models

The `uploads` app (`uploads/models.py`) contains 4 models that form a complete chunked upload infrastructure:

- **UploadBatch** — Groups files into logical batches. Status lifecycle: `init → in_progress → complete / partial / failed`. FK to User (`created_by`, SET_NULL). Has `idempotency_key` (CharField, db_index).
- **UploadFile** — Canonical file record. Status lifecycle: `uploading → stored → processed / deleted` or `uploading → failed`. Uses Django `FileField(upload_to="uploads/%Y/%m/")`. Has `sha256` (db_index), `size_bytes`, `metadata` (JSONField), `error_message` (TextField). FK to UploadBatch (SET_NULL) and User (SET_NULL).
- **UploadSession** — OneToOne with UploadFile. Tracks chunked upload progress (`completed_parts`, `bytes_received`, `total_parts`, `total_size_bytes`). Has `upload_token` and `idempotency_key`. Status lifecycle: `init → in_progress → complete / failed / aborted`.
- **UploadPart** — FK to UploadSession (CASCADE). Tracks individual chunks with `part_number`, `offset_bytes`, `size_bytes`, `sha256`, `temp_storage_key`. UniqueConstraint on `(session, part_number)`. Status lifecycle: `pending → received / failed`.

All models inherit from `TimeStampedModel`, use UUID v7 PKs via `common.utils.uuid7`, and have explicit `db_table` names (`upload_batch`, `upload_file`, `upload_session`, `upload_part`).

### Existing Service Layer

Two service modules exist:

- **`uploads/services/uploads.py`** (9 functions) — `validate_file`, `compute_sha256`, `create_upload_file`, `mark_file_processed`, `mark_file_failed`, `mark_file_deleted`, `create_batch`, `finalize_batch`, `notify_expiring_files`. The `create_upload_file` function wraps file creation + `emit_event("file.stored")` in `transaction.atomic()` using `common.services.outbox.emit_event`. It emits to the **common** `OutboxEvent` table.
- **`uploads/services/sessions.py`** (3 functions) — `create_upload_session`, `record_upload_part`, `complete_upload_session`. Uses `F()` expressions for atomic counter updates on session progress.

### Existing Task Layer

`uploads/tasks.py` contains 2 tasks:
- `cleanup_expired_upload_files_task` — Deletes files older than `FILE_UPLOAD_TTL_HOURS`. References `UploadFile` model and calls `upload.file.delete(save=False)` — **tightly coupled to Django's FileField**.
- `notify_expiring_files_task` — Delegates to `notify_expiring_files()` service.

Both are registered in `CELERY_BEAT_SCHEDULE` in `boot/settings.py` with task names prefixed `uploads.tasks.`.

### Existing Admin Layer

`uploads/admin.py` registers 4 admin classes: `UploadBatchAdmin`, `UploadFileAdmin`, `UploadSessionAdmin`, `UploadPartAdmin`. All use `list_select_related` and follow established patterns.

### Frontend Integration

The frontend `upload_view` (`frontend/views/upload.py`) imports from `uploads.models` and `uploads.services.uploads`. The upload templates (`frontend/templates/frontend/upload/`) reference `upload.status`, `upload.original_filename`, `upload.size_bytes`, `upload.error_message` — all context variables passed from the view, not direct model references.

### Outbox Integration

The existing uploads app emits events to `common.OutboxEvent` via `common.services.outbox.emit_event()`. Two event types: `file.stored` and `file.expiring`. The `aggregate_type` is `"UploadFile"`. This will change when the model is renamed to `IngestFile`.

### Structural Overlap with Portal Models

The existing models are ~80% aligned with the proposed portal domain model:

| Portal Model | Existing Model | Structural Overlap | Key Differences |
|-------------|---------------|-------------------|-----------------|
| IngestFile | UploadFile | ~75% | Replace `FileField` with explicit storage fields; simplify statuses (remove PROCESSED, DELETED) |
| UploadSession | UploadSession | ~95% | OneToOne FK target changes from UploadFile to IngestFile |
| UploadPart | UploadPart | ~100% | No structural changes |
| UploadBatch | UploadBatch | ~95% | Related name changes |
| PortalEventOutbox | (none) | 0% | New model, patterned after `common.OutboxEvent` |

## Key Files & Functions

### Source Files to Modify

| File | Changes Required |
|------|-----------------|
| `uploads/` → `portal/` (directory rename) | Physical directory rename |
| `portal/apps.py` (was `uploads/apps.py`) | `name="portal"`, `verbose_name="Portal"` |
| `portal/models.py` (was `uploads/models.py`) | Rename UploadFile→IngestFile, replace FileField with storage fields, simplify statuses, add PortalEventOutbox, update related_names |
| `portal/admin.py` (was `uploads/admin.py`) | Update imports, rename IngestFileAdmin, add PortalEventOutboxAdmin |
| `portal/tasks.py` (was `uploads/tasks.py`) | Update task names (`portal.tasks.*`), update model imports |
| `portal/services/uploads.py` | Update model imports, adapt for explicit storage fields (no more `upload.file.url`, `upload.file.delete()`) |
| `portal/services/sessions.py` | Update model imports (UploadFile→IngestFile in references) |
| `portal/tests/*.py` (4 files) | Update all `uploads.*` imports to `portal.*` |
| `boot/settings.py:40` | Change `"uploads"` to `"portal"` in INSTALLED_APPS |
| `boot/settings.py:155,172` | Update task paths from `uploads.tasks.*` to `portal.tasks.*` |
| `frontend/views/upload.py:8-9` | Update imports from `uploads.models` / `uploads.services.uploads` to `portal.*` |
| `frontend/tests/test_views_upload.py:6` | Update imports from `uploads.models` to `portal.models` |

### Source Files as Reference/Pattern

| File | Pattern Reference |
|------|------------------|
| `common/models.py:19-67` | `OutboxEvent` — structural template for `PortalEventOutbox` (Status choices, field names, indexes, constraints) |
| `common/models.py:9-16` | `TimeStampedModel` — base class for all models |
| `common/utils.py` | `uuid7()` — PK default for all models |
| `common/admin.py` | `OutboxEventAdmin` — pattern for `PortalEventOutboxAdmin` |

### Configuration Files Affected

| File | Impact |
|------|--------|
| `boot/settings.py` | INSTALLED_APPS, CELERY_BEAT_SCHEDULE task paths |
| `uploads/migrations/0001_initial.py` | Must remain (historical migration), but new migrations will target `portal` app label |

### Migration Files

Only one migration exists: `uploads/migrations/0001_initial.py`. This creates all four tables (`upload_batch`, `upload_file`, `upload_session`, `upload_part`) with indexes and constraints. Internal FK references use `to="uploads.uploadbatch"`, `to="uploads.uploadfile"`, `to="uploads.uploadsession"` — these are app_label-qualified references that will need updating in the rename migration.

## Technical Constraints

### Database Schema Constraints

1. **Existing `db_table` values**: The four tables use explicit `db_table` names: `upload_batch`, `upload_file`, `upload_session`, `upload_part`. The rename migration must either:
   - Rename tables to `portal_*` via `AlterModelTable` (the plan's stated approach), or
   - Keep existing table names and only change `app_label` in `django_content_type`

   **Recommendation**: Rename tables to `portal_*` for consistency with the new app name. This avoids confusion where a `portal` app has `upload_*` tables.

2. **`django_content_type` table**: Django stores `app_label` + `model` in `content_type`. The rename must update rows from `(app_label="uploads", model="uploadbatch")` to `(app_label="portal", model="uploadbatch")` (or to new model names if renamed). This is critical because generic relations, admin log entries, and permissions reference content types.

3. **`django_migrations` table**: The `uploads` app's migration history is stored with `app="uploads"`. The rename migration must be added to the **portal** app's migrations directory, and the historical migration records for `uploads` must be updated to `portal` in `django_migrations`. This is typically handled by a `migrations.RunSQL` or `migrations.RunPython` step.

4. **Existing FK constraints**: The `upload_file` table has FK constraints referencing `upload_batch`. The `upload_session` table has a FK (OneToOne) referencing `upload_file`. The `upload_part` table has a FK referencing `upload_session`. Table renames must preserve these constraints.

5. **UniqueConstraint name**: `unique_session_part_number` on UploadPart — this constraint name is baked into the database and the migration history. Renaming it is optional but would require an `AlterModelOptions` or `RemoveConstraint` + `AddConstraint` migration step.

6. **Index names**: Auto-generated index names like `upload_file_uploade_4deeb7_idx` and `upload_file_status_d3e036_idx` will persist through the rename unless explicitly altered.

### Dependency Restrictions

- No new dependencies required for the model changes themselves.
- The `PortalEventOutbox` model uses the same field types as `OutboxEvent` — no new imports needed.
- The explicit storage fields (`storage_backend`, `storage_bucket`, `storage_key`) are plain CharField/TextField — no dependency on `django-storages` at the model level.

### Performance Considerations

- The `PortalEventOutbox` partial index (`next_attempt_at WHERE status='pending'`) must use the same pattern as `OutboxEvent.idx_outbox_pending_next` for efficient delivery polling.
- The IngestFile composite index `["uploaded_by", "-created_at"]` supports the user's file list query pattern efficiently.
- The `sha256` db_index supports O(log n) dedup lookups.

### Service Layer Constraints

- **FileField removal impact**: The existing `cleanup_expired_upload_files_task` calls `upload.file.delete(save=False)` — this depends on Django's `FileField` which is being replaced with explicit storage fields. The cleanup task will need to be updated to use the new storage abstraction (PEP 0009) or a manual deletion approach.
- **`create_upload_file` service**: Currently uses `file=file` to populate Django's `FileField`. With explicit storage fields, the service must manually populate `storage_backend`, `storage_bucket`, `storage_key` instead. The `upload.file.url` references in event payloads will also break.
- **`notify_expiring_files` service**: References `upload.file.url` in the event payload — this will break with explicit storage fields.

## Pattern Analysis

### Patterns to Follow

1. **Model structure** (`uploads/models.py`): UUID v7 PK, TextChoices for status, explicit `db_table`, `Meta.ordering`, `__str__` format. The PortalEventOutbox should follow `OutboxEvent`'s pattern exactly for consistency.

2. **OutboxEvent field structure** (`common/models.py:19-67`): The `PortalEventOutbox` should mirror `OutboxEvent`'s fields but use `attempt_count` (the plan's name) vs `attempts` (OutboxEvent's name). **Observation**: The plan Step 6 uses `attempt_count` while `OutboxEvent` uses `attempts`. This naming inconsistency should be resolved — either match `OutboxEvent` (use `attempts`) or use `attempt_count` consistently. The discussions.md doesn't address this.

3. **Admin patterns** (`uploads/admin.py`, `common/admin.py`): `list_select_related`, `list_filter` on status/created_at, `readonly_fields` for computed/auto fields, `date_hierarchy = "created_at"`.

4. **Service layer** (`uploads/services/uploads.py`): Plain functions, `transaction.atomic()` for multi-model operations, logging with structured fields, `emit_event()` for outbox integration.

5. **Task patterns** (`uploads/tasks.py`): `@shared_task(name="...", bind=True, max_retries=2, default_retry_delay=60)`, lazy imports, structured return dicts.

### Patterns to Avoid

1. **Don't use multi-table inheritance** for PortalEventOutbox — it was explicitly rejected in discussions.md for performance reasons. Use a standalone model.

2. **Don't add denormalized counter fields** to UploadBatch — the discussions.md resolved this as computed via annotation.

3. **Don't use Django's `FileField`** for IngestFile — the explicit storage fields approach was chosen for fine-grained storage control.

### Conventions from aikb/conventions.md

- **Status fields**: Use CharField with TextChoices, not IntegerChoices (confirmed in existing models).
- **Model naming**: PascalCase singular (`IngestFile`, not `IngestFiles`).
- **One `models.py` per app**: Not a `models/` package.
- **Services in `{app}/services/`**: Business logic in services, not models or views.
- **Import order**: Standard library → Django → Third-party → Local app.

## External Research

### Django App Renaming

Django app renaming is a well-known complex operation. The standard approach involves:

1. **Physical rename**: Rename directory, update `apps.py`, update `INSTALLED_APPS`.
2. **Migration to rename tables**: Use `migrations.AlterModelTable` or raw SQL to rename database tables.
3. **Update `django_content_type`**: Run SQL or `RunPython` to update `app_label` column.
4. **Update `django_migrations`**: Run SQL to update the `app` column from old to new app name.
5. **Update `auth_permission`**: Permissions are derived from content types, so they update automatically when content types are fixed.

**Key risk**: If `django_content_type` rows are not updated, Django admin, generic relations, and permission lookups will break.

**Alternative approach**: Some projects keep the old migration files in the new directory and add a `RunSQL` migration that updates `django_content_type` and `django_migrations` in one step. This is simpler than trying to create a migration in one app that references another.

### Django Migration for Model Renaming

Django's `RenameModel` operation handles model renames within the same app. It updates `db_table` (if not explicitly set), content type entries, and FK references. However, since `db_table` is explicitly set on all models, `RenameModel` alone won't change the physical table name — an `AlterModelTable` must follow.

For `UploadFile → IngestFile`:
- `migrations.RenameModel(old_name="UploadFile", new_name="IngestFile")` — updates Django internals
- The existing `db_table = "upload_file"` can optionally be changed to `portal_ingest_file` via Meta class update + `AlterModelTable` in the migration

### Explicit Storage Fields vs FileField

The decision to replace Django's `FileField` with explicit `storage_backend`, `storage_bucket`, `storage_key` fields is a deliberate decoupling from Django's storage API. This is common in systems that need:
- Multi-backend storage (e.g., local + S3 + R2)
- Backend-agnostic file references
- Decoupled upload/storage lifecycle (file record created before file is physically stored)

The trade-off is that Django's built-in `FieldFile` methods (`url`, `delete()`, `open()`) are no longer available — all storage operations must go through a custom service layer (PEP 0009).

## Risk & Edge Cases

### High Risk: App Rename Migration Complexity

The `uploads → portal` rename is the highest-risk step. Key failure modes:
1. **`django_content_type` not updated**: Admin log entries, permissions, and any code using `ContentType.objects.get_for_model()` will break.
2. **`django_migrations` not updated**: Django will think the old `uploads` migrations haven't been run, and try to re-apply them (crashing on existing tables).
3. **FK references in migration files**: The existing `0001_initial.py` uses `to="uploads.uploadbatch"` etc. After the rename, these need to resolve to `portal.uploadbatch`. If the migration app label isn't updated in `django_migrations`, Django's migration framework may get confused.
4. **Celery beat schedule**: Task names change from `uploads.tasks.*` to `portal.tasks.*`. Any tasks enqueued before the rename will fail with `KeyError` on the worker. This is transient (next beat interval picks up new names).

**Mitigation**: The rename migration should be a single, carefully ordered migration that:
1. Renames database tables
2. Updates `django_content_type` rows
3. Updates `django_migrations` rows
4. All within a single transaction (PostgreSQL DDL is transactional)

### Medium Risk: FileField Removal Breaks Existing Services

Replacing `FileField` with explicit storage fields breaks:
- `create_upload_file()` — currently saves file via `file=file` parameter to ORM
- `mark_file_deleted()` — calls `upload_file.file.delete(save=False)`
- `cleanup_expired_upload_files_task()` — calls `upload.file.delete(save=False)`
- `notify_expiring_files()` — references `upload.file.url` in event payload
- `create_upload_file()` — references `upload.file.url` in event payload
- `frontend/views/upload.py` — the `create_upload_file` service returns an object the view accesses `.status`, `.original_filename`, `.size_bytes`, `.error_message` — these survive, but the file-upload path changes

**Question**: Should PEP 0008 remove the `FileField` immediately, or should it keep it alongside the new storage fields as a transitional step? The plan says to replace it, but PEP 0009 (Storage Backend Abstraction) is the PEP that defines the actual storage abstraction layer. Removing `FileField` before PEP 0009 creates a gap where files cannot be stored at all.

**Observation**: This is a potential ordering issue. If PEP 0008 removes `FileField` and adds explicit storage fields, but PEP 0009 hasn't implemented the storage service that populates those fields, then the existing upload functionality is broken between PEP 0008 and PEP 0009.

### Medium Risk: UploadFile Status Simplification

The plan simplifies IngestFile statuses from 5 → 3 (removing PROCESSED and DELETED):
- Current: `UPLOADING, STORED, PROCESSED, FAILED, DELETED`
- Proposed: `UPLOADING, STORED, FAILED`

This removes `mark_file_processed()` and `mark_file_deleted()` service functions. The `finalize_batch()` service references `UploadFile.Status.PROCESSED` in its success check. The cleanup task currently relies on deleting records regardless of status.

**Impact**: The frontend upload view and tests check `UploadFile.Status.STORED` and `UploadFile.Status.FAILED` — these survive. But `finalize_batch()` checks for both `STORED` and `PROCESSED` statuses, so it needs adjustment.

### Low Risk: Related Name Changes

Changing `related_name="upload_batches"` to `"portal_batches"` on `UploadBatch.created_by` affects any code using `user.upload_batches.all()`. Searching the codebase shows no usage of this related name outside of the uploads app itself (and its tests).

### Edge Cases

1. **Empty `storage_backend`/`storage_bucket`/`storage_key` on IngestFile with status=UPLOADING**: This is expected — the file is in progress. The STORED invariant (sha256 + size_bytes + storage pointer required) only applies when status=STORED.

2. **PortalEventOutbox with aggregate_type referencing a deleted IngestFile**: Since there's no FK, the outbox event persists even if the file is deleted. This is by design (outbox events should be delivered regardless of aggregate lifecycle).

3. **Concurrent session completions**: The `complete_upload_session` service uses `@transaction.atomic` and refreshes from DB, but the IngestFile status transition (`UPLOADING → STORED`) uses `filter(status=UPLOADING).update()` which is atomic at DB level.

4. **Migration ordering with `django_celery_beat`**: If beat is running during deployment, it may try to dispatch tasks with old names. The task registration (via `@shared_task(name=...)`) changes atomically with the code deployment, but any tasks already in the Celery queue with old names will fail.

## Recommendations

### 1. Split the FileField Removal into Two Phases

**Phase 1 (PEP 0008)**: Add the explicit storage fields (`storage_backend`, `storage_bucket`, `storage_key`) as new fields alongside the existing `FileField`. Mark them as `blank=True` so existing code continues to work. Remove `PROCESSED` and `DELETED` statuses. Add `PortalEventOutbox`.

**Phase 2 (PEP 0009)**: Implement the storage abstraction service, migrate existing code from `FileField` to the new storage fields, and then remove `FileField` in a subsequent migration.

**Rationale**: This avoids the gap where upload functionality is broken between PEP 0008 and PEP 0009. The explicit storage fields exist on the model but are not used until the storage service is ready.

### 2. Approach App Rename Carefully

Use a single migration that:
1. Renames tables from `upload_*` to `portal_*` (via `migrations.AlterModelTable` or `RunSQL`)
2. Updates `django_content_type` rows (via `RunPython`)
3. Updates `django_migrations` rows (via `RunSQL`)

Verify by running `python manage.py showmigrations` after the rename to confirm Django sees the migration history correctly.

### 3. Keep Service Layer Functional Throughout

Since the existing services (`create_upload_file`, `finalize_batch`, etc.) are used by the frontend upload view, they must remain functional after PEP 0008. The import paths change (`uploads.services.uploads` → `portal.services.uploads`), but the service functions should continue to work.

### 4. Use `attempts` Not `attempt_count` for PortalEventOutbox

The plan's Step 6 uses `attempt_count` while `OutboxEvent` uses `attempts`. For consistency with the existing `common.OutboxEvent` model (which is the template), use `attempts` as the field name on `PortalEventOutbox`.

### 5. Update All Import References in a Single Step

The app rename affects 12+ files across the codebase. Update all `uploads.*` imports to `portal.*` in a single commit to avoid partial rename states. Use grep to verify no orphaned references remain.

### 6. Verify with Comprehensive Regression

After the rename + model changes:
- `python manage.py check` — Django system check
- `python manage.py showmigrations` — Verify migration history
- `python manage.py migrate --run-syncdb` — Verify no sync issues
- `ruff check .` — Code quality
- `pytest` — All existing tests pass (with updated imports)

### 7. Things to Verify During Implementation

- [ ] `django_content_type` rows for uploads models are updated to `portal`
- [ ] `django_migrations` rows for `uploads` app are updated to `portal`
- [ ] All FK references in migration files resolve correctly
- [ ] `CELERY_BEAT_SCHEDULE` task paths are updated
- [ ] Frontend upload view works end-to-end after rename
- [ ] Outbox events emitted by `create_upload_file` still work (aggregate_type changes from `"UploadFile"` to `"IngestFile"`)
- [ ] PortalEventOutbox partial index and unique constraint mirror OutboxEvent's patterns
