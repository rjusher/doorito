# PEP 0008: Canonical Domain Model for OSS Ingest Portal — Implementation Plan

| Field | Value |
|-------|-------|
| **PEP** | 0008 |
| **Summary** | [summary.md](summary.md) |
| **Estimated Effort** | L |

---

## Context Files

Read these files before implementing any step. Each is listed with the specific reason it's needed.

| File | Why |
|------|-----|
| `aikb/models.md` | Upload model field definitions, FK cascade rules, entity relationships — the authoritative reference for existing model structure |
| `aikb/conventions.md` | Model patterns (TimeStampedModel, uuid7, TextChoices), service layer patterns, import ordering, naming conventions |
| `aikb/architecture.md` | App structure table (line 39–81), `INSTALLED_APPS` list, Celery configuration, URL routing |
| `aikb/services.md` | Upload service function signatures and behavior — `create_upload_file`, `finalize_batch`, `notify_expiring_files`, session services |
| `aikb/tasks.md` | Task naming convention (`uploads.tasks.*`), `CELERY_BEAT_SCHEDULE` entries, task conventions |
| `aikb/admin.md` | Upload admin class patterns, `list_select_related`, `date_hierarchy` conventions |
| `uploads/models.py` | Source of truth for model fields, Status choices, db_table values, indexes, constraints — the code being modified |
| `uploads/admin.py` | Admin registrations to update (imports from `uploads.models`) |
| `uploads/services/uploads.py` | 9 service functions — `mark_file_processed` (line 149), `mark_file_deleted` (line 197), `finalize_batch` (line 238), `notify_expiring_files` (line 274) must be modified |
| `uploads/services/sessions.py` | 3 session service functions — imports `from uploads.models` (line 8) |
| `uploads/tasks.py` | 2 tasks with `name="uploads.tasks.*"` (lines 16, 70) and lazy imports `from uploads.models` (line 33) and `from uploads.services.uploads` (line 84) |
| `uploads/apps.py` | Current `UploadsConfig` with `name = "uploads"` (line 7) |
| `uploads/migrations/0001_initial.py` | Initial migration — FK references to `"uploads.uploadbatch"` (line 124), `"uploads.uploadfile"` (line 213), `"uploads.uploadsession"` (line 286); explicit `db_table` values |
| `common/models.py` | `OutboxEvent` model (lines 19–67) — template for `PortalEventOutbox` field structure, Status choices, indexes, constraints |
| `common/admin.py` | `OutboxEventAdmin` (lines 9–49) — template for `PortalEventOutboxAdmin` pattern |
| `boot/settings.py` | `INSTALLED_APPS` (line 40: `"uploads"`), `CELERY_BEAT_SCHEDULE` property (lines 148–176: task paths `uploads.tasks.*`) |
| `frontend/views/upload.py` | Imports `from uploads.models import UploadFile` (line 8) and `from uploads.services.uploads import ...` (line 9) |
| `frontend/tests/test_views_upload.py` | Import `from uploads.models import UploadBatch, UploadFile` (line 6) |
| `uploads/tests/test_models.py` | Import `from uploads.models import ...` (line 9); `test_status_choices` (lines 210–237) asserts 5 UploadFile statuses |
| `uploads/tests/test_services.py` | Imports `mark_file_deleted, mark_file_processed` (lines 19–21); `TestMarkFileProcessed` (line 130), `TestMarkFileDeleted` (line 170); `test_skips_non_stored_files` uses `PROCESSED` (line 325) |
| `uploads/tests/test_sessions.py` | Import `from uploads.models` (line 6), `from uploads.services.sessions` (lines 7–11) |
| `uploads/tests/test_tasks.py` | Import `from uploads.models` (line 9), `from uploads.tasks` (line 10); `from uploads import tasks` (line 86) |
| `conftest.py` | Root conftest — `user` fixture (no uploads references, no changes needed) |
| `PEPs/PEP_0008_canonical_domain_model/discussions.md` | All resolved design decisions — naming, db_table convention, storage deferral, service scope |
| `PEPs/PEP_0008_canonical_domain_model/research.md` | Risk analysis, migration strategy, pattern analysis, structural overlap assessment |

## Prerequisites

<!-- Amendment 2026-02-28: Preflight — fixed DB prerequisite (Dev uses SQLite), added orphan cleanup -->
- Database accessible (SQLite in Dev, PostgreSQL in Production)
- Virtual environment active: `source ~/.virtualenvs/inventlily-d22a143/bin/activate`
- Current tests pass: `DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py test`
- No unapplied migrations: `DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py migrate --check`
- **Orphaned database records cleaned up** (from a previous implementation attempt):
  ```sql
  -- Run via: source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py dbshell
  DELETE FROM django_migrations WHERE app='uploads' AND name='0002_rename_fileupload_ingestfile';
  DELETE FROM django_content_type WHERE app_label='uploads' AND model='ingestfile';
  DROP TABLE IF EXISTS ingest_file;
  ```

## Implementation Steps

<!-- Amendment 2026-02-27: Changed from "create new app" to "evolve uploads app" per discussions.md decision -->
<!-- Amendment 2026-02-27: Clarified app name as "portal" per discussions.md -->
<!-- Amendment 2026-02-28: Clarified migration file handling and physical rename steps per discussions.md -->
<!-- Amendment 2026-02-28: Added table renames to portal_upload_* per discussions.md db_table naming decision -->
<!-- Amendment 2026-02-28: Preflight — fixed migration chicken-and-egg, added FK ref updates in 0001_initial, added Step 6a/6b pre-migration -->

### Phase A: App Rename (uploads → portal)

- [ ] **Step 1**: Physically rename `uploads/` directory to `portal/`
  - **Files**: `uploads/` → `portal/` (directory rename, includes `uploads/migrations/` → `portal/migrations/`)
  - **Details**: Use `git mv uploads portal` to rename the directory. This moves all files including:
    - `portal/__init__.py` (empty)
    - `portal/apps.py`
    - `portal/models.py`
    - `portal/admin.py`
    - `portal/tasks.py`
    - `portal/services/__init__.py` (empty)
    - `portal/services/uploads.py`
    - `portal/services/sessions.py`
    - `portal/tests/__init__.py` (empty)
    - `portal/tests/test_models.py`
    - `portal/tests/test_services.py`
    - `portal/tests/test_sessions.py`
    - `portal/tests/test_tasks.py`
    - `portal/migrations/__init__.py` (empty)
    - `portal/migrations/0001_initial.py`
  - **Verify**: `ls portal/models.py portal/migrations/0001_initial.py portal/apps.py`

