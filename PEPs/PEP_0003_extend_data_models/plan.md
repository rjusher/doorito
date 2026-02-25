# PEP 0003: Extend Data Models — Implementation Plan

| Field | Value |
|-------|-------|
| **PEP** | 0003 |
| **Summary** | [summary.md](summary.md) |
| **Research** | [research.md](research.md) |
| **Discussions** | [discussions.md](discussions.md) |
| **Estimated Effort** | M |

---

## Resolved Design Decisions

Before implementation, these decisions from [discussions.md](discussions.md) are resolved in this plan:

**Q1 — TimeStampedModel vs explicit timestamps**: **Use `TimeStampedModel`** for all 5 models. This is consistent with the project convention in `aikb/models.md` ("All future models should inherit from TimeStampedModel"). Models needing additional timestamp fields (`PortalEventOutbox.delivered_at`) add them alongside inherited `created_at`/`updated_at`. This reduces boilerplate and maintains consistency.

**Q2 — Existing services, tasks, and tests**: **Delete them**. The existing `uploads/services/uploads.py`, `uploads/tasks.py`, and `uploads/tests/` are tightly coupled to `FileField` and the old status lifecycle (`pending/ready/consumed/failed`). They cannot be incrementally adapted. New model-level tests will be written; service and task logic will be rebuilt in a future PEP.

**Q3 — PEP 0002 dependency**: **Require PEP 0002 completion first**. PEP 0002's code-level renames (admin, services, tasks, tests, aikb) must be done before PEP 0003 starts. The PEP 0002 database migration is moot (since PEP 0003 drops the table), but the code renames ensure a clean starting point with consistent `IngestFile` naming everywhere.

---

## Context Files

Read these files before starting implementation:

| File | Reason |
|------|--------|
| `PEPs/PEP_0003_extend_data_models/summary.md` | Acceptance criteria, model field definitions, ER diagram, out-of-scope boundaries |
| `PEPs/PEP_0003_extend_data_models/research.md` | Current state analysis, technical constraints (UUID PKs, JSONField, cascade rules), pattern analysis, risk assessment |
| `PEPs/PEP_0003_extend_data_models/discussions.md` | Resolved design decisions (TimeStampedModel, services/tasks fate, PEP 0002 dependency) |
| `uploads/models.py` | Current `IngestFile` model (58 lines) — being replaced. Study `Status` inner class pattern, `Meta` options, `__str__` pattern |
| `uploads/admin.py` | Current `IngestFileAdmin` (32 lines) — being replaced with 5 admin classes |
| `uploads/services/uploads.py` | Current services (133 lines) — `validate_file`, `create_ingest_file`, `consume_ingest_file` — being deleted |
| `uploads/tasks.py` | Current `cleanup_expired_ingest_files_task` (67 lines) — being deleted |
| `uploads/tests/test_services.py` | Current 10 service tests (145 lines) — being deleted |
| `uploads/tests/test_tasks.py` | Current 5 task tests (104 lines) — being deleted and replaced with model tests |
| `uploads/apps.py` | `UploadsConfig` with `default_auto_field = "django.db.models.BigAutoField"` — UUID models need explicit `id` field |
| `uploads/migrations/0001_initial.py` | Current migration (84 lines) — being deleted and regenerated |
| `common/models.py` | `TimeStampedModel` abstract base (14 lines) — base class for all new models |
| `common/fields.py` | `MoneyField` example (26 lines) — pattern reference for custom field `deconstruct()` |
| `accounts/models.py` | `User` model (16 lines) — FK target for `uploaded_by` and `created_by` fields |
| `boot/settings.py` | Settings: `DEFAULT_AUTO_FIELD` (L144), `FILE_UPLOAD_*` settings (L139-141), `AUTH_USER_MODEL` (L77), Celery serializer (L129) |
| `conftest.py` | Shared `user` fixture (16 lines) — reused by new model tests |
| `aikb/models.md` | Current model documentation — must be rewritten for 5 models |
| `aikb/admin.md` | Current admin documentation — must be rewritten for 5 admin classes |
| `aikb/services.md` | Current service documentation — must be updated (services deleted) |
| `aikb/tasks.md` | Current task documentation — must be updated (task deleted) |
| `aikb/conventions.md` | Coding patterns: `TextChoices`, `db_table`, `__str__`, service layer, task patterns |
| `aikb/architecture.md` | App structure tree — must be updated |

## Prerequisites

