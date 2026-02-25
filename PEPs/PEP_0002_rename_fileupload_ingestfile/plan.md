# PEP 0002: Rename FileUpload to IngestFile — Implementation Plan

| Field | Value |
|-------|-------|
| **PEP** | 0002 |
| **Summary** | [summary.md](summary.md) |
| **Estimated Effort** | S |

---

## Context Files

Read these files before starting implementation:

- `PEPs/PEP_0002_rename_fileupload_ingestfile/summary.md` — acceptance criteria, scope, out-of-scope items
- `PEPs/PEP_0002_rename_fileupload_ingestfile/research.md` — full reference count, migration strategy, risk analysis
- `PEPs/PEP_0002_rename_fileupload_ingestfile/discussions.md` — resolved questions (migration strategy, verbose_name, related_name open thread)
- `uploads/models.py` — `FileUpload` model class being renamed (58 lines)
- `uploads/services/uploads.py` — service functions `create_upload`, `consume_upload`, `validate_file` (133 lines)
- `uploads/admin.py` — `FileUploadAdmin` class (32 lines)
- `uploads/tasks.py` — `cleanup_expired_uploads_task` with explicit `name=` string (67 lines)
- `uploads/tests/test_services.py` — 11 tests across `TestValidateFile`, `TestCreateUpload`, `TestConsumeUpload` (141 lines)
- `uploads/tests/test_tasks.py` — 5 tests in `TestCleanupExpiredUploadsTask`, includes `make_upload` fixture (104 lines)
- `uploads/migrations/0001_initial.py` — existing migration (DO NOT EDIT), needed for index name reference: `file_upload_user_id_c50e60_idx` (L75) and `file_upload_status_20c17f_idx` (L78)
- `aikb/models.md` — documents `FileUpload` model (5 occurrences to rename)
- `aikb/services.md` — documents `create_upload`, `consume_upload` functions (4 occurrences)
- `aikb/tasks.md` — documents `cleanup_expired_uploads_task` (2 occurrences)
- `aikb/admin.md` — documents `FileUploadAdmin` (2 occurrences)
- `aikb/architecture.md` — tree diagram and background processing section (5 occurrences)
- `CLAUDE.md` — references `cleanup_expired_uploads_task` on L249

## Prerequisites

- [ ] PEP 0001 (File Upload Infrastructure) is implemented — **confirmed**: `uploads/` app exists with model, services, admin, task, and tests
- [ ] No uncommitted changes in `uploads/` — run `git status uploads/` to verify clean state
- [ ] Database is migrated to current state — run `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py showmigrations uploads` to verify `[X] 0001_initial`

## Implementation Steps

### Step 1: Rename model class and Meta options

- [x] **Step 1**: Rename `FileUpload` → `IngestFile` in `uploads/models.py`
  - Files: `uploads/models.py` — modify existing file
  - Details:
    - L1: Change module docstring from `"""File upload model for temporary file storage."""` to `"""Ingest file model for temporary file storage."""`
    - L8: Rename class `FileUpload` → `IngestFile`
    - L9: Update class docstring: `"""Temporary file upload with lifecycle tracking."""` → `"""Temporary ingest file with lifecycle tracking."""`
    - L20: Update docstring reference: `Currently, create_upload transitions` → `Currently, create_ingest_file transitions`
    - L33: Change `related_name="uploads"` to `related_name="ingest_files"` (see discussions.md — zero current consumers, aligns with rename goal)
    - L47: Change `db_table = "file_upload"` → `db_table = "ingest_file"`
    - L48: Change `verbose_name = "file upload"` → `verbose_name = "ingest file"`
    - L49: Change `verbose_name_plural = "file uploads"` → `verbose_name_plural = "ingest files"`
    - Leave `Status` inner class, field definitions, `__str__`, `ordering`, and `indexes` unchanged
  - Verify: `grep -n "class IngestFile" uploads/models.py && grep -n 'db_table = "ingest_file"' uploads/models.py && grep -n 'related_name="ingest_files"' uploads/models.py`

### Step 2: Generate and verify migration