- [ ] **Step 1a**: Update FK references in `portal/migrations/0001_initial.py`
  - **Files**: `portal/migrations/0001_initial.py` (modify)
  - **Details**: After moving the migration file, update the `to=` FK reference strings from the old `uploads` app label to `portal`. These are read by Django's migration state builder to construct the model graph; leaving them as `uploads.*` will cause state errors since `uploads` is no longer in `INSTALLED_APPS`. This is safe because the migration is already applied — Django won't re-run it.
    - Line 124: `to="uploads.uploadbatch"` → `to="portal.uploadbatch"`
    - Line 213: `to="uploads.uploadfile"` → `to="portal.uploadfile"`
    - Line 286: `to="uploads.uploadsession"` → `to="portal.uploadsession"`
  - **Verify**: `grep -n 'to="uploads\.' portal/migrations/0001_initial.py` (should return zero results)

- [ ] **Step 2**: Update `portal/apps.py` — app configuration
  - **Files**: `portal/apps.py` (modify)
  - **Details**: Change `UploadsConfig` class:
    ```python
    class PortalConfig(AppConfig):
        name = "portal"
        verbose_name = "Portal"
        default_auto_field = "django.db.models.BigAutoField"
    ```
    Change class name from `UploadsConfig` to `PortalConfig`, `name` from `"uploads"` to `"portal"`, `verbose_name` from `"Uploads"` to `"Portal"`. Update module docstring to `"""Django AppConfig for the portal app."""`.
  - **Verify**: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && python -c "from portal.apps import PortalConfig; assert PortalConfig.name == 'portal'"`

- [ ] **Step 3**: Update `boot/settings.py` — INSTALLED_APPS and CELERY_BEAT_SCHEDULE
  - **Files**: `boot/settings.py` (modify)
  - **Details**:
    1. Line 40: Change `"uploads"` to `"portal"` in `INSTALLED_APPS`
    2. Line 155: Change `"task": "uploads.tasks.cleanup_expired_upload_files_task"` to `"task": "portal.tasks.cleanup_expired_upload_files_task"`
    3. Line 172: Change `"task": "uploads.tasks.notify_expiring_files_task"` to `"task": "portal.tasks.notify_expiring_files_task"`
  - **Verify**: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && python -c "from boot.settings import Base; apps = Base.INSTALLED_APPS; assert 'portal' in apps and 'uploads' not in apps"`

- [ ] **Step 4**: Update all `uploads.*` imports across the codebase
  - **Files** (8 files to modify):
    - `portal/models.py` — no internal `uploads.*` imports (uses `common.models`, `common.utils`, `django.*`)
    - `portal/admin.py` line 5: `from uploads.models import ...` → `from portal.models import ...`
    - `portal/services/uploads.py` line 15: `from uploads.models import UploadBatch, UploadFile` → `from portal.models import UploadBatch, UploadFile`
    - `portal/services/sessions.py` line 8: `from uploads.models import UploadFile, UploadPart, UploadSession` → `from portal.models import UploadFile, UploadPart, UploadSession`
    - `portal/tasks.py` line 33: `from uploads.models import UploadFile` → `from portal.models import UploadFile`
    - `portal/tasks.py` line 84: `from uploads.services.uploads import notify_expiring_files` → `from portal.services.uploads import notify_expiring_files`
    - `frontend/views/upload.py` line 8: `from uploads.models import UploadFile` → `from portal.models import UploadFile`
    - `frontend/views/upload.py` line 9: `from uploads.services.uploads import create_batch, create_upload_file, finalize_batch` → `from portal.services.uploads import create_batch, create_upload_file, finalize_batch`
  - **Details**: Simple find-and-replace of `from uploads.` to `from portal.` in all 8 files listed above. Do NOT change `upload_to="uploads/%Y/%m/"` in `portal/models.py` line 78 — that's a storage path, not a module import.
  - **Verify**: `grep -r "from uploads\." --include="*.py" . | grep -v ".pyc" | grep -v "migrations/" | grep -v "PEPs/" | grep -v "__pycache__"`  (should return zero results)

- [ ] **Step 5**: Update task name strings in `portal/tasks.py`
  - **Files**: `portal/tasks.py` (modify)
  - **Details**:
    1. Line 16: `name="uploads.tasks.cleanup_expired_upload_files_task"` → `name="portal.tasks.cleanup_expired_upload_files_task"`
    2. Line 70: `name="uploads.tasks.notify_expiring_files_task"` → `name="portal.tasks.notify_expiring_files_task"`
    3. Update module docstring: `"""Celery tasks for the uploads app."""` → `"""Celery tasks for the portal app."""`
  - **Verify**: `grep -n "uploads\.tasks\." portal/tasks.py` (should return zero results)

- [ ] **Step 6a**: Pre-migration: update `django_migrations` and `django_content_type` outside of the migration framework
  - **Files**: none (database-only operation)
  - **Details**: Django's migration executor resolves dependencies by checking `django_migrations` for applied migrations. After renaming the directory to `portal/`, Django will look for `(app='portal', name='0001_initial')` but the row still says `app='uploads'`. This causes a chicken-and-egg problem: `0002_rename_app.py` depends on `0001_initial` being applied as `portal`, but the update happens inside the migration that can't run. **Fix**: Run the updates before `migrate`:
    ```bash
    source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py dbshell <<'SQL'
    UPDATE django_migrations SET app = 'portal' WHERE app = 'uploads';
    UPDATE django_content_type SET app_label = 'portal' WHERE app_label = 'uploads';
    SQL
    ```
  - **Verify**: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py showmigrations portal` — should show `[X] 0001_initial`

- [ ] **Step 6b**: Update `db_table` values in `portal/models.py` and create rename migration
  - **Files**: `portal/models.py` (modify), `portal/migrations/0002_rename_app.py` (new file)
  - **Details**:
    1. Update `portal/models.py` db_table values:
       - `UploadBatch.Meta.db_table`: `"upload_batch"` → `"portal_upload_batch"` (line 39)
       - `UploadFile.Meta.db_table`: `"upload_file"` → `"portal_upload_file"` (line 92)
       - `UploadSession.Meta.db_table`: `"upload_session"` → `"portal_upload_session"` (line 154)
       - `UploadPart.Meta.db_table`: `"upload_part"` → `"portal_upload_part"` (line 199)
    2. Create manual migration `portal/migrations/0002_rename_app.py`:
       ```python
       """Rename uploads app to portal: rename database tables."""

       from django.db import migrations


       class Migration(migrations.Migration):
           dependencies = [
               ("portal", "0001_initial"),
           ]

           operations = [
               # Rename database tables
               migrations.RunSQL(
                   "ALTER TABLE upload_batch RENAME TO portal_upload_batch",
                   "ALTER TABLE portal_upload_batch RENAME TO upload_batch",
               ),
               migrations.RunSQL(
                   "ALTER TABLE upload_file RENAME TO portal_upload_file",
                   "ALTER TABLE portal_upload_file RENAME TO upload_file",
               ),
               migrations.RunSQL(
                   "ALTER TABLE upload_session RENAME TO portal_upload_session",
                   "ALTER TABLE portal_upload_session RENAME TO upload_session",
               ),
               migrations.RunSQL(
                   "ALTER TABLE upload_part RENAME TO portal_upload_part",
                   "ALTER TABLE portal_upload_part RENAME TO upload_part",
               ),
           ]
       ```
       Note: `django_migrations` and `django_content_type` updates are handled in Step 6a (pre-migration) to avoid the chicken-and-egg dependency problem. The migration only handles table renames.
  - **Verify**: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py migrate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py showmigrations portal`