- [ ] **PEP 0002 is fully implemented** — All code renames (model, admin, services, tasks, tests, aikb) are complete. The PEP 0002 database migration is NOT required (it's moot since PEP 0003 drops the table).
  - Verify: `grep -rn "FileUpload\|FileUploadAdmin\|create_upload\|consume_upload\|cleanup_expired_uploads" --include="*.py" uploads/ | grep -v migrations/` (expect 0 results)
- [ ] **Clean working tree in `uploads/`** — No uncommitted changes
  - Verify: `git status uploads/`
- [ ] **Database is migrated** — Current migrations are applied
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py showmigrations uploads`
- [ ] **All existing tests pass** before any changes
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev pytest uploads/tests/ -v`

## Implementation Steps

### Step 1: Rewrite `uploads/models.py` with 5 models

- [ ] **Step 1**: Replace the single `IngestFile` model with 5 new models in `uploads/models.py`
  - Files: `uploads/models.py` — complete rewrite (existing: 58 lines → new: ~230 lines)
  - Details:
    - **Imports**: Replace existing imports with:
      ```python
      import uuid
      from common.models import TimeStampedModel
      from django.conf import settings
      from django.db import models
      ```
    - **Module docstring**: `"""Data models for file upload, chunked sessions, and event outbox."""`
    - **Model 1: `UploadBatch(TimeStampedModel)`**
      - `id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)`
      - Inner `class Status(models.TextChoices)`: `INIT`, `IN_PROGRESS`, `COMPLETE`, `PARTIAL`, `FAILED`
      - `created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="upload_batches")`
      - `status = models.CharField(max_length=20, choices=Status.choices, default=Status.INIT)`
      - `total_files = models.PositiveIntegerField(default=0)`
      - `stored_files = models.PositiveIntegerField(default=0)`
      - `failed_files = models.PositiveIntegerField(default=0)`
      - `idempotency_key = models.CharField(max_length=255, unique=True, blank=True, null=True)`
      - `Meta`: `db_table = "upload_batch"`, `verbose_name = "upload batch"`, `verbose_name_plural = "upload batches"`, `ordering = ["-created_at"]`
      - `__str__`: `f"Batch {self.id} ({self.get_status_display()})"`
    - **Model 2: `IngestFile(TimeStampedModel)`** — complete redesign
      - `id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)`
      - Inner `class Status(models.TextChoices)`: `UPLOADING`, `STORED`, `FAILED`, `DELETED`
      - `batch = models.ForeignKey("UploadBatch", null=True, blank=True, on_delete=models.SET_NULL, related_name="files")`
      - `uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="ingest_files")`
      - `original_filename = models.CharField(max_length=255)`
      - `content_type = models.CharField(max_length=100)`
      - `size_bytes = models.PositiveBigIntegerField(help_text="File size in bytes")`
      - `sha256 = models.CharField(max_length=64, blank=True, help_text="SHA-256 content hash")`
      - `storage_backend = models.CharField(max_length=20, default="local")`
      - `storage_bucket = models.CharField(max_length=255, blank=True)`
      - `storage_key = models.CharField(max_length=500, blank=True)`
      - `metadata = models.JSONField(default=dict, blank=True)`
      - `status = models.CharField(max_length=20, choices=Status.choices, default=Status.UPLOADING)`
      - `Meta`: `db_table = "ingest_file"`, `verbose_name = "ingest file"`, `verbose_name_plural = "ingest files"`, `ordering = ["-created_at"]`, indexes on `["uploaded_by", "-created_at"]`, `["status"]`, and `["sha256"]`
      - `__str__`: `f"{self.original_filename} ({self.get_status_display()})"`
    - **Model 3: `UploadSession(TimeStampedModel)`**
      - `id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)`
      - Inner `class Status(models.TextChoices)`: `INIT`, `IN_PROGRESS`, `COMPLETE`, `FAILED`, `ABORTED`
      - `file = models.OneToOneField("IngestFile", on_delete=models.CASCADE, related_name="session")`
      - `status = models.CharField(max_length=20, choices=Status.choices, default=Status.INIT)`
      - `chunk_size_bytes = models.PositiveIntegerField(default=5_242_880, help_text="Target chunk size in bytes (default 5 MB)")`
      - `total_size_bytes = models.PositiveBigIntegerField(help_text="Total file size contract")`
      - `total_parts = models.PositiveIntegerField(help_text="Expected number of parts")`
      - `bytes_received = models.PositiveBigIntegerField(default=0)`
      - `completed_parts = models.PositiveIntegerField(default=0)`
      - `idempotency_key = models.CharField(max_length=255, unique=True, blank=True, null=True)`
      - `upload_token = models.CharField(max_length=255, unique=True, blank=True, null=True)`
      - `Meta`: `db_table = "upload_session"`, `verbose_name = "upload session"`, `verbose_name_plural = "upload sessions"`, `ordering = ["-created_at"]`
      - `__str__`: `f"Session {self.id} ({self.get_status_display()})"`
    - **Model 4: `UploadPart(TimeStampedModel)`**
      - `id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)`
      - Inner `class Status(models.TextChoices)`: `PENDING`, `RECEIVED`, `FAILED`
      - `session = models.ForeignKey("UploadSession", on_delete=models.CASCADE, related_name="parts")`
      - `part_number = models.PositiveIntegerField()`
      - `offset_bytes = models.PositiveBigIntegerField()`
      - `size_bytes = models.PositiveBigIntegerField()`
      - `sha256 = models.CharField(max_length=64, blank=True)`
      - `status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)`
      - `temp_storage_key = models.CharField(max_length=500, blank=True)`
      - `Meta`: `db_table = "upload_part"`, `verbose_name = "upload part"`, `verbose_name_plural = "upload parts"`, `ordering = ["part_number"]`, `constraints = [UniqueConstraint(fields=["session", "part_number"], name="unique_session_part")]`
      - `__str__`: `f"Part {self.part_number} of {self.session_id}"`
    - **Model 5: `PortalEventOutbox(TimeStampedModel)`**
      - `id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)`
      - Inner `class Status(models.TextChoices)`: `PENDING`, `SENDING`, `DELIVERED`, `FAILED`
      - `event_type = models.CharField(max_length=100)`
      - `idempotency_key = models.CharField(max_length=255)`
      - `file = models.ForeignKey("IngestFile", on_delete=models.CASCADE, related_name="outbox_events")`
      - `payload = models.JSONField(default=dict)`
      - `status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)`
      - `attempts = models.PositiveIntegerField(default=0)`
      - `next_attempt_at = models.DateTimeField(null=True, blank=True)`
      - `delivered_at = models.DateTimeField(null=True, blank=True)`
      - `Meta`: `db_table = "portal_event_outbox"`, `verbose_name = "portal event outbox"`, `verbose_name_plural = "portal event outbox entries"`, `ordering = ["-created_at"]`, `constraints = [UniqueConstraint(fields=["event_type", "idempotency_key"], name="unique_event_idempotency")]`
      - `__str__`: `f"{self.event_type} ({self.get_status_display()})"`
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from uploads.models import UploadBatch, IngestFile, UploadSession, UploadPart, PortalEventOutbox; print('All 5 models imported OK')"` && `grep -c "class.*TimeStampedModel" uploads/models.py` (expect 5)

### Step 2: Delete existing migrations

- [ ] **Step 2**: Delete all existing migration files and regenerate from scratch
  - Files: `uploads/migrations/0001_initial.py` — delete
  - Details:
    - Delete `uploads/migrations/0001_initial.py`. There is no production data, so a clean slate is safe.
    - If PEP 0002 created `uploads/migrations/0002_*.py`, delete that too.
    - Keep `uploads/migrations/__init__.py`.
  - Verify: `ls uploads/migrations/*.py` (expect only `__init__.py`)

### Step 3: Generate and apply fresh migration

- [ ] **Step 3**: Run `makemigrations` to generate a clean initial migration for all 5 models, then apply it
  - Files: `uploads/migrations/0001_initial.py` — new file (auto-generated)
  - Details:
    - Run `makemigrations uploads` — Django should generate a single `0001_initial.py` with `CreateModel` operations for all 5 models.
    - Inspect the generated migration to confirm:
      - All 5 `CreateModel` operations are present (`UploadBatch`, `IngestFile`, `UploadSession`, `UploadPart`, `PortalEventOutbox`)
      - UUID primary key fields are `UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)`
      - FK dependencies are in the correct order (UploadBatch before IngestFile, IngestFile before UploadSession and PortalEventOutbox, UploadSession before UploadPart)
      - `UniqueConstraint` entries are present for `UploadPart` and `PortalEventOutbox`
      - `JSONField(default=dict)` is used (not `default={}`)
    - Drop the old `ingest_file` table before migrating (since we deleted the old migration): `python manage.py dbshell -- -c "DROP TABLE IF EXISTS ingest_file CASCADE;"`
    - Run `migrate uploads` to apply.
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py showmigrations uploads` (expect `[X] 0001_initial`) && `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py dbshell -- -c "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename IN ('upload_batch','ingest_file','upload_session','upload_part','portal_event_outbox') ORDER BY tablename;"` (expect all 5 tables)

### Step 4: Rewrite admin classes

- [ ] **Step 4**: Replace the single `IngestFileAdmin` with 5 admin classes in `uploads/admin.py`
  - Files: `uploads/admin.py` — complete rewrite (existing: 32 lines → new: ~100 lines)
  - Details:
    - **Module docstring**: `"""Admin configuration for upload models."""`
    - **Imports**: `from uploads.models import IngestFile, PortalEventOutbox, UploadBatch, UploadPart, UploadSession`
    - **`UploadBatchAdmin`**:
      - `list_display = ("id", "created_by", "status", "total_files", "stored_files", "failed_files", "created_at")`
      - `list_filter = ("status", "created_at")`
      - `search_fields = ("id", "created_by__email", "created_by__username", "idempotency_key")`
      - `readonly_fields = ("id", "total_files", "stored_files", "failed_files", "created_at", "updated_at")`
      - `list_select_related = ("created_by",)`
      - `date_hierarchy = "created_at"`
    - **`IngestFileAdmin`** (redesigned):
      - `list_display = ("original_filename", "uploaded_by", "content_type", "size_bytes", "status", "storage_backend", "created_at")`
      - `list_filter = ("status", "storage_backend", "content_type", "created_at")`
      - `search_fields = ("original_filename", "uploaded_by__email", "uploaded_by__username", "sha256", "storage_key")`
      - `readonly_fields = ("id", "sha256", "size_bytes", "content_type", "storage_backend", "storage_bucket", "storage_key", "metadata", "created_at", "updated_at")`
      - `list_select_related = ("uploaded_by", "batch")`
      - `date_hierarchy = "created_at"`
    - **`UploadSessionAdmin`**:
      - `list_display = ("id", "file", "status", "completed_parts", "total_parts", "bytes_received", "total_size_bytes", "created_at")`
      - `list_filter = ("status", "created_at")`
      - `search_fields = ("id", "idempotency_key", "upload_token")`
      - `readonly_fields = ("id", "bytes_received", "completed_parts", "created_at", "updated_at")`
      - `list_select_related = ("file",)`
      - `date_hierarchy = "created_at"`
    - **`UploadPartAdmin`**:
      - `list_display = ("id", "session", "part_number", "size_bytes", "status", "created_at")`
      - `list_filter = ("status",)`
      - `search_fields = ("id", "session__id")`
      - `readonly_fields = ("id", "created_at", "updated_at")`
      - `list_select_related = ("session",)`
    - **`PortalEventOutboxAdmin`**:
      - `list_display = ("id", "event_type", "file", "status", "attempts", "next_attempt_at", "delivered_at", "created_at")`
      - `list_filter = ("status", "event_type", "created_at")`
      - `search_fields = ("id", "event_type", "idempotency_key")`
      - `readonly_fields = ("id", "payload", "attempts", "delivered_at", "created_at", "updated_at")`
      - `list_select_related = ("file",)`
      - `date_hierarchy = "created_at"`
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from django.contrib import admin; from uploads.models import UploadBatch, IngestFile, UploadSession, UploadPart, PortalEventOutbox; print('UploadBatch:', admin.site.is_registered(UploadBatch)); print('IngestFile:', admin.site.is_registered(IngestFile)); print('UploadSession:', admin.site.is_registered(UploadSession)); print('UploadPart:', admin.site.is_registered(UploadPart)); print('PortalEventOutbox:', admin.site.is_registered(PortalEventOutbox))"` (expect all `True`)

### Step 5: Delete existing services

- [ ] **Step 5**: Remove the existing service functions that depend on `FileField` and the old status lifecycle
  - Files:
    - `uploads/services/uploads.py` — delete file
    - `uploads/services/__init__.py` — keep (empty module, preserves directory structure for future services)
  - Details:
    - Delete `uploads/services/uploads.py` entirely. The three functions (`validate_file`, `create_ingest_file`, `consume_ingest_file`) are tightly coupled to `FileField`, `SimpleUploadedFile`, and the old `pending/ready/consumed/failed` status lifecycle. They cannot be adapted to the new model shape.
    - Keep `uploads/services/__init__.py` to preserve the `services/` package structure for future PEPs that will rebuild the service layer for the new models.
  - Verify: `ls uploads/services/` (expect only `__init__.py`) && `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "import uploads.services; print('services package OK')"` (should import without error)

### Step 6: Delete existing task

- [ ] **Step 6**: Remove the `cleanup_expired_ingest_files_task` that depends on `FileField`
  - Files: `uploads/tasks.py` — delete file
  - Details:
    - Delete `uploads/tasks.py` entirely. The `cleanup_expired_ingest_files_task` calls `upload.file.delete(save=False)` which requires Django's `FileField` — this method doesn't exist on the redesigned model with abstract storage pointers.
    - The task concept (TTL-based cleanup) remains valid, but the implementation must be rebuilt once the storage backend service layer is defined in a future PEP.
    - The `FILE_UPLOAD_TTL_HOURS` setting in `boot/settings.py` is **not deleted** — it will be used by the future cleanup task.
  - Verify: `test ! -f uploads/tasks.py && echo "tasks.py deleted"` && `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check` (should pass — Celery autodiscovery gracefully handles missing `tasks.py`)

### Step 7: Delete existing tests and write model tests

- [ ] **Step 7a**: Delete existing tests that depend on `FileField` and old services
  - Files:
    - `uploads/tests/test_services.py` — delete file
    - `uploads/tests/test_tasks.py` — delete file
  - Details:
    - All 10 service tests and 5 task tests depend on `SimpleUploadedFile`, `FileField`, old status values (`READY`, `CONSUMED`), and deleted service/task functions. They cannot be adapted.
  - Verify: `ls uploads/tests/` (expect only `__init__.py` and `test_models.py` after Step 7b)

- [ ] **Step 7b**: Write model tests in `uploads/tests/test_models.py`
  - Files: `uploads/tests/test_models.py` — new file (~180 lines)
  - Details:
    - **Module docstring**: `"""Unit tests for upload data models."""`
    - **Imports**: `uuid`, `pytest`, `from django.db import IntegrityError`, `from uploads.models import UploadBatch, IngestFile, UploadSession, UploadPart, PortalEventOutbox`
    - **Test class `TestUploadBatch`** (`@pytest.mark.django_db`):
      - `test_create_batch` — create batch with `created_by=user`, verify UUID PK, default `status=INIT`, default counters are 0
      - `test_batch_user_set_null` — create batch, delete user, verify `batch.created_by is None` (SET_NULL)
      - `test_idempotency_key_unique` — create two batches with same `idempotency_key`, expect `IntegrityError`
    - **Test class `TestIngestFile`** (`@pytest.mark.django_db`):
      - `test_create_file` — create file with required fields, verify UUID PK, default `status=UPLOADING`, `metadata={}`, `storage_backend="local"`
      - `test_file_user_set_null` — create file, delete user, verify `file.uploaded_by is None` (SET_NULL)
      - `test_file_batch_set_null` — create file with batch, delete batch, verify `file.batch is None` (SET_NULL)
      - `test_sha256_index_lookup` — create file with `sha256` value, verify query by `sha256` returns correct file
      - `test_json_metadata` — create file with `metadata={"xml_root": "Invoice"}`, verify round-trip
    - **Test class `TestUploadSession`** (`@pytest.mark.django_db`):
      - `test_create_session` — create session linked to file, verify default `status=INIT`, counters are 0
      - `test_session_cascade_on_file_delete` — create session, delete file, verify session is deleted
      - `test_one_to_one_constraint` — create two sessions for same file, expect `IntegrityError`
    - **Test class `TestUploadPart`** (`@pytest.mark.django_db`):
      - `test_create_part` — create part with all required fields, verify default `status=PENDING`
      - `test_unique_session_part_number` — create two parts with same `(session, part_number)`, expect `IntegrityError`
      - `test_parts_cascade_on_session_delete` — create parts, delete session, verify parts are deleted
    - **Test class `TestPortalEventOutbox`** (`@pytest.mark.django_db`):
      - `test_create_event` — create event with required fields, verify defaults
      - `test_unique_event_idempotency` — create two events with same `(event_type, idempotency_key)`, expect `IntegrityError`
      - `test_event_cascade_on_file_delete` — create event, delete file, verify event is deleted
    - Use the existing `user` fixture from `conftest.py` for FK tests.
    - Helper function or fixture `make_ingest_file(uploaded_by=None, **kwargs)` for creating `IngestFile` instances with minimal required fields.
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev pytest uploads/tests/test_models.py -v`

### Step 8: Add chunk size setting

- [ ] **Step 8**: Add `FILE_UPLOAD_CHUNK_SIZE` setting to `boot/settings.py`
  - Files: `boot/settings.py` — modify existing file (add 1 line after L141)
  - Details:
    - Add `FILE_UPLOAD_CHUNK_SIZE = 5_242_880  # 5 MB default chunk size` after `FILE_UPLOAD_ALLOWED_TYPES` on L141, within the `Base` class.
    - This provides a central configuration point for the default chunk size used by `UploadSession.chunk_size_bytes`. The model field's `default=5_242_880` matches this setting.
  - Verify: `grep -n "FILE_UPLOAD_CHUNK_SIZE" boot/settings.py` (expect 1 result)

### Step 9: Run system checks and lint

- [ ] **Step 9**: Verify the full system passes Django checks and linting
  - Files: none (validation only)
  - Details:
    - Run `python manage.py check` — verify no errors or warnings
    - Run `ruff check .` — verify no lint errors (import ordering, unused imports after deletions)
    - Run `ruff format --check .` — verify formatting
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check && ruff check . && ruff format --check .`

### Step 10: Update `aikb/models.md`

- [ ] **Step 10**: Rewrite the Uploads App section of `aikb/models.md` to document all 5 models
  - Files: `aikb/models.md` — modify existing file
  - Details:
    - **Replace the entire `## Uploads App` section** (L24-66) with documentation for all 5 models:
      - `### UploadBatch (TimeStampedModel)` — fields, status choices, Meta, `__str__`
      - `### IngestFile (TimeStampedModel)` — redesigned fields, new status choices (`uploading/stored/failed/deleted`), storage pointer fields, JSONField, indexes
      - `### UploadSession (TimeStampedModel)` — fields, status choices, OneToOne to IngestFile
      - `### UploadPart (TimeStampedModel)` — fields, status choices, UniqueConstraint
      - `### PortalEventOutbox (TimeStampedModel)` — fields, status choices, `delivered_at`, UniqueConstraint
    - **Replace the `## Entity Relationship Summary`** (L58-65) with the full ER diagram from the summary:
      ```
      User
        ├── UploadBatch (via created_by FK, SET_NULL)
        │     └── IngestFile (via batch FK, SET_NULL)
        │           ├── UploadSession (1:1, CASCADE)
        │           │     └── UploadPart (via session FK, CASCADE)
        │           └── PortalEventOutbox (via file FK, CASCADE)
        └── IngestFile (via uploaded_by FK, SET_NULL)
      ```
    - **Keep the closing note** about `TimeStampedModel` and `MoneyField` (L67) — this convention is still correct since all new models use `TimeStampedModel`.
  - Verify: `grep -c "UploadBatch\|IngestFile\|UploadSession\|UploadPart\|PortalEventOutbox" aikb/models.md` (expect multiple results for each model)

### Step 11: Update `aikb/admin.md`

- [ ] **Step 11**: Rewrite the `uploads/admin.py` section to document all 5 admin classes
  - Files: `aikb/admin.md` — modify existing file
  - Details:
    - **Replace the `### uploads/admin.py` section** (L23-36) with documentation for 5 admin classes: `UploadBatchAdmin`, `IngestFileAdmin`, `UploadSessionAdmin`, `UploadPartAdmin`, `PortalEventOutboxAdmin`.
    - Document key admin options for each class: `list_display`, `list_filter`, `list_select_related`, `date_hierarchy`.
    - **Update the `## Access` section** (L20) to note that 6 models are visible in admin (User + 5 upload models).
  - Verify: `grep -c "UploadBatchAdmin\|IngestFileAdmin\|UploadSessionAdmin\|UploadPartAdmin\|PortalEventOutboxAdmin" aikb/admin.md` (expect 5)

### Step 12: Update `aikb/services.md`

- [ ] **Step 12**: Update the Uploads App section to reflect that services have been deleted
  - Files: `aikb/services.md` — modify existing file
  - Details:
    - **Replace the `## Uploads App` section** (L36-58) with a note:
      ```
      ## Uploads App

      The uploads app service layer was removed as part of PEP 0003 (Extend Data Models).
      The previous services (`validate_file`, `create_ingest_file`, `consume_ingest_file`)
      were tightly coupled to Django's `FileField` and the old status lifecycle. New services
      for the redesigned models (abstract storage pointers, chunked uploads, event outbox)
      will be defined in a future PEP.

      The `uploads/services/` package directory is preserved for future use.
      ```
    - **Update the `## Current State` section** (L36-37) to note the package exists but is empty.
  - Verify: `grep -c "validate_file\|create_ingest_file\|consume_ingest_file\|create_upload\|consume_upload" aikb/services.md` (expect 0 — old function names should not appear as current API)

### Step 13: Update `aikb/tasks.md`

- [ ] **Step 13**: Update the Uploads App section to reflect that the task has been deleted
  - Files: `aikb/tasks.md` — modify existing file
  - Details:
    - **Replace the `## Uploads App` section** (L46-62) and the `## Current State` paragraph (L44-46) with a note:
      ```
      ## Current State

      No tasks are currently defined. The previous `cleanup_expired_ingest_files_task` was
      removed as part of PEP 0003 (Extend Data Models) because it depended on Django's
      `FileField` which was replaced with abstract storage pointers. A new cleanup task
      will be defined in a future PEP alongside the storage backend service layer.

      Celery autodiscovery (`boot/celery.py`) automatically discovers `tasks.py` in all
      `INSTALLED_APPS`. When adding tasks to a new app, create `{app}/tasks.py` and follow
      the conventions below.
      ```
    - Keep the `## Task Conventions` section (L64-101) and `## Running Celery` section (L103-112) unchanged — they document patterns for future tasks.
  - Verify: `grep -c "cleanup_expired" aikb/tasks.md` (expect 0)

### Step 14: Update `aikb/architecture.md`

- [ ] **Step 14**: Update the app structure tree and background processing section
  - Files: `aikb/architecture.md` — modify existing file
  - Details:
    - **Update the uploads section of the app tree** (L63-69):
      ```
      ├── uploads/        # File upload infrastructure
      │   ├── models.py       # UploadBatch, IngestFile, UploadSession, UploadPart, PortalEventOutbox
      │   ├── admin.py        # Admin classes for all 5 upload models
      │   ├── services/       # (empty — service layer to be defined in future PEP)
      │   ├── tests/          # test_models.py
      │   └── migrations/     # 0001_initial.py
      ```
    - Note: `tasks.py` is removed from the tree since it no longer exists.
    - **Update the Background Processing section** (L129-135):
      ```
      ## Background Processing

      See [tasks.md](tasks.md) for details.

      - **Celery** with PostgreSQL broker via SQLAlchemy transport (no Redis)
      - **Tasks**: None currently defined. Upload cleanup task was removed in PEP 0003; will be rebuilt with storage backend services.
      - **Dev mode**: `CELERY_TASK_ALWAYS_EAGER=True` (synchronous, no broker needed)
      ```
    - **Update the Storage section** (L117-127): Note that the `IngestFile` model now uses abstract storage pointers (`storage_backend`, `storage_bucket`, `storage_key`) instead of Django's `FileField`. The `media/uploads/` directory is no longer used by the model. Physical file storage is deferred to a future PEP.
  - Verify: `grep "UploadBatch" aikb/architecture.md && grep -c "cleanup_expired" aikb/architecture.md` (expect UploadBatch found, 0 cleanup references)

### Step 15: Update `CLAUDE.md`

- [ ] **Step 15**: Update `CLAUDE.md` to reflect the new model landscape and removed task
  - Files: `CLAUDE.md` — modify existing file
  - Details:
    - **Update the `### Django App Structure` table** (Uploads row): Change description from "File upload model, services, admin, cleanup task" to "Upload models (5), admin, services (empty — to be rebuilt)"
    - **Update `### Celery (Background Tasks)` section** (L249): Remove the reference to `cleanup_expired_uploads_task`. Change to: "Tasks defined: None currently. The upload cleanup task was removed in PEP 0003; it will be rebuilt with the storage backend service layer."
    - **Update `### File Upload Settings`** in the Architecture section: Add `FILE_UPLOAD_CHUNK_SIZE` to the settings table with description "Default chunk size in bytes (default: 5,242,880 = 5 MB)"
  - Verify: `grep -c "cleanup_expired" CLAUDE.md` (expect 0) && `grep "FILE_UPLOAD_CHUNK_SIZE" CLAUDE.md` (expect 1 result)

## Testing

- [ ] **All new model tests pass** — 15+ tests covering model creation, FK cascades, unique constraints, and JSONField round-trips
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev pytest uploads/tests/ -v`
- [ ] **No broken imports in the uploads app** — all modules importable
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from uploads import models, admin; import uploads.services; print('All imports OK')"`
- [ ] **Old service/task test files are deleted** — no test files reference deleted code
  - Verify: `ls uploads/tests/` (expect `__init__.py` and `test_models.py` only)

## Rollback Plan

1. **Revert all code changes**: `git checkout -- uploads/ aikb/ CLAUDE.md boot/settings.py conftest.py`
2. **Restore old migration**: The old `0001_initial.py` will be restored by git checkout.
3. **Drop new tables and recreate old table**:
   ```bash
   source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py dbshell -- -c "
     DROP TABLE IF EXISTS upload_part CASCADE;
     DROP TABLE IF EXISTS portal_event_outbox CASCADE;
     DROP TABLE IF EXISTS upload_session CASCADE;
     DROP TABLE IF EXISTS ingest_file CASCADE;
     DROP TABLE IF EXISTS upload_batch CASCADE;
   "
   ```
4. **Re-apply old migration**: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py migrate uploads`
5. **Verify rollback**: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check && pytest uploads/tests/ -v`

No feature flags needed. No data migration needed (no production data). Rollback is straightforward because there are no downstream consumers of the new models yet.

## aikb Impact Map

- [ ] `aikb/models.md` — Complete rewrite of §Uploads App: document all 5 models (UploadBatch, IngestFile, UploadSession, UploadPart, PortalEventOutbox) with fields, status choices, relationships, indexes, constraints. Rewrite §Entity Relationship Summary with full ER diagram.
- [ ] `aikb/admin.md` — Rewrite §uploads/admin.py: document 5 admin classes with their `list_display`, `list_filter`, `list_select_related`, `date_hierarchy` options. Update §Access to note 6 registered models.
- [ ] `aikb/services.md` — Update §Uploads App and §Current State: note services were removed in PEP 0003, package directory preserved for future PEP. Remove documentation of deleted functions.
- [ ] `aikb/tasks.md` — Update §Current State and remove §Uploads App: note task was removed in PEP 0003 due to `FileField` removal. Keep §Task Conventions and §Running Celery sections unchanged.
- [ ] `aikb/architecture.md` — Update app structure tree (L63-69): list 5 models, remove `tasks.py`, note empty services. Update §Background Processing (L129-135): remove task reference. Update §Storage (L117-127): note abstract storage pointers replace `FileField`.
- [ ] `aikb/signals.md` — N/A (no signals added or removed in this PEP)
- [ ] `aikb/cli.md` — N/A (no CLI changes in this PEP)
- [ ] `aikb/conventions.md` — N/A (all new models follow existing conventions: `TimeStampedModel`, `TextChoices`, `db_table`, `__str__`)
- [ ] `aikb/dependencies.md` — N/A (no new dependencies added)
- [ ] `aikb/specs-roadmap.md` — N/A (roadmap references "File upload infrastructure" which is the app concept, not specific models)
- [ ] `CLAUDE.md` — Update §Django App Structure table (uploads row), §Celery (Background Tasks) (remove task reference), §File Upload Settings (add `FILE_UPLOAD_CHUNK_SIZE`)

## Detailed Todo List

### Phase 1: Prerequisites & Setup

- [ ] Verify PEP 0002 is fully implemented (all code renames: model, admin, services, tasks, tests, aikb)
  - Run: `grep -rn "FileUpload\|FileUploadAdmin\|create_upload\|consume_upload\|cleanup_expired_uploads" --include="*.py" uploads/ | grep -v migrations/` → expect 0 results
- [ ] Verify clean working tree in `uploads/`
  - Run: `git status uploads/`
- [ ] Verify database is migrated to current state
  - Run: `python manage.py showmigrations uploads` → all checked
- [ ] Run existing test suite to confirm green baseline
  - Run: `pytest uploads/tests/ -v` → all pass

### Phase 2: Rewrite Models (Step 1)

- [ ] Replace `uploads/models.py` with 5 new model classes
  - [ ] Add imports: `uuid`, `TimeStampedModel`, `settings`, `models`
  - [ ] Add module docstring
  - [ ] Write `UploadBatch(TimeStampedModel)` — UUID PK, Status choices (INIT/IN_PROGRESS/COMPLETE/PARTIAL/FAILED), `created_by` FK (SET_NULL), counters, `idempotency_key`, Meta, `__str__`
  - [ ] Write `IngestFile(TimeStampedModel)` — UUID PK, Status choices (UPLOADING/STORED/FAILED/DELETED), `batch` FK (SET_NULL), `uploaded_by` FK (SET_NULL), file metadata fields, storage pointer fields, `metadata` JSONField, Meta with 3 indexes, `__str__`
  - [ ] Write `UploadSession(TimeStampedModel)` — UUID PK, Status choices (INIT/IN_PROGRESS/COMPLETE/FAILED/ABORTED), OneToOne to IngestFile (CASCADE), chunking fields, progress counters, `idempotency_key`, `upload_token`, Meta, `__str__`
  - [ ] Write `UploadPart(TimeStampedModel)` — UUID PK, Status choices (PENDING/RECEIVED/FAILED), FK to UploadSession (CASCADE), `part_number`, byte range fields, `sha256`, `temp_storage_key`, Meta with UniqueConstraint, `__str__`
  - [ ] Write `PortalEventOutbox(TimeStampedModel)` — UUID PK, Status choices (PENDING/SENDING/DELIVERED/FAILED), `event_type`, `idempotency_key`, FK to IngestFile (CASCADE), `payload` JSONField, retry fields, `delivered_at`, Meta with UniqueConstraint, `__str__`
- [ ] Verify all 5 models import correctly
  - Run: `python -c "from uploads.models import UploadBatch, IngestFile, UploadSession, UploadPart, PortalEventOutbox; print('OK')"` → OK
- [ ] Verify all 5 classes inherit from TimeStampedModel
  - Run: `grep -c "class.*TimeStampedModel" uploads/models.py` → 5

### Phase 3: Migration Reset (Steps 2–3)

- [ ] Delete `uploads/migrations/0001_initial.py` (and any `0002_*.py` from PEP 0002)
- [ ] Verify only `__init__.py` remains in `uploads/migrations/`
  - Run: `ls uploads/migrations/*.py` → only `__init__.py`
- [ ] Run `makemigrations uploads` to generate fresh `0001_initial.py`
- [ ] Inspect generated migration for correctness:
  - [ ] All 5 `CreateModel` operations present
  - [ ] UUID PKs use `default=uuid.uuid4, editable=False`
  - [ ] FK dependency ordering is correct (UploadBatch → IngestFile → UploadSession/PortalEventOutbox → UploadPart)
  - [ ] UniqueConstraints present for UploadPart and PortalEventOutbox
  - [ ] JSONField uses `default=dict` (not `default={}`)
- [ ] Drop old `ingest_file` table: `python manage.py dbshell -- -c "DROP TABLE IF EXISTS ingest_file CASCADE;"`
- [ ] Apply migration: `python manage.py migrate uploads`
- [ ] Verify all 5 tables exist in database
  - Run: `python manage.py dbshell -- -c "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename IN ('upload_batch','ingest_file','upload_session','upload_part','portal_event_outbox') ORDER BY tablename;"` → 5 rows

### Phase 4: Rewrite Admin (Step 4)

- [ ] Replace `uploads/admin.py` with 5 admin classes
  - [ ] Write `UploadBatchAdmin` — list_display, list_filter, search_fields, readonly_fields, list_select_related, date_hierarchy
  - [ ] Write `IngestFileAdmin` (redesigned) — list_display, list_filter, search_fields, readonly_fields, list_select_related, date_hierarchy
  - [ ] Write `UploadSessionAdmin` — list_display, list_filter, search_fields, readonly_fields, list_select_related, date_hierarchy
  - [ ] Write `UploadPartAdmin` — list_display, list_filter, search_fields, readonly_fields, list_select_related
  - [ ] Write `PortalEventOutboxAdmin` — list_display, list_filter, search_fields, readonly_fields, list_select_related, date_hierarchy
- [ ] Verify all 5 admin classes are registered
  - Run: `python -c "from django.contrib import admin; from uploads.models import *; assert all(admin.site.is_registered(m) for m in [UploadBatch, IngestFile, UploadSession, UploadPart, PortalEventOutbox]); print('OK')"` → OK

### Phase 5: Remove Old Code (Steps 5–6)

- [ ] Delete `uploads/services/uploads.py`
- [ ] Verify `uploads/services/__init__.py` still exists (preserves package)
  - Run: `ls uploads/services/` → only `__init__.py`
- [ ] Verify services package imports cleanly
  - Run: `python -c "import uploads.services; print('OK')"` → OK
- [ ] Delete `uploads/tasks.py`
- [ ] Verify `uploads/tasks.py` no longer exists
  - Run: `test ! -f uploads/tasks.py && echo "deleted"` → deleted
- [ ] Verify `python manage.py check` passes (Celery autodiscovery handles missing tasks.py gracefully)

### Phase 6: Tests (Step 7)

- [ ] Delete `uploads/tests/test_services.py`
- [ ] Delete `uploads/tests/test_tasks.py`
- [ ] Verify only `__init__.py` remains in `uploads/tests/` (before writing new tests)
- [ ] Create `uploads/tests/test_models.py` with model tests:
  - [ ] Write helper fixture `make_ingest_file` for creating IngestFile with minimal required fields
  - [ ] Write `TestUploadBatch` — `test_create_batch`, `test_batch_user_set_null`, `test_idempotency_key_unique`
  - [ ] Write `TestIngestFile` — `test_create_file`, `test_file_user_set_null`, `test_file_batch_set_null`, `test_sha256_index_lookup`, `test_json_metadata`
  - [ ] Write `TestUploadSession` — `test_create_session`, `test_session_cascade_on_file_delete`, `test_one_to_one_constraint`
  - [ ] Write `TestUploadPart` — `test_create_part`, `test_unique_session_part_number`, `test_parts_cascade_on_session_delete`
  - [ ] Write `TestPortalEventOutbox` — `test_create_event`, `test_unique_event_idempotency`, `test_event_cascade_on_file_delete`
- [ ] Run model tests and verify all pass
  - Run: `pytest uploads/tests/test_models.py -v` → 15+ tests pass

### Phase 7: Settings (Step 8)

- [ ] Add `FILE_UPLOAD_CHUNK_SIZE = 5_242_880` to `Base` class in `boot/settings.py` (after `FILE_UPLOAD_ALLOWED_TYPES`)
- [ ] Verify setting exists
  - Run: `grep -n "FILE_UPLOAD_CHUNK_SIZE" boot/settings.py` → 1 result

### Phase 8: Quality Checks (Step 9)

- [ ] Run `python manage.py check` — no errors or warnings
- [ ] Run `ruff check .` — no lint errors
- [ ] Run `ruff format --check .` — formatting clean

### Phase 9: Documentation Updates (Steps 10–15)

- [ ] **aikb/models.md** (Step 10): Rewrite §Uploads App with all 5 models, rewrite §Entity Relationship Summary with full ER diagram
  - Verify: `grep -c "UploadBatch\|UploadSession\|UploadPart\|PortalEventOutbox" aikb/models.md` → multiple hits
- [ ] **aikb/admin.md** (Step 11): Rewrite §uploads/admin.py with 5 admin classes, update §Access to note 6 registered models
  - Verify: `grep -c "UploadBatchAdmin\|UploadSessionAdmin\|UploadPartAdmin\|PortalEventOutboxAdmin" aikb/admin.md` → 4
- [ ] **aikb/services.md** (Step 12): Replace §Uploads App with note that services were removed in PEP 0003
  - Verify: `grep -c "validate_file\|create_ingest_file\|consume_ingest_file" aikb/services.md` → 0
- [ ] **aikb/tasks.md** (Step 13): Replace §Current State and §Uploads App with note that task was removed in PEP 0003, keep §Task Conventions and §Running Celery
  - Verify: `grep -c "cleanup_expired" aikb/tasks.md` → 0
- [ ] **aikb/architecture.md** (Step 14): Update app structure tree (list 5 models, remove tasks.py, note empty services), update §Background Processing, update §Storage for abstract storage pointers
  - Verify: `grep "UploadBatch" aikb/architecture.md` → found; `grep -c "cleanup_expired" aikb/architecture.md` → 0
- [ ] **CLAUDE.md** (Step 15): Update §Django App Structure (uploads row), §Celery (remove task reference), §File Upload Settings (add `FILE_UPLOAD_CHUNK_SIZE`)
  - Verify: `grep -c "cleanup_expired" CLAUDE.md` → 0; `grep "FILE_UPLOAD_CHUNK_SIZE" CLAUDE.md` → found

### Phase 10: No Stale References

- [ ] Verify no old-name references remain in source code
  - Run: `grep -rn "FileUpload\|FileField\|file_upload\|create_upload\|consume_upload\|cleanup_expired" --include="*.py" uploads/ | grep -v migrations/ | grep -v "# PEP\|# TODO"` → 0 results
- [ ] Verify no stale references in documentation
  - Run: `grep -rn "FileUpload\|FileUploadAdmin\|create_upload\|consume_upload\|cleanup_expired_uploads\|cleanup_expired_ingest_files" aikb/ CLAUDE.md` → 0 results

## Final Verification

### Acceptance Criteria

- [ ] **5 new models exist in `uploads/models.py`** — `UploadBatch`, `IngestFile` (redesigned), `UploadSession`, `UploadPart`, `PortalEventOutbox`
  - Verify: `grep -c "class.*TimeStampedModel" uploads/models.py` (expect 5)

- [ ] **All models use UUID primary keys**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from uploads.models import UploadBatch, IngestFile, UploadSession, UploadPart, PortalEventOutbox; [print(m.__name__, m._meta.pk.get_internal_type()) for m in [UploadBatch, IngestFile, UploadSession, UploadPart, PortalEventOutbox]]"` (expect all `UUIDField`)

- [ ] **IngestFile uses abstract storage pointers instead of FileField** — fields `storage_backend`, `storage_bucket`, `storage_key` exist; no `FileField` on any model
  - Verify: `grep -c "FileField" uploads/models.py` (expect 0) && `grep "storage_backend\|storage_bucket\|storage_key" uploads/models.py` (expect 3 lines)

- [ ] **IngestFile status choices are `uploading/stored/failed/deleted`**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from uploads.models import IngestFile; print([c[0] for c in IngestFile.Status.choices])"` (expect `['uploading', 'stored', 'failed', 'deleted']`)

- [ ] **User FKs use `SET_NULL` with `null=True`** — files and batches survive user deletion
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from uploads.models import IngestFile, UploadBatch; print('IngestFile.uploaded_by on_delete:', IngestFile._meta.get_field('uploaded_by').remote_field.on_delete.__name__); print('UploadBatch.created_by on_delete:', UploadBatch._meta.get_field('created_by').remote_field.on_delete.__name__)"` (expect both `SET_NULL`)

- [ ] **UniqueConstraint on UploadPart `(session, part_number)`**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from uploads.models import UploadPart; print([c.name for c in UploadPart._meta.constraints])"` (expect `['unique_session_part']`)

- [ ] **UniqueConstraint on PortalEventOutbox `(event_type, idempotency_key)`**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from uploads.models import PortalEventOutbox; print([c.name for c in PortalEventOutbox._meta.constraints])"` (expect `['unique_event_idempotency']`)

- [ ] **Migration applies cleanly** — single `0001_initial.py` creates all 5 tables
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py showmigrations uploads` (expect `[X] 0001_initial`)

- [ ] **`python manage.py check` passes**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check`

- [ ] **All admin classes are registered**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from django.contrib import admin; from uploads.models import UploadBatch, IngestFile, UploadSession, UploadPart, PortalEventOutbox; assert all(admin.site.is_registered(m) for m in [UploadBatch, IngestFile, UploadSession, UploadPart, PortalEventOutbox]); print('All 5 admin classes registered')"` (expect success)

### Integration Checks

- [ ] **All 5 models importable from `uploads.models`**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from uploads.models import UploadBatch, IngestFile, UploadSession, UploadPart, PortalEventOutbox; print('OK')"`

- [ ] **FK cascade rules work correctly** — create a user, create a batch and file, delete user, verify SET_NULL
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "
import django; django.setup()
from accounts.models import User
from uploads.models import UploadBatch, IngestFile
u = User.objects.create_user('cascade_test', 'ct@test.com', 'pass123')
b = UploadBatch.objects.create(created_by=u)
f = IngestFile.objects.create(uploaded_by=u, batch=b, original_filename='test.txt', content_type='text/plain', size_bytes=100)
u.delete()
b.refresh_from_db(); f.refresh_from_db()
assert b.created_by is None, 'batch.created_by should be None'
assert f.uploaded_by is None, 'file.uploaded_by should be None'
print('SET_NULL cascade OK')
b.delete(); f.refresh_from_db()
assert f.batch is None, 'file.batch should be None after batch deletion'
print('Batch SET_NULL cascade OK')
f.delete()
print('All cascade rules verified')
"`

- [ ] **UUID PKs work in Django admin** — admin pages render without errors
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check --deploy 2>&1 | grep -v "WARNINGS\|does not pass\|SECURE\|HSTS\|SESSION_COOKIE\|CSRF_COOKIE\|SSL" || true` (no model/admin errors)

- [ ] **JSONField defaults work** — `default=dict` produces `{}` not `None`
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "
import django; django.setup()
from uploads.models import IngestFile
f = IngestFile(original_filename='test.txt', content_type='text/plain', size_bytes=0)
assert f.metadata == {}, f'Expected empty dict, got {f.metadata}'
print('JSONField default=dict OK')
"`

- [ ] **UniqueConstraints produce database errors on violation**
  - Verify: covered by model tests in Step 7b (`test_unique_session_part_number`, `test_unique_event_idempotency`)

- [ ] **No stale old-name references remain in source**
  - Verify: `grep -rn "FileUpload\|FileField\|file_upload\|create_upload\|consume_upload\|cleanup_expired" --include="*.py" uploads/ | grep -v migrations/ | grep -v "# PEP\|# TODO"` (expect 0 results)

### Regression Checks

- [ ] **`python manage.py check` passes**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check`

- [ ] **`ruff check .` passes**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && ruff check .`

- [ ] **`ruff format --check .` passes**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && ruff format --check .`

- [ ] **Full test suite passes** (not just uploads tests)
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev pytest -v`

- [ ] **No broken documentation references** — all `aikb/` files are internally consistent
  - Verify: `grep -rn "FileUpload\|FileUploadAdmin\|create_upload\|consume_upload\|cleanup_expired_uploads\|cleanup_expired_ingest_files" aikb/ CLAUDE.md` (expect 0 results)