- [x] **Step 2**: Generate the rename migration via `makemigrations`
  - Files: `uploads/migrations/0002_*.py` — new file (auto-generated)
  - Details:
    - Run `makemigrations` after Step 1. Django should detect the model rename and prompt "Did you rename the uploads.FileUpload model to IngestFile? [y/N]". Answer `y`.
    - The migration should contain:
      - `migrations.RenameModel(old_name="FileUpload", new_name="IngestFile")` — renames model in Django state and content types
      - `migrations.AlterModelTable(name="ingestfile", table="ingest_file")` — renames actual DB table
      - `migrations.AlterModelOptions(name="ingestfile", options={"db_table": ..., "verbose_name": "ingest file", ...})` — updates verbose names
      - `migrations.RenameIndex(model_name="ingestfile", new_name="ingest_file_user_id_c50e60_idx", old_name="file_upload_user_id_c50e60_idx")` — renames composite index
      - `migrations.RenameIndex(model_name="ingestfile", new_name="ingest_file_status_20c17f_idx", old_name="file_upload_status_20c17f_idx")` — renames status index
      - `migrations.AlterField(...)` for the `related_name` change on the `user` FK
    - **CRITICAL**: Inspect the generated migration. If it contains `DeleteModel` + `CreateModel` instead of `RenameModel`, discard it and hand-craft the migration using the operations listed above.
    - **CRITICAL**: If `RenameIndex` operations are missing, add them manually. The old index names are in `uploads/migrations/0001_initial.py` lines 75 and 78.
  - Verify: `grep -n "RenameModel" uploads/migrations/0002_*.py && grep -n "RenameIndex" uploads/migrations/0002_*.py`

### Step 3: Apply migration and verify database state