- [ ] **Step 7**: Verify app rename integrity
  - **Files**: none (verification only)
  - **Details**: Confirm the app rename is fully consistent:
    1. `showmigrations portal` shows both `0001_initial` and `0002_rename_app` as applied
    2. `check` passes with no errors
    3. No orphaned `uploads.*` imports remain
  - **Verify**: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check && grep -r "from uploads\." --include="*.py" . | grep -v ".pyc" | grep -v "migrations/" | grep -v "PEPs/" | grep -v "__pycache__" | wc -l`  (should output 0)

### Phase B: Model Changes (Status Simplification + PortalEventOutbox)

- [ ] **Step 8**: Simplify UploadFile status choices from 5 → 3
  - **Files**: `portal/models.py` (modify)
  - **Details**: In `UploadFile.Status` TextChoices class (currently at line 56–61):
    - Remove: `PROCESSED = "processed", "Processed"` (line 59)
    - Remove: `DELETED = "deleted", "Deleted"` (line 61)
    - Result: Only `UPLOADING`, `STORED`, `FAILED` remain
    - Update class docstring (currently line 48–54): Change lifecycle from `uploading → stored → processed / deleted` to `uploading → stored` or `uploading → failed`
    - Keep **all existing fields unchanged**: `file` (FileField), `sha256`, `size_bytes`, `original_filename`, `content_type`, `uploaded_by`, `batch`, `error_message`, `metadata`, `status`. Keep all existing indexes unchanged.
  - **Verify**: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && python -c "from portal.models import UploadFile; assert set(UploadFile.Status.values) == {'uploading', 'stored', 'failed'}"`

- [ ] **Step 9**: Define PortalEventOutbox model
  - **Files**: `portal/models.py` (modify — add new model class at end of file)
  - **Details**: Add `PortalEventOutbox` class after `UploadPart`, modeled after `common.models.OutboxEvent` (lines 19–67 of `common/models.py`). Import `DjangoJSONEncoder` from `django.core.serializers.json` at the top of the file.
    ```python
    class PortalEventOutbox(TimeStampedModel):
        """Durable event queue for portal domain events.

        Uses the generic aggregate_type/aggregate_id pattern (not FK-bound)
        to support file, batch, and session-level events.

        Status lifecycle:
            pending → delivered (success)
            pending → ... retry ... → failed (max retries exhausted)
        """

        class Status(models.TextChoices):
            PENDING = "pending", "Pending"
            DELIVERED = "delivered", "Delivered"
            FAILED = "failed", "Failed"

        id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
        aggregate_type = models.CharField(max_length=100)
        aggregate_id = models.CharField(max_length=100)
        event_type = models.CharField(max_length=100)
        payload = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
        status = models.CharField(
            max_length=20, choices=Status.choices, default=Status.PENDING
        )
        idempotency_key = models.CharField(max_length=255)
        attempts = models.PositiveIntegerField(default=0)
        max_attempts = models.PositiveIntegerField(default=5)
        next_attempt_at = models.DateTimeField(null=True)
        delivered_at = models.DateTimeField(null=True, blank=True)
        error_message = models.TextField(blank=True)

        class Meta:
            db_table = "portal_event_outbox"
            verbose_name = "portal event outbox"
            verbose_name_plural = "portal event outbox entries"
            ordering = ["-created_at"]
            indexes = [
                models.Index(
                    fields=["next_attempt_at"],
                    condition=models.Q(status="pending"),
                    name="idx_portal_outbox_pending_next",
                ),
            ]
            constraints = [
                models.UniqueConstraint(
                    fields=["event_type", "idempotency_key"],
                    name="unique_portal_event_type_idempotency_key",
                ),
            ]

        def __str__(self):
            return f"{self.event_type} ({self.get_status_display()})"
    ```
    Add import at top of file: `from django.core.serializers.json import DjangoJSONEncoder`
    Add import for `models.Q` — already available via `from django.db import models`.
  - **Verify**: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && python -c "from portal.models import PortalEventOutbox; print(PortalEventOutbox._meta.db_table)"`

- [ ] **Step 10**: Generate and apply migrations for status change and new model
  - **Files**: `portal/migrations/0003_*.py` (auto-generated)
  - **Details**: Run `makemigrations portal` to generate the migration for:
    1. UploadFile status choices change (5 → 3)
    2. New PortalEventOutbox model
    Then apply with `migrate`.
  - **Verify**: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py makemigrations portal && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py migrate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py migrate --check`

### Phase C: Service and Task Updates

- [ ] **Step 11**: Update service functions for status simplification
  - **Files**: `portal/services/uploads.py` (modify)
  - **Details**:
    1. **Remove `mark_file_processed()` function** (lines 149–177): Delete entirely — PROCESSED status no longer exists
    2. **Remove `mark_file_deleted()` function** (lines 197–212): Delete entirely — DELETED status no longer exists
    3. **Update `finalize_batch()`** (line 258): Change `success_statuses = {UploadFile.Status.STORED, UploadFile.Status.PROCESSED}` to `success_statuses = {UploadFile.Status.STORED}`. Update docstring to remove "or PROCESSED" references.
    4. **Update module docstring**: Change `"""Upload services for file validation, creation, and status transitions."""` to `"""Portal upload services for file validation, creation, and status transitions."""`
    5. Keep all other functions unchanged: `validate_file`, `compute_sha256`, `create_upload_file`, `mark_file_failed`, `create_batch`, `notify_expiring_files`
    6. Remove `import contextlib` (line 3) — only used by the deleted `mark_file_deleted` function
  - **Verify**: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && cd /home/rjusher/doorito && ruff check portal/services/uploads.py`

- [ ] **Step 12**: Update session services module docstring
  - **Files**: `portal/services/sessions.py` (modify)
  - **Details**: Update module docstring from `"""Upload session services for chunked upload lifecycle management."""` to `"""Portal session services for chunked upload lifecycle management."""`. No other changes needed — all function signatures and logic remain the same.
  - **Verify**: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && cd /home/rjusher/doorito && ruff check portal/services/sessions.py`

- [ ] **Step 13**: Update task module docstring
  - **Files**: `portal/tasks.py` (modify)
  - **Details**: Update module docstring from `"""Celery tasks for the portal app."""` (already updated in Step 5) — verify it was changed. No other task logic changes needed.
  - **Verify**: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && cd /home/rjusher/doorito && ruff check portal/tasks.py`

### Phase D: Admin Update

- [ ] **Step 14**: Add PortalEventOutboxAdmin to `portal/admin.py`
  - **Files**: `portal/admin.py` (modify)
  - **Details**:
    1. Update import line to include `PortalEventOutbox`: `from portal.models import UploadBatch, UploadFile, UploadPart, UploadSession, PortalEventOutbox`
    2. Add new admin class modeled after `common/admin.py:OutboxEventAdmin` (lines 9–49):
       ```python
       @admin.register(PortalEventOutbox)
       class PortalEventOutboxAdmin(admin.ModelAdmin):
           """Admin interface for portal event outbox."""

           list_display = (
               "event_type",
               "aggregate_type",
               "aggregate_id",
               "status",
               "attempts",
               "next_attempt_at",
               "created_at",
           )
           list_filter = ("status", "event_type", "aggregate_type", "created_at")
           search_fields = (
               "event_type",
               "aggregate_type",
               "aggregate_id",
               "idempotency_key",
           )
           readonly_fields = (
               "pk",
               "aggregate_type",
               "aggregate_id",
               "event_type",
               "payload",
               "idempotency_key",
               "attempts",
               "delivered_at",
               "error_message",
               "created_at",
               "updated_at",
           )
           date_hierarchy = "created_at"
       ```
    3. Update module docstring: `"""Admin configuration for upload models."""` → `"""Admin configuration for portal models."""`
  - **Verify**: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check`

### Phase E: Test Updates

- [ ] **Step 15**: Update test imports and assertions for app rename and status simplification
  - **Files** (5 test files to modify):
    1. **`portal/tests/test_models.py`**:
       - Line 9: `from uploads.models import ...` → `from portal.models import ...`
       - Lines 219–225: In `test_status_choices`, change `assert set(UploadFile.Status.values) == {"uploading", "stored", "processed", "failed", "deleted"}` to `assert set(UploadFile.Status.values) == {"uploading", "stored", "failed"}`
    2. **`portal/tests/test_services.py`**:
       - Lines 13–14: `from uploads.models import ...` → `from portal.models import ...`; `from uploads.services.uploads import ...` → `from portal.services.uploads import ...`
       - Lines 19–21: Remove `mark_file_deleted` and `mark_file_processed` from the import list
       - Lines 129–152: Delete entire `TestMarkFileProcessed` class (tests the removed function)
       - Lines 170–183: Delete entire `TestMarkFileDeleted` class (tests the removed function)
       - Lines 322–326: In `test_skips_non_stored_files`, change `upload.status = UploadFile.Status.PROCESSED` to `upload.status = UploadFile.Status.FAILED`
    3. **`portal/tests/test_sessions.py`**:
       - Line 6: `from uploads.models import ...` → `from portal.models import ...`
       - Lines 7–11: `from uploads.services.sessions import ...` → `from portal.services.sessions import ...`
    4. **`portal/tests/test_tasks.py`**:
       - Line 9: `from uploads.models import UploadFile` → `from portal.models import UploadFile`
       - Line 10: `from uploads.tasks import cleanup_expired_upload_files_task` → `from portal.tasks import cleanup_expired_upload_files_task`
       - Line 86: `from uploads import tasks` → `from portal import tasks`
    5. **`frontend/tests/test_views_upload.py`**:
       - Line 6: `from uploads.models import UploadBatch, UploadFile` → `from portal.models import UploadBatch, UploadFile`
  - **Verify**: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py test`

### Phase F: New Tests for PortalEventOutbox

- [ ] **Step 16**: Add PortalEventOutbox model tests
  - **Files**: `portal/tests/test_models.py` (modify — add new test classes)
  - **Details**: Add these test classes to the existing test file:
    1. **`TestPortalEventOutboxUUID7PK`**: Create a `PortalEventOutbox` instance, verify `pk` is `uuid.UUID` with `version == 7`
    2. **`TestPortalEventOutboxStatusChoices`**: Assert `PortalEventOutbox.Status.values == {"pending", "delivered", "failed"}`
    3. **`TestPortalEventOutboxUniqueConstraint`**: Create an outbox entry with `event_type="file.stored"`, `idempotency_key="key1"`, then attempt a second with the same `(event_type, idempotency_key)` — assert `IntegrityError` is raised
    4. **`TestPortalEventOutboxDefaults`**: Create an entry, verify `status == "pending"`, `attempts == 0`, `max_attempts == 5`, `payload == {}`, `delivered_at is None`, `error_message == ""`
    5. **`TestPortalEventOutboxStr`**: Verify `str(entry) == f"{entry.event_type} (Pending)"` for a PENDING entry
    Add import for `PortalEventOutbox` to the existing imports from `portal.models`.
  - **Verify**: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py test portal.tests.test_models`