- [ ] **Step 3**: Apply the rename migration
  - Files: none (database operation)
  - Details:
    - Run `migrate` to apply the new migration
    - Verify the table `ingest_file` exists and `file_upload` does not
    - Verify both renamed indexes exist
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py migrate uploads && source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py dbshell -- -c "SELECT tablename FROM pg_tables WHERE tablename IN ('file_upload', 'ingest_file');" | grep ingest_file`

### Step 4: Rename service functions

- [ ] **Step 4**: Rename services in `uploads/services/uploads.py`
  - Files: `uploads/services/uploads.py` — modify existing file (19 occurrences)
  - Details:
    - L1: Change module docstring to `"""Ingest file services for file validation, creation, and consumption."""`
    - L9: Change import `from uploads.models import FileUpload` → `from uploads.models import IngestFile`
    - L54: Rename function `create_upload` → `create_ingest_file`
    - L55: Update docstring: `"""Validate and store a file upload."""` → `"""Validate and store an ingest file."""`
    - L58: Update docstring: `user: The User instance who owns this upload.` → `user: The User instance who owns this ingest file.`
    - L62: Update docstring: `A FileUpload instance` → `An IngestFile instance`
    - L68: Change `FileUpload.objects.create(` → `IngestFile.objects.create(`
    - L74: Change `FileUpload.Status.FAILED` → `IngestFile.Status.FAILED`
    - L78: Update log: `"Upload failed validation for user %s: %s"` → `"Ingest file failed validation for user %s: %s"`
    - L84: Change `FileUpload.objects.create(` → `IngestFile.objects.create(`
    - L90: Change `FileUpload.Status.READY` → `IngestFile.Status.READY`
    - L93: Update log: `"Upload created: pk=%s user=%s file=%s size=%d"` → `"Ingest file created: pk=%s user=%s file=%s size=%d"`
    - L102: Rename function `consume_upload` → `consume_ingest_file`
    - L102: Rename parameter `file_upload` → `ingest_file`
    - L103: Update docstring: `"""Mark an upload as consumed by a downstream process."""` → `"""Mark an ingest file as consumed by a downstream process."""`
    - L110: Update docstring: `file_upload: A FileUpload instance to consume.` → `ingest_file: An IngestFile instance to consume.`
    - L113: Update docstring: `The updated FileUpload instance.` → `The updated IngestFile instance.`
    - L116: Update docstring: `ValueError: If the upload is not in READY status` → `ValueError: If the ingest file is not in READY status`
    - L119-122: Change all `FileUpload.objects.filter` → `IngestFile.objects.filter`, `FileUpload.Status.*` → `IngestFile.Status.*`
    - L120, 126, 127, 130, 131, 132: Change all `file_upload.pk` / `file_upload.status` / `file_upload.refresh_from_db()` / `return file_upload` → `ingest_file.*` / `return ingest_file`
    - L126: Update error: `f"Cannot consume upload {file_upload.pk}:` → `f"Cannot consume ingest file {ingest_file.pk}:`
    - L131: Update log: `"Upload consumed: pk=%s"` → `"Ingest file consumed: pk=%s"`
    - `validate_file` function (L14-51) is **unchanged** — per summary.md Out of Scope
  - Verify: `grep -c "FileUpload\|file_upload\|create_upload\|consume_upload" uploads/services/uploads.py` (expect 0)

### Step 5: Rename admin class

- [ ] **Step 5**: Rename admin in `uploads/admin.py`
  - Files: `uploads/admin.py` — modify existing file (3 occurrences)
  - Details:
    - L1: Change module docstring to `"""Admin configuration for ingest files."""`
    - L5: Change import `from uploads.models import FileUpload` → `from uploads.models import IngestFile`
    - L8: Change `@admin.register(FileUpload)` → `@admin.register(IngestFile)`
    - L9: Change `class FileUploadAdmin` → `class IngestFileAdmin`
    - L10: Change docstring: `"""Admin interface for inspecting and managing file uploads."""` → `"""Admin interface for inspecting and managing ingest files."""`
  - Verify: `grep -c "FileUpload\|FileUploadAdmin" uploads/admin.py` (expect 0)

### Step 6: Rename Celery task

- [ ] **Step 6**: Rename task in `uploads/tasks.py`
  - Files: `uploads/tasks.py` — modify existing file (5 occurrences)
  - Details:
    - L1: Module docstring `"""Celery tasks for the uploads app."""` — **unchanged** (app is still named `uploads`)
    - L16: Change task name string `name="uploads.tasks.cleanup_expired_uploads_task"` → `name="uploads.tasks.cleanup_expired_ingest_files_task"`
    - L21: Rename function `cleanup_expired_uploads_task` → `cleanup_expired_ingest_files_task`
    - L22: Update docstring: `"""Delete file uploads older than FILE_UPLOAD_TTL_HOURS."""` → `"""Delete ingest files older than FILE_UPLOAD_TTL_HOURS."""`
    - L33: Change lazy import `from uploads.models import FileUpload` → `from uploads.models import IngestFile`
    - L37: Change `FileUpload.objects.filter(` → `IngestFile.objects.filter(`
    - L41: Update log: `"No expired uploads to clean up."` → `"No expired ingest files to clean up."`
    - L47: Change `FileUpload.objects.filter(` → `IngestFile.objects.filter(`
    - L61: Update log: `"Cleaned up %d expired uploads (%d files removed), "` → `"Cleaned up %d expired ingest files (%d files removed), "`
  - Verify: `grep -c "FileUpload\|cleanup_expired_uploads" uploads/tasks.py` (expect 0)

### Step 7: Update service tests

- [ ] **Step 7**: Update `uploads/tests/test_services.py`
  - Files: `uploads/tests/test_services.py` — modify existing file (22 occurrences)
  - Details:
    - L1: Change module docstring to `"""Unit tests for ingest file services."""`
    - L8: Change import `from uploads.models import FileUpload` → `from uploads.models import IngestFile`
    - L9: Change import `from uploads.services.uploads import consume_upload, create_upload, validate_file` → `from uploads.services.uploads import consume_ingest_file, create_ingest_file, validate_file`
    - L64: Rename class `TestCreateUpload` → `TestCreateIngestFile`
    - L65: Update docstring: `"""Tests for create_upload service."""` → `"""Tests for create_ingest_file service."""`
    - L69: Update docstring: `"""Valid file creates FileUpload with status=READY."""` → `"""Valid file creates IngestFile with status=READY."""`
    - L72: Change `create_upload(user, file)` → `create_ingest_file(user, file)`
    - L74: Change `FileUpload.Status.READY` → `IngestFile.Status.READY`
    - L83: Update docstring: `"""File exceeding max size creates FileUpload with status=FAILED."""` → `"""File exceeding max size creates IngestFile with status=FAILED."""`
    - L87: Change `create_upload(user, file)` → `create_ingest_file(user, file)`
    - L89: Change `FileUpload.Status.FAILED` → `IngestFile.Status.FAILED`
    - L95: Update docstring: `"""Returned FileUpload has correct...` → `"""Returned IngestFile has correct...`
    - L98: Change `create_upload(user, file)` → `create_ingest_file(user, file)`
    - L105: Rename class `TestConsumeUpload` → `TestConsumeIngestFile`
    - L106: Update docstring: `"""Tests for consume_upload service."""` → `"""Tests for consume_ingest_file service."""`
    - L113, 124, 136: Change all `create_upload(...)` → `create_ingest_file(...)`
    - L114, 117, 137: Change all `FileUpload.Status.*` → `IngestFile.Status.*`
    - L116, 125, 128, 140: Change all `consume_upload(...)` → `consume_ingest_file(...)`
  - Verify: `grep -c "FileUpload\|create_upload\|consume_upload" uploads/tests/test_services.py` (expect 0)

### Step 8: Update task tests

- [ ] **Step 8**: Update `uploads/tests/test_tasks.py`
  - Files: `uploads/tests/test_tasks.py` — modify existing file (16 occurrences)
  - Details:
    - L1: Change module docstring to `"""Unit tests for ingest file cleanup task."""`
    - L9: Change import `from uploads.models import FileUpload` → `from uploads.models import IngestFile`
    - L10: Change import `from uploads.tasks import cleanup_expired_uploads_task` → `from uploads.tasks import cleanup_expired_ingest_files_task`
    - L20: Rename fixture docstring: `"""Factory fixture to create FileUpload instances."""` → `"""Factory fixture to create IngestFile instances."""`
    - L23: Change `status=FileUpload.Status.READY` → `status=IngestFile.Status.READY`
    - L25: Change `FileUpload.objects.create(` → `IngestFile.objects.create(`
    - L35: Change `FileUpload.objects.filter(` → `IngestFile.objects.filter(`
    - L43: Rename class `TestCleanupExpiredUploadsTask` → `TestCleanupExpiredIngestFilesTask`
    - L44: Update docstring: `"""Tests for cleanup_expired_uploads_task."""` → `"""Tests for cleanup_expired_ingest_files_task."""`
    - L48, 56, 71, 80, 97: Change all `cleanup_expired_uploads_task()` → `cleanup_expired_ingest_files_task()`
    - L60, 74, 83, 101: Change all `FileUpload.objects.filter(` / `FileUpload.objects.count()` → `IngestFile.objects.*`
  - Verify: `grep -c "FileUpload\|cleanup_expired_uploads" uploads/tests/test_tasks.py` (expect 0)

### Step 9: Update aikb documentation

- [ ] **Step 9**: Update all `aikb/` files with new naming
  - Files:
    - `aikb/models.md` — rename `FileUpload` → `IngestFile`, `file_upload` → `ingest_file`, `create_upload` → `create_ingest_file`, `related_name="uploads"` → `related_name="ingest_files"` throughout §Uploads App and §Entity Relationship Summary
    - `aikb/services.md` — rename `create_upload` → `create_ingest_file`, `consume_upload` → `consume_ingest_file`, `FileUpload` → `IngestFile` throughout §Uploads App
    - `aikb/tasks.md` — rename `cleanup_expired_uploads_task` → `cleanup_expired_ingest_files_task`, `FileUpload` → `IngestFile` throughout §Uploads App
    - `aikb/admin.md` — rename `FileUpload` → `IngestFile`, `FileUploadAdmin` → `IngestFileAdmin` in §uploads/admin.py section
    - `aikb/architecture.md` — update tree diagram L64-68 (`FileUpload` → `IngestFile`, `FileUploadAdmin` → `IngestFileAdmin`, `create_upload` → `create_ingest_file`, `consume_upload` → `consume_ingest_file`, `cleanup_expired_uploads_task` → `cleanup_expired_ingest_files_task`), update L134 background processing reference
  - Details:
    - For `aikb/models.md`:
      - L26: `### FileUpload (TimeStampedModel)` → `### IngestFile (TimeStampedModel)`
      - L27: Update description, change `db_table = "file_upload"` → `db_table = "ingest_file"`
      - L30: Change `related_name="uploads"` → `related_name="ingest_files"`
      - L40: `**Status Choices (FileUpload.Status):**` → `**Status Choices (IngestFile.Status):**`
      - L41: `create_upload` → `create_ingest_file`
      - L63: `└── FileUpload (uploads.FileUpload, via user FK, CASCADE)` → `└── IngestFile (uploads.IngestFile, via user FK, CASCADE)`
    - For `aikb/services.md`:
      - L53: `**\`create_upload(user, file)\`**` → `**\`create_ingest_file(user, file)\`**`
      - L54: All `FileUpload` → `IngestFile`
      - L56: `**\`consume_upload(file_upload)\`**` → `**\`consume_ingest_file(ingest_file)\`**`
      - L57: All `FileUpload` → `IngestFile`
    - For `aikb/tasks.md`:
      - L54: `**\`cleanup_expired_uploads_task\`**` → `**\`cleanup_expired_ingest_files_task\`**`
      - L55: `uploads.tasks.cleanup_expired_uploads_task` → `uploads.tasks.cleanup_expired_ingest_files_task`
      - L56: `file uploads` → `ingest files`
    - For `aikb/admin.md`:
      - L26: `@admin.register(FileUpload)` → `@admin.register(IngestFile)`
      - L27: `class FileUploadAdmin` → `class IngestFileAdmin`
    - For `aikb/architecture.md`:
      - L64: `FileUpload (temporary file with lifecycle tracking)` → `IngestFile (temporary file with lifecycle tracking)`
      - L65: `FileUploadAdmin` → `IngestFileAdmin`
      - L66: `validate_file, create_upload, consume_upload` → `validate_file, create_ingest_file, consume_ingest_file`
      - L67: `cleanup_expired_uploads_task` → `cleanup_expired_ingest_files_task`
      - L134: `cleanup_expired_uploads_task` → `cleanup_expired_ingest_files_task`, `expired file uploads` → `expired ingest files`
  - Verify: `grep -rn "FileUpload\|file_upload\|FileUploadAdmin\|create_upload\|consume_upload\|cleanup_expired_uploads" aikb/` (expect 0 results)

### Step 10: Update CLAUDE.md

- [ ] **Step 10**: Update `CLAUDE.md` task reference
  - Files: `CLAUDE.md` — modify existing file (1 occurrence)
  - Details:
    - L249: Change `Tasks defined: \`cleanup_expired_uploads_task\` (uploads app)` → `Tasks defined: \`cleanup_expired_ingest_files_task\` (uploads app)`
  - Verify: `grep -n "cleanup_expired" CLAUDE.md | grep -v "uploads_task"` (should show `cleanup_expired_ingest_files_task`)

## Testing

- [ ] **All 16 existing tests pass with new naming** — The test count remains 16 (11 service + 5 task). No new tests are needed — this is a pure rename with no behavior changes.
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev pytest uploads/tests/ -v`
- [ ] **No remaining old-name references in Python source** (excluding migrations and PEPs)
  - Verify: `grep -rn "FileUpload\|FileUploadAdmin\|create_upload\|consume_upload\|cleanup_expired_uploads" --include="*.py" uploads/ | grep -v migrations/`
- [ ] **No remaining old-name references in documentation** (excluding PEPs)
  - Verify: `grep -rn "FileUpload\|FileUploadAdmin\|create_upload\|consume_upload\|cleanup_expired_uploads" aikb/ CLAUDE.md`

## Rollback Plan

1. **Reverse migration**: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py migrate uploads 0001` — this reverses the table/index rename back to `file_upload`.
2. **Revert code changes**: `git checkout -- uploads/ aikb/ CLAUDE.md` — restores all source files to pre-rename state.
3. **Delete generated migration**: `rm uploads/migrations/0002_*.py`
4. **Verify rollback**: Run `python manage.py check` and `pytest uploads/tests/ -v` to confirm everything works with old naming.

No feature flags needed. No data cleanup needed (pure schema rename, no data transformation). The migration is fully reversible because Django's `RenameModel`, `AlterModelTable`, `RenameIndex`, and `AlterField` all have reverse operations.

## aikb Impact Map

- [ ] `aikb/models.md` — Rename `FileUpload` → `IngestFile` in §Uploads App heading (L26), description (L27), `db_table` (L27), `related_name` (L30), Status Choices header (L40), `create_upload` reference (L41), ER diagram (L63)
- [ ] `aikb/services.md` — Rename `create_upload` → `create_ingest_file` (L53), `consume_upload` → `consume_ingest_file` (L56), all `FileUpload` → `IngestFile` in return type descriptions (L54, L57)
- [ ] `aikb/tasks.md` — Rename `cleanup_expired_uploads_task` → `cleanup_expired_ingest_files_task` (L54-55), update description to say "ingest files" (L56)
- [ ] `aikb/signals.md` — N/A (no FileUpload references)
- [ ] `aikb/admin.md` — Rename `FileUpload` → `IngestFile` and `FileUploadAdmin` → `IngestFileAdmin` in code block (L26-27)
- [ ] `aikb/cli.md` — N/A (no FileUpload references)
- [ ] `aikb/architecture.md` — Update tree diagram: model name (L64), admin class (L65), service function names (L66), task name (L67). Update background processing section (L134)
- [ ] `aikb/conventions.md` — N/A (no direct FileUpload references)
- [ ] `aikb/dependencies.md` — N/A (no FileUpload references)
- [ ] `aikb/specs-roadmap.md` — N/A (references "File upload infrastructure" which is the app name, not the model name)
- [ ] `CLAUDE.md` — Update task reference on L249: `cleanup_expired_uploads_task` → `cleanup_expired_ingest_files_task`

## Final Verification

### Acceptance Criteria

- [ ] **The `IngestFile` model exists in `uploads/models.py` with `db_table = "ingest_file"`**
  - Verify: `grep -n 'class IngestFile' uploads/models.py && grep -n 'db_table = "ingest_file"' uploads/models.py`

- [ ] **No references to `FileUpload` or `FileUploadAdmin` remain in Python source files (excluding migrations)**
  - Verify: `grep -rn "FileUpload\|FileUploadAdmin" --include="*.py" uploads/ | grep -v migrations/` (expect 0 results)

- [ ] **A database migration renames the table from `file_upload` to `ingest_file`**
  - Verify: `ls uploads/migrations/0002_*.py && grep "RenameModel" uploads/migrations/0002_*.py`

- [ ] **`python manage.py check` passes with no errors**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check`

- [ ] **`python manage.py migrate` applies the rename migration successfully**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py showmigrations uploads` (expect `[X] 0001_initial` and `[X] 0002_*`)

- [ ] **All 16 existing tests pass with the new naming**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev pytest uploads/tests/ -v`

- [ ] **`ruff check .` passes with no lint errors**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && ruff check .`

- [ ] **All `aikb/` documentation files reflect the new naming**
  - Verify: `grep -rn "FileUpload\|FileUploadAdmin\|create_upload\|consume_upload\|cleanup_expired_uploads" aikb/` (expect 0 results)

- [ ] **`CLAUDE.md` reflects the new naming where applicable**
  - Verify: `grep -n "cleanup_expired" CLAUDE.md` (should show `cleanup_expired_ingest_files_task`)

### Integration Checks

- [ ] **Model import works from all consumers**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from uploads.models import IngestFile; print(IngestFile._meta.db_table);"` (expect `ingest_file`)

- [ ] **Service functions are importable with new names**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from uploads.services.uploads import create_ingest_file, consume_ingest_file, validate_file; print('OK')"`

- [ ] **Celery task is registered with new name**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from uploads.tasks import cleanup_expired_ingest_files_task; print(cleanup_expired_ingest_files_task.name)"` (expect `uploads.tasks.cleanup_expired_ingest_files_task`)

- [ ] **Admin is registered with new class**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from django.contrib import admin; from uploads.models import IngestFile; print(admin.site.is_registered(IngestFile))"` (expect `True`)

- [ ] **Comprehensive old-name sweep** — No `FileUpload`, `file_upload` (non-migration), `create_upload`, `consume_upload`, or `cleanup_expired_uploads` references remain in any source or doc file
  - Verify: `grep -rn "FileUpload\|create_upload\|consume_upload\|cleanup_expired_uploads\|FileUploadAdmin" --include="*.py" --include="*.md" . | grep -v migrations/ | grep -v PEPs/` (expect 0 results)

### Regression Checks

- [ ] `python manage.py check` passes
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check`
- [ ] `ruff check .` passes
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && ruff check .`
- [ ] Full test suite passes (not just uploads tests)
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev pytest -v`

## Detailed Todo List

### Phase 1: Pre-flight checks

- [ ] Verify no uncommitted changes in `uploads/`: `git status uploads/`
- [ ] Verify database is migrated: `python manage.py showmigrations uploads` shows `[X] 0001_initial`
- [ ] Verify existing tests pass before any changes: `pytest uploads/tests/ -v`
- [ ] Read all context files listed above (model, services, admin, tasks, tests)

### Phase 2: Model rename (Step 1)

- [ ] Rename class `FileUpload` → `IngestFile` in `uploads/models.py`
- [ ] Update module docstring to reference "Ingest file"
- [ ] Update class docstring to reference "ingest file"
- [ ] Update inline docstring reference: `create_upload` → `create_ingest_file`
- [ ] Change `related_name="uploads"` → `related_name="ingest_files"` on user FK
- [ ] Change `db_table = "file_upload"` → `db_table = "ingest_file"`
- [ ] Change `verbose_name` and `verbose_name_plural` to "ingest file" / "ingest files"
- [ ] Verify: `grep -n "class IngestFile" uploads/models.py` succeeds
- [ ] Verify: no `FileUpload` references remain: `grep -c "FileUpload" uploads/models.py` returns 0

### Phase 3: Migration (Steps 2–3)

- [ ] Run `makemigrations` — answer `y` to model rename prompt
- [ ] Inspect generated migration for `RenameModel` (not `DeleteModel` + `CreateModel`)
- [ ] Inspect generated migration for `AlterModelTable` with `table="ingest_file"`
- [ ] Inspect generated migration for `RenameIndex` operations (both indexes)
  - [ ] `file_upload_user_id_c50e60_idx` → `ingest_file_user_id_c50e60_idx`
  - [ ] `file_upload_status_20c17f_idx` → `ingest_file_status_20c17f_idx`
- [ ] If `RenameIndex` ops are missing, add them manually referencing `0001_initial.py` L75, L78
- [ ] Apply migration: `python manage.py migrate uploads`
- [ ] Verify table exists: `dbshell` query confirms `ingest_file` exists, `file_upload` does not

### Phase 4: Service renames (Step 4)

- [ ] Change import `FileUpload` → `IngestFile` in `uploads/services/uploads.py`
- [ ] Rename function `create_upload` → `create_ingest_file`
  - [ ] Update function docstring (description, parameter docs, return type)
  - [ ] Replace all `FileUpload.objects.create` → `IngestFile.objects.create`
  - [ ] Replace all `FileUpload.Status.*` → `IngestFile.Status.*`
  - [ ] Update log messages from "Upload" to "Ingest file"
- [ ] Rename function `consume_upload` → `consume_ingest_file`
  - [ ] Rename parameter `file_upload` → `ingest_file`
  - [ ] Update function docstring (description, parameter docs, return type, raises)
  - [ ] Replace all `FileUpload.objects.filter` → `IngestFile.objects.filter`
  - [ ] Replace all `FileUpload.Status.*` → `IngestFile.Status.*`
  - [ ] Replace all `file_upload.pk` / `file_upload.status` / `file_upload.refresh_from_db()` → `ingest_file.*`
  - [ ] Update log messages and error messages
- [ ] Update module docstring to reference "Ingest file"
- [ ] Leave `validate_file` unchanged (per Out of Scope)
- [ ] Verify: `grep -c "FileUpload\|file_upload\|create_upload\|consume_upload" uploads/services/uploads.py` returns 0

### Phase 5: Admin rename (Step 5)

- [ ] Change import `FileUpload` → `IngestFile` in `uploads/admin.py`
- [ ] Change `@admin.register(FileUpload)` → `@admin.register(IngestFile)`
- [ ] Rename class `FileUploadAdmin` → `IngestFileAdmin`
- [ ] Update module and class docstrings
- [ ] Verify: `grep -c "FileUpload\|FileUploadAdmin" uploads/admin.py` returns 0

### Phase 6: Task rename (Step 6)

- [ ] Change lazy import `FileUpload` → `IngestFile` in `uploads/tasks.py`
- [ ] Change task `name=` string to `"uploads.tasks.cleanup_expired_ingest_files_task"`
- [ ] Rename function `cleanup_expired_uploads_task` → `cleanup_expired_ingest_files_task`
- [ ] Replace all `FileUpload.objects.filter` → `IngestFile.objects.filter`
- [ ] Update docstring and log messages ("uploads" → "ingest files")
- [ ] Verify: `grep -c "FileUpload\|cleanup_expired_uploads" uploads/tasks.py` returns 0

### Phase 7: Test updates (Steps 7–8)

- [ ] Update `uploads/tests/test_services.py`
  - [ ] Change imports: `FileUpload` → `IngestFile`, `create_upload` → `create_ingest_file`, `consume_upload` → `consume_ingest_file`
  - [ ] Rename class `TestCreateUpload` → `TestCreateIngestFile`
  - [ ] Rename class `TestConsumeUpload` → `TestConsumeIngestFile`
  - [ ] Replace all `create_upload(` → `create_ingest_file(` calls
  - [ ] Replace all `consume_upload(` → `consume_ingest_file(` calls
  - [ ] Replace all `FileUpload.Status.*` → `IngestFile.Status.*`
  - [ ] Update all docstrings referencing old names
  - [ ] Verify: `grep -c "FileUpload\|create_upload\|consume_upload" uploads/tests/test_services.py` returns 0
- [ ] Update `uploads/tests/test_tasks.py`
  - [ ] Change imports: `FileUpload` → `IngestFile`, `cleanup_expired_uploads_task` → `cleanup_expired_ingest_files_task`
  - [ ] Rename class `TestCleanupExpiredUploadsTask` → `TestCleanupExpiredIngestFilesTask`
  - [ ] Replace all `FileUpload.objects.*` → `IngestFile.objects.*`
  - [ ] Replace all `FileUpload.Status.*` → `IngestFile.Status.*`
  - [ ] Replace all `cleanup_expired_uploads_task()` → `cleanup_expired_ingest_files_task()`
  - [ ] Update fixture docstring and all test docstrings
  - [ ] Verify: `grep -c "FileUpload\|cleanup_expired_uploads" uploads/tests/test_tasks.py` returns 0

### Phase 8: Test execution

- [ ] Run all uploads tests: `pytest uploads/tests/ -v` — expect 16 passing
- [ ] Verify no old-name references remain in Python source (excluding migrations): `grep -rn "FileUpload\|FileUploadAdmin\|create_upload\|consume_upload\|cleanup_expired_uploads" --include="*.py" uploads/ | grep -v migrations/` returns 0
- [ ] Run `python manage.py check` — expect no errors
- [ ] Run `ruff check .` — expect no lint errors

### Phase 9: Documentation updates (Steps 9–10)

- [ ] Update `aikb/models.md`
  - [ ] Rename heading `FileUpload` → `IngestFile`
  - [ ] Update `db_table`, `related_name`, description, Status Choices header
  - [ ] Update `create_upload` reference → `create_ingest_file`
  - [ ] Update ER diagram line
- [ ] Update `aikb/services.md`
  - [ ] Rename `create_upload` → `create_ingest_file` heading and description
  - [ ] Rename `consume_upload` → `consume_ingest_file` heading and description
  - [ ] Replace all `FileUpload` → `IngestFile` in return types
- [ ] Update `aikb/tasks.md`
  - [ ] Rename `cleanup_expired_uploads_task` → `cleanup_expired_ingest_files_task`
  - [ ] Update task name string and description
- [ ] Update `aikb/admin.md`
  - [ ] Rename `FileUpload` → `IngestFile` and `FileUploadAdmin` → `IngestFileAdmin`
- [ ] Update `aikb/architecture.md`
  - [ ] Update tree diagram: model, admin, service functions, task name
  - [ ] Update background processing section reference
- [ ] Update `CLAUDE.md` L249: `cleanup_expired_uploads_task` → `cleanup_expired_ingest_files_task`
- [ ] Verify: `grep -rn "FileUpload\|FileUploadAdmin\|create_upload\|consume_upload\|cleanup_expired_uploads" aikb/ CLAUDE.md` returns 0

### Phase 10: Final verification

- [ ] Run acceptance criteria checks (all items from Final Verification § above)
- [ ] Run integration checks (model import, service imports, task registration, admin registration)
- [ ] Run comprehensive old-name sweep across all source and doc files (excluding migrations and PEPs)
- [ ] Run regression checks: `python manage.py check`, `ruff check .`, `pytest -v` (full suite)

## Completion

- [ ] **Update `PEPs/IMPLEMENTED/LATEST.md`** — Add entry with PEP number, title, commit hash(es), and summary
- [ ] **Update `PEPs/INDEX.md`** — Remove the PEP row
- [ ] **Remove PEP directory** — Delete `PEPs/PEP_0002_rename_fileupload_ingestfile/`