- [ ] **Step 17**: Add admin registration test for PortalEventOutbox
  - **Files**: `portal/tests/test_models.py` (modify — add test)
  - **Details**: Add a test that verifies all 5 portal models are registered in the admin site:
    ```python
    @pytest.mark.django_db
    class TestAdminRegistration:
        def test_all_portal_models_registered(self):
            from django.contrib.admin.sites import site
            from portal.models import (
                PortalEventOutbox,
                UploadBatch,
                UploadFile,
                UploadPart,
                UploadSession,
            )
            for model in [UploadBatch, UploadFile, UploadSession, UploadPart, PortalEventOutbox]:
                assert model in site._registry, f"{model.__name__} not registered in admin"
    ```
  - **Verify**: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py test portal.tests.test_models`

## Testing

All tests should pass after completing Phase E and F:

- [ ] Unit tests for all existing model constraints survive the rename (UUID v7 PKs, CASCADE rules, unique constraint on `(session, part_number)`)
- [ ] Unique constraint on `(session, part_number)` is still enforced (existing `TestConstraints.test_unique_session_part_number`)
- [ ] UploadFile status choices are exactly `{uploading, stored, failed}` (updated assertion in `test_status_choices`)
- [ ] PortalEventOutbox creation with all required fields (new `TestPortalEventOutboxDefaults`)
- [ ] PortalEventOutbox unique constraint on `(event_type, idempotency_key)` (new `TestPortalEventOutboxUniqueConstraint`)
- [ ] `finalize_batch()` works with only STORED as success status (existing `TestFinalizeBatch` tests)
- [ ] `create_upload_file()` still emits outbox events with `aggregate_type="UploadFile"` (existing `TestCreateUploadFileOutboxEvent`)
- [ ] Admin registration for all 5 portal models (new `TestAdminRegistration`)
- [ ] Frontend upload view works end-to-end (existing `TestUploadViewPost`, `TestUploadViewHtmx`)

## Rollback Plan

All steps are reversible:

1. **Reverse model changes**: Revert `portal/models.py` to restore PROCESSED/DELETED statuses and remove `PortalEventOutbox`
2. **Reverse migrations**: `DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py migrate portal 0001_initial` (reverts 0002 and 0003)
3. **Reverse app rename**: `git mv portal uploads`, restore `uploads/apps.py` (`UploadsConfig`, `name="uploads"`), restore `"uploads"` in `boot/settings.py` INSTALLED_APPS, restore all `from uploads.*` imports, restore `uploads.tasks.*` task names
4. **Reverse django_migrations**: Manually run `UPDATE django_migrations SET app='uploads' WHERE app='portal'; UPDATE django_content_type SET app_label='uploads' WHERE app_label='portal';` (these were applied via Step 6a pre-migration, not via the migration file). Also restore FK references in `0001_initial.py` back to `uploads.*`

For a full rollback: `git checkout HEAD -- uploads/ portal/ boot/settings.py frontend/ conftest.py` (assuming changes are committed) or `git stash` (if uncommitted).

## aikb Impact Map

- [ ] `aikb/models.md` — Update "Uploads App" section: change `db_table` values to `portal_upload_*`, simplify UploadFile status choices (remove PROCESSED/DELETED from Status Choices and lifecycle), add `PortalEventOutbox` model documentation with all fields/indexes/constraints. Update Entity Relationship Summary to show `PortalEventOutbox (standalone, no FKs)`.
- [ ] `aikb/services.md` — Update "Uploads App" header to "Portal App", change file paths from `uploads/services/*` to `portal/services/*`, remove `mark_file_processed()` and `mark_file_deleted()` function documentation, update `finalize_batch()` to reference only STORED (not PROCESSED). Update `create_upload_file()` to note that `aggregate_type` remains `"UploadFile"`.
- [ ] `aikb/tasks.md` — Update "Uploads App" header to "Portal App", change file path from `uploads/tasks.py` to `portal/tasks.py`, update task name paths from `uploads.tasks.*` to `portal.tasks.*`, update Current Schedule table with new task paths.
- [ ] `aikb/signals.md` — N/A (no signals added or modified)
- [ ] `aikb/admin.md` — Update `uploads/admin.py` references to `portal/admin.py`, add `PortalEventOutboxAdmin` documentation following the existing OutboxEventAdmin pattern. Update "Models visible" list to include `PortalEventOutbox`.
- [ ] `aikb/cli.md` — N/A (no CLI commands added or modified)
- [ ] `aikb/architecture.md` — Rename "uploads" entry in the app structure table to "portal" with updated description: `portal/ | Batched, chunked file upload infrastructure + portal event outbox`. Update file tree to show `portal/` instead of `uploads/`. Update Background Processing section to reference `portal.tasks.*`.
- [ ] `aikb/conventions.md` — N/A (no new patterns introduced; existing patterns followed)
- [ ] `aikb/dependencies.md` — N/A (no new dependencies added)
- [ ] `aikb/specs-roadmap.md` — Update "File upload infrastructure (uploads)" to "File upload infrastructure + portal event outbox (portal)" in the What's Ready table
- [ ] `CLAUDE.md` — Update Django App Structure table: rename `uploads` row to `portal` with updated description. Update `INSTALLED_APPS` references. Update Celery task paths from `uploads.tasks.*` to `portal.tasks.*`.

## Final Verification

### Acceptance Criteria

- [ ] **AC1: Unique constraint on (session, part_number) enforced at DB level**
  - Verify: existing test `portal/tests/test_models.py::TestConstraints::test_unique_session_part_number` passes
  - Command: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py test portal.tests.test_models.TestConstraints`

- [ ] **AC2: File cannot be marked STORED without required metadata (sha256, size_bytes, file stored)**
  - Verify: existing test `portal/tests/test_services.py::TestCreateUploadFile::test_valid_upload_creates_stored_record` confirms STORED files have sha256, size_bytes, and file
  - Command: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py test portal.tests.test_services.TestCreateUploadFile`

- [ ] **AC3: PortalEventOutbox entries for file aggregates cannot be created unless the referenced file is STORED**
  - Verify: existing test `portal/tests/test_services.py::TestCreateUploadFileOutboxEvent::test_failed_file_does_not_emit_outbox_event` confirms no outbox event for FAILED files
  - Command: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py test portal.tests.test_services.TestCreateUploadFileOutboxEvent`

- [ ] **AC4: All models inherit from TimeStampedModel and use uuid7 primary keys**
  - Verify: existing `TestUUIDv7PrimaryKeys` tests all 4 upload models; new `TestPortalEventOutboxUUID7PK` tests the 5th model
  - Command: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py test portal.tests.test_models.TestUUIDv7PrimaryKeys portal.tests.test_models.TestPortalEventOutboxUUID7PK`

- [ ] **AC5: Database migrations are generated and apply cleanly**
  - Command: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py migrate --check`

- [ ] **AC6: `python manage.py check` passes**
  - Command: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check`

### Integration Checks

- [ ] **Full model creation workflow**: Create batch → create file → create session → create parts → mark stored
  - Verify: existing `portal/tests/test_sessions.py::TestCompleteUploadSession::test_all_parts_received_completes` exercises this entire workflow
  - Command: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py test portal.tests.test_sessions.TestCompleteUploadSession`

- [ ] **App rename integrity**: `showmigrations` shows correct portal migration history
  - Command: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py showmigrations portal`
  - Expected: 3 migrations (0001_initial, 0002_rename_app, 0003_*) all marked `[X]`

- [ ] **No orphaned uploads references**: No `uploads.models` or `uploads.services` imports remain outside of migrations and PEPs
  - Command: `grep -r "from uploads\.\|import uploads\." --include="*.py" . | grep -v ".pyc" | grep -v "migrations/" | grep -v "PEPs/" | grep -v "__pycache__"`
  - Expected: zero results

- [ ] **Frontend upload view works**: Upload view creates files and batches via the portal app
  - Command: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py test frontend.tests.test_views_upload`

- [ ] **Outbox events still emitted**: `create_upload_file()` emits `file.stored` events with `aggregate_type="UploadFile"`
  - Command: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py test portal.tests.test_services.TestCreateUploadFileOutboxEvent`

### Regression Checks

- [ ] **Django system check passes**
  - Command: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check`

- [ ] **No unapplied migrations**
  - Command: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py migrate --check`

- [ ] **Ruff passes**
  - Command: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && cd /home/rjusher/doorito && ruff check .`

- [ ] **All tests pass**
  - Command: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py test`

## Detailed Todo List

### Phase 1: Pre-Implementation Setup

- [ ] Read all context files listed in the Context Files table above
- [ ] Read `PEPs/PEP_0008_canonical_domain_model/discussions.md` for resolved design decisions
- [ ] Read `PEPs/PEP_0008_canonical_domain_model/research.md` for risk analysis and migration strategy
- [ ] Verify prerequisites:
  - [ ] Database accessible (SQLite in Dev)
  - [ ] Virtual environment activates successfully
  - [ ] All existing tests pass: `DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py test`
  - [ ] No unapplied migrations: `DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py migrate --check`
  - [ ] Ruff passes: `ruff check .`
- [ ] Clean up orphaned database records from previous attempt (see Prerequisites section)
- [ ] Create a clean git branch for the PEP work

### Phase 2: App Rename — Directory and Configuration (Steps 1–3)

- [ ] **2.1** Physically rename `uploads/` → `portal/` using `git mv uploads portal` (Step 1)
- [ ] **2.2** Verify all expected files exist under `portal/`: `models.py`, `admin.py`, `apps.py`, `tasks.py`, `services/uploads.py`, `services/sessions.py`, `migrations/0001_initial.py`, all test files
- [ ] **2.3** Update FK references in `portal/migrations/0001_initial.py` (Step 1a):
  - [ ] `to="uploads.uploadbatch"` → `to="portal.uploadbatch"` (line 124)
  - [ ] `to="uploads.uploadfile"` → `to="portal.uploadfile"` (line 213)
  - [ ] `to="uploads.uploadsession"` → `to="portal.uploadsession"` (line 286)
  - [ ] Verify: `grep -n 'to="uploads\.' portal/migrations/0001_initial.py` → zero results
- [ ] **2.4** Update `portal/apps.py` (Step 2):
  - [ ] Rename class `UploadsConfig` → `PortalConfig`
  - [ ] Change `name = "uploads"` → `name = "portal"`
  - [ ] Change `verbose_name = "Uploads"` → `verbose_name = "Portal"`
  - [ ] Update module docstring
- [ ] **2.5** Verify app config: `python -c "from portal.apps import PortalConfig; assert PortalConfig.name == 'portal'"`
- [ ] **2.6** Update `boot/settings.py` (Step 3):
  - [ ] Change `"uploads"` → `"portal"` in `INSTALLED_APPS`
  - [ ] Change task path `"uploads.tasks.cleanup_expired_upload_files_task"` → `"portal.tasks.cleanup_expired_upload_files_task"` in `CELERY_BEAT_SCHEDULE`
  - [ ] Change task path `"uploads.tasks.notify_expiring_files_task"` → `"portal.tasks.notify_expiring_files_task"` in `CELERY_BEAT_SCHEDULE`
- [ ] **2.7** Verify settings: `python -c "from boot.settings import Base; apps = Base.INSTALLED_APPS; assert 'portal' in apps and 'uploads' not in apps"`

### Phase 3: App Rename — Import Updates (Steps 4–5)

- [ ] **3.1** Update imports in `portal/admin.py`: `from uploads.models` → `from portal.models` (Step 4)
- [ ] **3.2** Update imports in `portal/services/uploads.py`: `from uploads.models` → `from portal.models` (Step 4)
- [ ] **3.3** Update imports in `portal/services/sessions.py`: `from uploads.models` → `from portal.models` (Step 4)
- [ ] **3.4** Update imports in `portal/tasks.py` (Steps 4 and 5):
  - [ ] `from uploads.models` → `from portal.models` (lazy import inside task)
  - [ ] `from uploads.services.uploads` → `from portal.services.uploads` (lazy import inside task)
  - [ ] Update task `name=` strings from `"uploads.tasks.*"` to `"portal.tasks.*"`
  - [ ] Update module docstring to reference "portal app"
- [ ] **3.5** Update imports in `frontend/views/upload.py` (Step 4):
  - [ ] `from uploads.models` → `from portal.models`
  - [ ] `from uploads.services.uploads` → `from portal.services.uploads`
- [ ] **3.6** Verify no orphaned `from uploads.` imports remain (excluding migrations and PEPs):
  `grep -r "from uploads\." --include="*.py" . | grep -v ".pyc" | grep -v "migrations/" | grep -v "PEPs/" | grep -v "__pycache__"` → zero results

### Phase 4: App Rename — Migration and Table Renames (Steps 6a–6b)

- [ ] **4.1** Run pre-migration SQL to update `django_migrations` and `django_content_type` (Step 6a):
  - [ ] `UPDATE django_migrations SET app = 'portal' WHERE app = 'uploads'`
  - [ ] `UPDATE django_content_type SET app_label = 'portal' WHERE app_label = 'uploads'`
  - [ ] Verify: `python manage.py showmigrations portal` → shows `[X] 0001_initial`
- [ ] **4.2** Update `db_table` values in `portal/models.py` (Step 6b):
  - [ ] `UploadBatch.Meta.db_table`: `"upload_batch"` → `"portal_upload_batch"`
  - [ ] `UploadFile.Meta.db_table`: `"upload_file"` → `"portal_upload_file"`
  - [ ] `UploadSession.Meta.db_table`: `"upload_session"` → `"portal_upload_session"`
  - [ ] `UploadPart.Meta.db_table`: `"upload_part"` → `"portal_upload_part"`
- [ ] **4.3** Create manual migration `portal/migrations/0002_rename_app.py` with `RunSQL` operations for:
  - [ ] Rename all four tables (`ALTER TABLE upload_* RENAME TO portal_upload_*`)
  - [ ] Include reverse SQL for all table renames
  - [ ] (Note: `django_migrations` and `django_content_type` updates are handled in 4.1, NOT in the migration)
- [ ] **4.4** Apply migration: `python manage.py migrate`
- [ ] **4.5** Verify migration applied: `python manage.py showmigrations portal` — shows `0001_initial` and `0002_rename_app` both `[X]`

### Phase 5: App Rename — Verification (Step 7)

- [ ] **5.1** `python manage.py check` passes with no errors
- [ ] **5.2** Confirm no orphaned `uploads.*` imports outside migrations/PEPs
- [ ] **5.3** `ruff check .` passes
- [ ] **5.4** Commit the app rename as a standalone commit (clean checkpoint before model changes)

### Phase 6: Model Changes — Status Simplification (Step 8)

- [ ] **6.1** In `portal/models.py`, remove `PROCESSED = "processed", "Processed"` from `UploadFile.Status` TextChoices
- [ ] **6.2** In `portal/models.py`, remove `DELETED = "deleted", "Deleted"` from `UploadFile.Status` TextChoices
- [ ] **6.3** Update `UploadFile` class docstring to reflect simplified lifecycle (`uploading → stored` or `uploading → failed`)
- [ ] **6.4** Verify status choices: `python -c "from portal.models import UploadFile; assert set(UploadFile.Status.values) == {'uploading', 'stored', 'failed'}"`

### Phase 7: Model Changes — PortalEventOutbox (Step 9)

- [ ] **7.1** Add `from django.core.serializers.json import DjangoJSONEncoder` import to top of `portal/models.py`
- [ ] **7.2** Add `PortalEventOutbox` model class after `UploadPart` in `portal/models.py` with:
  - [ ] `Status` TextChoices: PENDING, DELIVERED, FAILED
  - [ ] `id` field: UUID PK with `default=uuid7`
  - [ ] `aggregate_type` and `aggregate_id` CharFields (generic aggregate pattern)
  - [ ] `event_type` CharField
  - [ ] `payload` JSONField with `DjangoJSONEncoder`
  - [ ] `status` CharField with Status choices, default PENDING
  - [ ] `idempotency_key` CharField
  - [ ] `attempts` and `max_attempts` PositiveIntegerFields
  - [ ] `next_attempt_at` DateTimeField (nullable)
  - [ ] `delivered_at` DateTimeField (nullable)
  - [ ] `error_message` TextField (blank)
- [ ] **7.3** Add `Meta` class with:
  - [ ] `db_table = "portal_event_outbox"`
  - [ ] `ordering = ["-created_at"]`
  - [ ] Partial index `idx_portal_outbox_pending_next` on `next_attempt_at` where `status="pending"`
  - [ ] Unique constraint `unique_portal_event_type_idempotency_key` on `(event_type, idempotency_key)`
- [ ] **7.4** Add `__str__` method returning `f"{self.event_type} ({self.get_status_display()})"`
- [ ] **7.5** Verify model imports: `python -c "from portal.models import PortalEventOutbox; print(PortalEventOutbox._meta.db_table)"`

### Phase 8: Model Changes — Migration (Step 10)

- [ ] **8.1** Generate migration: `python manage.py makemigrations portal`
- [ ] **8.2** Verify the generated migration covers both the status choices change and the new PortalEventOutbox model
- [ ] **8.3** Apply migration: `python manage.py migrate`
- [ ] **8.4** Verify no unapplied migrations: `python manage.py migrate --check`

### Phase 9: Service and Task Updates (Steps 11–13)

- [ ] **9.1** In `portal/services/uploads.py`, remove the `mark_file_processed()` function entirely (Step 11)
- [ ] **9.2** In `portal/services/uploads.py`, remove the `mark_file_deleted()` function entirely (Step 11)
- [ ] **9.3** In `portal/services/uploads.py`, update `finalize_batch()`: change `success_statuses` from `{UploadFile.Status.STORED, UploadFile.Status.PROCESSED}` to `{UploadFile.Status.STORED}` (Step 11)
- [ ] **9.4** In `portal/services/uploads.py`, update `finalize_batch()` docstring to remove "or PROCESSED" references (Step 11)
- [ ] **9.5** In `portal/services/uploads.py`, remove `import contextlib` if only used by deleted functions (Step 11)
- [ ] **9.6** Update module docstring of `portal/services/uploads.py` to reference "Portal" (Step 11)
- [ ] **9.7** Update module docstring of `portal/services/sessions.py` to reference "Portal" (Step 12)
- [ ] **9.8** Verify `portal/tasks.py` docstring was updated in Phase 3 (Step 13)
- [ ] **9.9** Run `ruff check portal/services/ portal/tasks.py` — all pass

### Phase 10: Admin Update (Step 14)

- [ ] **10.1** Add `PortalEventOutbox` to the import line in `portal/admin.py`
- [ ] **10.2** Add `PortalEventOutboxAdmin` class with `@admin.register(PortalEventOutbox)` decorator:
  - [ ] `list_display`: event_type, aggregate_type, aggregate_id, status, attempts, next_attempt_at, created_at
  - [ ] `list_filter`: status, event_type, aggregate_type, created_at
  - [ ] `search_fields`: event_type, aggregate_type, aggregate_id, idempotency_key
  - [ ] `readonly_fields`: pk, aggregate_type, aggregate_id, event_type, payload, idempotency_key, attempts, delivered_at, error_message, created_at, updated_at
  - [ ] `date_hierarchy = "created_at"`
- [ ] **10.3** Update `portal/admin.py` module docstring to reference "portal models"
- [ ] **10.4** Verify: `python manage.py check` passes

### Phase 11: Test Updates — Existing Tests (Step 15)

- [ ] **11.1** Update `portal/tests/test_models.py`:
  - [ ] Change `from uploads.models import ...` → `from portal.models import ...`
  - [ ] In `test_status_choices`, update expected values from `{"uploading", "stored", "processed", "failed", "deleted"}` to `{"uploading", "stored", "failed"}`
- [ ] **11.2** Update `portal/tests/test_services.py`:
  - [ ] Change `from uploads.models import ...` → `from portal.models import ...`
  - [ ] Change `from uploads.services.uploads import ...` → `from portal.services.uploads import ...`
  - [ ] Remove `mark_file_deleted` and `mark_file_processed` from imports
  - [ ] Delete entire `TestMarkFileProcessed` class
  - [ ] Delete entire `TestMarkFileDeleted` class
  - [ ] In `test_skips_non_stored_files`, change `UploadFile.Status.PROCESSED` to `UploadFile.Status.FAILED`
- [ ] **11.3** Update `portal/tests/test_sessions.py`:
  - [ ] Change `from uploads.models import ...` → `from portal.models import ...`
  - [ ] Change `from uploads.services.sessions import ...` → `from portal.services.sessions import ...`
- [ ] **11.4** Update `portal/tests/test_tasks.py`:
  - [ ] Change `from uploads.models import UploadFile` → `from portal.models import UploadFile`
  - [ ] Change `from uploads.tasks import ...` → `from portal.tasks import ...`
  - [ ] Change `from uploads import tasks` → `from portal import tasks`
- [ ] **11.5** Update `frontend/tests/test_views_upload.py`:
  - [ ] Change `from uploads.models import UploadBatch, UploadFile` → `from portal.models import UploadBatch, UploadFile`
- [ ] **11.6** Run all tests: `python manage.py test` — all pass

### Phase 12: New Tests — PortalEventOutbox (Steps 16–17)

- [ ] **12.1** Add `PortalEventOutbox` to imports in `portal/tests/test_models.py`
- [ ] **12.2** Add `TestPortalEventOutboxUUID7PK`: create instance, verify `pk` is `uuid.UUID` with `version == 7`
- [ ] **12.3** Add `TestPortalEventOutboxStatusChoices`: assert `set(PortalEventOutbox.Status.values) == {"pending", "delivered", "failed"}`
- [ ] **12.4** Add `TestPortalEventOutboxUniqueConstraint`: create entry with `(event_type, idempotency_key)`, create duplicate → assert `IntegrityError`
- [ ] **12.5** Add `TestPortalEventOutboxDefaults`: verify `status == "pending"`, `attempts == 0`, `max_attempts == 5`, `payload == {}`, `delivered_at is None`, `error_message == ""`
- [ ] **12.6** Add `TestPortalEventOutboxStr`: verify `str(entry)` format matches `f"{entry.event_type} (Pending)"`
- [ ] **12.7** Add `TestAdminRegistration`: verify all 5 portal models are registered in `admin.site._registry`
- [ ] **12.8** Run model tests: `python manage.py test portal.tests.test_models` — all pass

### Phase 13: Full Verification

- [ ] **13.1** Run full test suite: `python manage.py test` — all pass
- [ ] **13.2** Run `python manage.py check` — no issues
- [ ] **13.3** Run `python manage.py migrate --check` — no unapplied migrations
- [ ] **13.4** Run `python manage.py showmigrations portal` — all 3 migrations `[X]`
- [ ] **13.5** Run `ruff check .` — passes
- [ ] **13.6** Verify no orphaned `uploads.*` imports: `grep -r "from uploads\.\|import uploads\." --include="*.py" . | grep -v ".pyc" | grep -v "migrations/" | grep -v "PEPs/" | grep -v "__pycache__"` → zero results
- [ ] **13.7** Run acceptance criteria commands (AC1–AC6 from Final Verification section)
- [ ] **13.8** Run integration checks (from Final Verification section)
- [ ] **13.9** Run regression checks (from Final Verification section)

### Phase 14: aikb Documentation Updates

- [ ] **14.1** Update `aikb/models.md` — change `db_table` values to `portal_upload_*`, simplify UploadFile status choices (remove PROCESSED/DELETED), add `PortalEventOutbox` model documentation
- [ ] **14.2** Update `aikb/services.md` — rename "Uploads App" header to "Portal App", update file paths `uploads/services/*` → `portal/services/*`, remove `mark_file_processed()` and `mark_file_deleted()` docs, update `finalize_batch()` to reference only STORED
- [ ] **14.3** Update `aikb/tasks.md` — rename header to "Portal App", update file path and task name paths from `uploads.tasks.*` to `portal.tasks.*`
- [ ] **14.4** Update `aikb/admin.md` — update file path references, add `PortalEventOutboxAdmin` documentation
- [ ] **14.5** Update `aikb/architecture.md` — rename "uploads" to "portal" in app structure table and file tree, update task path references
- [ ] **14.6** Update `aikb/specs-roadmap.md` — update "File upload infrastructure (uploads)" entry to reference portal app
- [ ] **14.7** Update `CLAUDE.md` — update Django App Structure table (uploads → portal), update `INSTALLED_APPS` references, update Celery task paths

### Phase 15: Finalization

- [ ] **15.1** Commit all implementation changes
- [ ] **15.2** Update `PEPs/IMPLEMENTED/LATEST.md` with PEP 0008 entry (number, title, commit hash, summary)
- [ ] **15.3** Update `PEPs/INDEX.md` — remove the PEP 0008 row
- [ ] **15.4** Remove PEP directory `PEPs/PEP_0008_canonical_domain_model/`
- [ ] **15.5** Final commit for PEP finalization

## Completion

- [ ] **Update `PEPs/IMPLEMENTED/LATEST.md`** — Add entry with PEP number, title, commit hash(es), and summary
- [ ] **Update `PEPs/INDEX.md`** — Remove the PEP 0008 row
- [ ] **Remove PEP directory** — Delete `PEPs/PEP_0008_canonical_domain_model/`
