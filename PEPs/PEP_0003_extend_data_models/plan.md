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

**Q1 — TimeStampedModel vs explicit timestamps**: **Use `TimeStampedModel`** for all 4 models. Consistent with `aikb/models.md` ("All future models should inherit from TimeStampedModel"). `TimeStampedModel` is defined in `common/models.py:6-13` and provides `created_at` (auto_now_add) and `updated_at` (auto_now).

**Q2 — Existing services, tasks, and tests**: **Rewrite them**. The existing `uploads/services/uploads.py` (3 functions: `validate_file`, `create_ingest_file`, `consume_ingest_file`), `uploads/tasks.py` (`cleanup_expired_ingest_files_task`), and `uploads/tests/` (15 tests) are tightly coupled to the old status lifecycle (`pending/ready/consumed/failed`). They will be deleted and replaced.

**Q3 — PEP 0002 dependency**: **Require PEP 0002 completion first**. PEP 0002 is finalized (commit `27382c6`). The code currently uses `IngestFile` naming.

**Q4 — PEP scope: models only vs models + services**: **Include services**. All 4 models and their core services will be delivered in this PEP.

**Q5 — FileField retained**: Django's `FileField` is kept. No abstract storage pointers.

**Q6 — IngestFile → UploadFile rename**: All models use `Upload*` prefix.

**Q7 — PROCESSED status added**: Full lifecycle: `uploading → stored → processed / deleted` and `uploading → failed`.

**Q8 — No denormalized counters**: Use `batch.files.filter(status=...).count()`.

**Q9 — Event outbox deferred**: `PortalEventOutbox` removed from scope. Deferred to PEP 0004.

**Q10 — UUID v7 via uuid_utils**: Use `uuid_utils.uuid7()` for all PK defaults. **Critical implementation note**: `uuid_utils.UUID` is NOT a subclass of `uuid.UUID`. Django's `UUIDField.get_prep_value()` fails with raw `uuid_utils.UUID` objects. A wrapper function must convert to stdlib `uuid.UUID`: `uuid.UUID(bytes=uuid_utils.uuid7().bytes)`. This wrapper will be placed in `common/utils.py`.

**Q11 — Service signatures alongside models**: Each model section lists associated service functions.

---

## Context Files

Read these files before implementing any step:

| File | Why |
|------|-----|
| `common/models.py` | `TimeStampedModel` definition (lines 6-13) — base class for all 4 models |
| `common/fields.py` | `MoneyField` — reference for custom field patterns (not used in this PEP, but shows `deconstruct()` pattern) |
| `common/utils.py` | `generate_reference()`, `safe_dispatch()` — utility patterns; UUID v7 wrapper will be added here |
| `uploads/models.py` | Current `IngestFile` model (58 lines) — will be replaced entirely |
| `uploads/admin.py` | Current `IngestFileAdmin` (32 lines) — will be replaced entirely |
| `uploads/services/uploads.py` | Current services: `validate_file`, `create_ingest_file`, `consume_ingest_file` — will be replaced |
| `uploads/tasks.py` | Current `cleanup_expired_ingest_files_task` (67 lines) — will be updated for new model |
| `uploads/tests/test_services.py` | Current service tests (144 lines) — will be replaced |
| `uploads/tests/test_tasks.py` | Current task tests (103 lines) — will be replaced |
| `uploads/apps.py` | `UploadsConfig` with `default_auto_field = "django.db.models.BigAutoField"` — UUID PKs need explicit field on each model |
| `boot/settings.py` | `DEFAULT_AUTO_FIELD` (line 144), upload settings (lines 139-141), Celery JSON serializer (line 129), `AUTH_USER_MODEL` (line 77) |
| `conftest.py` | Shared `user` fixture — no changes needed, but tests will use it |
| `requirements.in` | `uuid_utils>=0.9` already present (line 24) — no dependency change needed |
| `aikb/conventions.md` | Code patterns: TextChoices, db_table, service layer, import order, naming |
| `aikb/models.md` | Model documentation — must be updated after implementation |
| `aikb/services.md` | Service layer docs — must be updated after implementation |
| `aikb/tasks.md` | Task docs — must be updated after implementation |
| `aikb/admin.md` | Admin docs — must be updated after implementation |

---

## Prerequisites

- [ ] **PEP 0002 is finalized** — Verify `uploads/models.py` contains `class IngestFile` (not `FileUpload`)
  ```bash
  grep -c "class IngestFile" uploads/models.py  # Expected: 1
  ```

- [ ] **`uuid_utils` is installed** — Already in `requirements.in` (line 24: `uuid_utils>=0.9`)
  ```bash
  source ~/.virtualenvs/inventlily-d22a143/bin/activate && python -c "import uuid_utils; print(uuid_utils.__version__)"
  # Expected: 0.14.1 or higher
  ```

- [ ] **Database is migrated to current state** — All existing migrations applied
  ```bash
  source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py showmigrations uploads
  # Expected: [X] 0001_initial, [X] 0002_rename_fileupload_ingestfile
  ```

- [ ] **No uncommitted changes in uploads/** — Clean git state for the files we'll modify
  ```bash
  git diff --name-only uploads/
  # Expected: empty (no unstaged changes)
  ```

---

## Implementation Steps

### Step 1: Add UUID v7 wrapper to common/utils.py

**Files**: `common/utils.py` (modify — add function after existing code)

**Details**: Add a `uuid7()` wrapper function that generates a UUID v7 value and returns it as a stdlib `uuid.UUID` instance. This is necessary because `uuid_utils.uuid7()` returns `uuid_utils.UUID` which is NOT an instance of `uuid.UUID` — Django's `UUIDField.get_prep_value()` calls `to_python()` which fails on `uuid_utils.UUID` objects with `AttributeError: 'uuid_utils.UUID' object has no attribute 'replace'`.

```python
# Add to common/utils.py after existing imports
import uuid
import uuid_utils as _uuid_utils

def uuid7():
    """Generate a UUID v7 (time-ordered, RFC 9562) as a stdlib uuid.UUID.

    Uses ``uuid_utils.uuid7()`` internally but converts to ``uuid.UUID``
    for compatibility with Django's ``UUIDField``.
    """
    return uuid.UUID(bytes=_uuid_utils.uuid7().bytes)
```

**Verify**:
```bash
source ~/.virtualenvs/inventlily-d22a143/bin/activate && python -c "
from common.utils import uuid7
import uuid
u = uuid7()
assert isinstance(u, uuid.UUID), f'Expected uuid.UUID, got {type(u)}'
assert u.version == 7, f'Expected version 7, got {u.version}'
print('uuid7() OK:', u)
"
```

---

### Step 2: Delete existing migrations

**Files**: `uploads/migrations/0001_initial.py` (delete), `uploads/migrations/0002_rename_fileupload_ingestfile.py` (delete)

**Details**: Since there is no production data (confirmed in summary.md "Out of Scope"), delete all existing migrations. A fresh `0001_initial.py` will be generated after writing the new models. Keep `uploads/migrations/__init__.py`.

**Verify**:
```bash
ls uploads/migrations/*.py
# Expected: only __init__.py
```

---

### Step 3: Write the 4 models in uploads/models.py

**Files**: `uploads/models.py` (rewrite — replace entire file)

**Details**: Replace the current `IngestFile` model (58 lines) with 4 new models. Each model:
- Inherits from `TimeStampedModel` (from `common/models.py:6-13`)
- Has explicit `id = models.UUIDField(primary_key=True, default=uuid7, editable=False)` — overrides `DEFAULT_AUTO_FIELD` in `boot/settings.py:144` and `uploads/apps.py:9`
- Uses `default=uuid7` where `uuid7` is the wrapper from `common/utils.py` (Step 1)
- Has `db_table`, `verbose_name`, `verbose_name_plural`, `ordering`, `__str__` per conventions in `aikb/conventions.md`
- Uses `TextChoices` for status fields (per `aikb/conventions.md` "Status fields" section)
- References `settings.AUTH_USER_MODEL` for user FKs (value: `"accounts.User"` per `boot/settings.py:77`)

**Model definitions:**

#### UploadBatch
```python
class UploadBatch(TimeStampedModel):
    class Status(models.TextChoices):
        INIT = "init", "Init"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETE = "complete", "Complete"
        PARTIAL = "partial", "Partial"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="upload_batches",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.INIT,
    )
    idempotency_key = models.CharField(
        max_length=255, blank=True, db_index=True,
    )

    class Meta:
        db_table = "upload_batch"
        verbose_name = "upload batch"
        verbose_name_plural = "upload batches"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Batch {self.pk} ({self.get_status_display()})"
```

#### UploadFile
```python
class UploadFile(TimeStampedModel):
    class Status(models.TextChoices):
        UPLOADING = "uploading", "Uploading"
        STORED = "stored", "Stored"
        PROCESSED = "processed", "Processed"
        FAILED = "failed", "Failed"
        DELETED = "deleted", "Deleted"

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    batch = models.ForeignKey(
        "UploadBatch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="files",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="upload_files",
    )
    file = models.FileField(upload_to="uploads/%Y/%m/")
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    size_bytes = models.PositiveBigIntegerField(help_text="File size in bytes")
    sha256 = models.CharField(max_length=64, blank=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.UPLOADING,
    )
    error_message = models.TextField(blank=True)

    class Meta:
        db_table = "upload_file"
        verbose_name = "upload file"
        verbose_name_plural = "upload files"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["uploaded_by", "-created_at"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.original_filename} ({self.get_status_display()})"
```

#### UploadSession
```python
class UploadSession(TimeStampedModel):
    class Status(models.TextChoices):
        INIT = "init", "Init"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETE = "complete", "Complete"
        FAILED = "failed", "Failed"
        ABORTED = "aborted", "Aborted"

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    file = models.OneToOneField(
        "UploadFile",
        on_delete=models.CASCADE,
        related_name="session",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.INIT,
    )
    chunk_size_bytes = models.PositiveIntegerField(
        default=5_242_880,
        help_text="Target chunk size in bytes (default 5 MB)",
    )
    total_size_bytes = models.PositiveBigIntegerField(
        help_text="Total expected file size in bytes",
    )
    total_parts = models.PositiveIntegerField(
        help_text="Total expected number of parts",
    )
    bytes_received = models.PositiveBigIntegerField(default=0)
    completed_parts = models.PositiveIntegerField(default=0)
    idempotency_key = models.CharField(
        max_length=255, blank=True, db_index=True,
    )
    upload_token = models.CharField(
        max_length=255, blank=True, db_index=True,
    )

    class Meta:
        db_table = "upload_session"
        verbose_name = "upload session"
        verbose_name_plural = "upload sessions"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Session {self.pk} ({self.get_status_display()})"
```

#### UploadPart
```python
class UploadPart(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RECEIVED = "received", "Received"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    session = models.ForeignKey(
        "UploadSession",
        on_delete=models.CASCADE,
        related_name="parts",
    )
    part_number = models.PositiveIntegerField(help_text="1-indexed chunk ordinal")
    offset_bytes = models.PositiveBigIntegerField(help_text="Byte offset of this part")
    size_bytes = models.PositiveBigIntegerField(help_text="Size of this part in bytes")
    sha256 = models.CharField(max_length=64, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    temp_storage_key = models.CharField(
        max_length=500,
        blank=True,
        help_text="Temporary storage location for chunk before assembly",
    )

    class Meta:
        db_table = "upload_part"
        verbose_name = "upload part"
        verbose_name_plural = "upload parts"
        ordering = ["part_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "part_number"],
                name="unique_session_part_number",
            ),
        ]

    def __str__(self):
        return f"Part {self.part_number} of session {self.session_id}"
```

**Import block at top of file:**
```python
"""Upload data models for batched, chunked file uploads."""

from common.models import TimeStampedModel
from common.utils import uuid7
from django.conf import settings
from django.db import models
```

**Verify**:
```bash
source ~/.virtualenvs/inventlily-d22a143/bin/activate && python -c "
from uploads.models import UploadBatch, UploadFile, UploadSession, UploadPart
print('UploadBatch fields:', [f.name for f in UploadBatch._meta.get_fields()])
print('UploadFile fields:', [f.name for f in UploadFile._meta.get_fields()])
print('UploadSession fields:', [f.name for f in UploadSession._meta.get_fields()])
print('UploadPart fields:', [f.name for f in UploadPart._meta.get_fields()])
# Verify UUID v7 PK type
import uuid
batch = UploadBatch()
assert isinstance(batch.pk, uuid.UUID), f'Expected uuid.UUID PK, got {type(batch.pk)}'
assert batch.pk.version == 7, f'Expected version 7, got {batch.pk.version}'
print('All 4 models imported and UUID v7 PKs verified.')
"
```

---

### Step 4: Generate and apply fresh migration

**Files**: `uploads/migrations/0001_initial.py` (new file — auto-generated by `makemigrations`)

**Details**: Run `makemigrations` to generate a single initial migration for all 4 models. Then apply it. Since old migrations were deleted in Step 2 and the old tables may still exist in the local DB, we need to `migrate uploads zero` first (to unapply the deleted migrations from Django's state), then apply the new one. If the tables don't exist (fresh DB), `migrate` will create them directly.

**Verify**:
```bash
# Generate migration
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py makemigrations uploads --check --dry-run 2>&1 | head -5
# If the above says "No changes detected", the migration already exists. Otherwise:
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py makemigrations uploads

# Apply migration (handle existing DB state)
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py migrate uploads zero --fake 2>/dev/null; source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py migrate uploads

# Verify migration applied
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py showmigrations uploads
# Expected: [X] 0001_initial

# Verify all 4 tables exist
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py dbshell -- -c "\dt upload_*"
# Expected: upload_batch, upload_file, upload_session, upload_part
```

---

### Step 5: Write admin classes for all 4 models

**Files**: `uploads/admin.py` (rewrite — replace entire file)

**Details**: Replace the current `IngestFileAdmin` with admin classes for all 4 models. Follow patterns from `aikb/admin.md`: use `list_select_related` for FK optimization, `list_filter` for status fields, `readonly_fields` for auto-computed fields, `date_hierarchy` for time-based models.

```python
"""Admin configuration for upload models."""

from django.contrib import admin

from uploads.models import UploadBatch, UploadFile, UploadPart, UploadSession


@admin.register(UploadBatch)
class UploadBatchAdmin(admin.ModelAdmin):
    """Admin interface for upload batches."""

    list_display = ("pk", "created_by", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("pk", "idempotency_key", "created_by__email")
    readonly_fields = ("pk", "created_at", "updated_at")
    list_select_related = ("created_by",)
    date_hierarchy = "created_at"


@admin.register(UploadFile)
class UploadFileAdmin(admin.ModelAdmin):
    """Admin interface for upload files."""

    list_display = (
        "original_filename",
        "uploaded_by",
        "content_type",
        "size_bytes",
        "status",
        "created_at",
    )
    list_filter = ("status", "content_type", "created_at")
    search_fields = ("original_filename", "sha256", "uploaded_by__email")
    readonly_fields = (
        "pk",
        "size_bytes",
        "content_type",
        "sha256",
        "status",
        "error_message",
        "created_at",
        "updated_at",
    )
    list_select_related = ("uploaded_by", "batch")
    date_hierarchy = "created_at"


@admin.register(UploadSession)
class UploadSessionAdmin(admin.ModelAdmin):
    """Admin interface for upload sessions."""

    list_display = (
        "pk",
        "file",
        "status",
        "completed_parts",
        "total_parts",
        "bytes_received",
        "total_size_bytes",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("pk", "idempotency_key", "upload_token")
    readonly_fields = (
        "pk",
        "bytes_received",
        "completed_parts",
        "created_at",
        "updated_at",
    )
    list_select_related = ("file",)
    date_hierarchy = "created_at"


@admin.register(UploadPart)
class UploadPartAdmin(admin.ModelAdmin):
    """Admin interface for upload parts."""

    list_display = (
        "pk",
        "session",
        "part_number",
        "size_bytes",
        "status",
        "created_at",
    )
    list_filter = ("status",)
    search_fields = ("pk", "session__pk")
    readonly_fields = ("pk", "created_at", "updated_at")
    list_select_related = ("session",)
```

**Verify**:
```bash
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check
# Expected: System check identified no issues.

# Verify admin registration
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "
from django.contrib import admin
from uploads.models import UploadBatch, UploadFile, UploadSession, UploadPart
assert admin.site.is_registered(UploadBatch), 'UploadBatch not registered'
assert admin.site.is_registered(UploadFile), 'UploadFile not registered'
assert admin.site.is_registered(UploadSession), 'UploadSession not registered'
assert admin.site.is_registered(UploadPart), 'UploadPart not registered'
print('All 4 admin classes registered.')
"
```

---

### Step 6: Write services for UploadBatch and UploadFile

**Files**: `uploads/services/uploads.py` (rewrite — replace entire file)

**Details**: Replace the 3 existing functions (`validate_file`, `create_ingest_file`, `consume_ingest_file`) with new service functions. Follow service layer conventions from `aikb/services.md` and `aikb/conventions.md`: plain functions (not classes), business logic only, models imported at top level (not lazy — lazy imports are only for tasks/signals per convention).

**Service functions:**

```python
"""Upload services for file validation, creation, and status transitions."""

import hashlib
import logging
import mimetypes

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from uploads.models import UploadBatch, UploadFile

logger = logging.getLogger(__name__)


def validate_file(file, max_size=None):
    """Validate an uploaded file's size and MIME type.

    Args:
        file: A Django UploadedFile instance.
        max_size: Maximum file size in bytes. Defaults to
            ``settings.FILE_UPLOAD_MAX_SIZE`` (50 MB).

    Returns:
        A tuple of (content_type, size_bytes).

    Raises:
        ValidationError: If the file exceeds the size limit or has a
            disallowed MIME type.
    """
    max_size = max_size or settings.FILE_UPLOAD_MAX_SIZE
    size_bytes = file.size

    if size_bytes > max_size:
        raise ValidationError(
            f"File size {size_bytes} bytes exceeds maximum "
            f"of {max_size} bytes.",
            code="file_too_large",
        )

    content_type, _ = mimetypes.guess_type(file.name)
    if content_type is None:
        content_type = "application/octet-stream"

    allowed_types = settings.FILE_UPLOAD_ALLOWED_TYPES
    if allowed_types is not None and content_type not in allowed_types:
        raise ValidationError(
            f"File type '{content_type}' is not allowed. "
            f"Allowed types: {', '.join(allowed_types)}",
            code="file_type_not_allowed",
        )

    return content_type, size_bytes


def compute_sha256(file):
    """Compute SHA-256 hash of a file.

    Reads the file in 64 KB chunks. Seeks back to the start after hashing
    so the file can be saved by Django's FileField afterward.

    Args:
        file: A Django UploadedFile instance.

    Returns:
        Hex-encoded SHA-256 hash string (64 characters).
    """
    hasher = hashlib.sha256()
    file.seek(0)
    for chunk in file.chunks(chunk_size=65_536):
        hasher.update(chunk)
    file.seek(0)
    return hasher.hexdigest()


def create_upload_file(user, file, batch=None):
    """Validate, hash, and store an upload file.

    Args:
        user: The User instance who uploaded the file (or None).
        file: A Django UploadedFile instance.
        batch: Optional UploadBatch to associate with.

    Returns:
        An UploadFile instance with status STORED (success) or FAILED
        (validation error).
    """
    try:
        content_type, size_bytes = validate_file(file)
    except ValidationError as exc:
        upload = UploadFile.objects.create(
            uploaded_by=user,
            file=file,
            original_filename=file.name,
            content_type="unknown",
            size_bytes=file.size,
            batch=batch,
            status=UploadFile.Status.FAILED,
            error_message=str(exc.message),
        )
        logger.warning(
            "Upload file failed validation: pk=%s user=%s error=%s",
            upload.pk,
            user.pk if user else None,
            exc.message,
        )
        return upload

    sha256 = compute_sha256(file)

    upload = UploadFile.objects.create(
        uploaded_by=user,
        file=file,
        original_filename=file.name,
        content_type=content_type,
        size_bytes=size_bytes,
        sha256=sha256,
        batch=batch,
        status=UploadFile.Status.STORED,
    )
    logger.info(
        "Upload file created: pk=%s user=%s file=%s size=%d sha256=%s",
        upload.pk,
        user.pk if user else None,
        file.name,
        size_bytes,
        sha256[:16],
    )
    return upload


def mark_file_processed(upload_file):
    """Transition an upload file from STORED to PROCESSED.

    Uses an atomic UPDATE with a WHERE clause on status to prevent
    race conditions.

    Args:
        upload_file: An UploadFile instance.

    Returns:
        The updated UploadFile instance.

    Raises:
        ValueError: If the file is not in STORED status.
    """
    updated = UploadFile.objects.filter(
        pk=upload_file.pk,
        status=UploadFile.Status.STORED,
    ).update(status=UploadFile.Status.PROCESSED)

    if updated == 0:
        raise ValueError(
            f"Cannot mark upload file {upload_file.pk} as processed: "
            f"status is '{upload_file.status}', expected 'stored'."
        )

    upload_file.refresh_from_db()
    logger.info("Upload file processed: pk=%s", upload_file.pk)
    return upload_file


def mark_file_failed(upload_file, error=""):
    """Transition an upload file to FAILED status.

    Args:
        upload_file: An UploadFile instance.
        error: Error message describing the failure.

    Returns:
        The updated UploadFile instance.
    """
    upload_file.status = UploadFile.Status.FAILED
    upload_file.error_message = error
    upload_file.save(update_fields=["status", "error_message", "updated_at"])
    logger.warning("Upload file failed: pk=%s error=%s", upload_file.pk, error)
    return upload_file


def mark_file_deleted(upload_file):
    """Transition an upload file to DELETED status and remove the physical file.

    Args:
        upload_file: An UploadFile instance.

    Returns:
        The updated UploadFile instance.
    """
    try:
        upload_file.file.delete(save=False)
    except FileNotFoundError:
        pass  # File already gone

    upload_file.status = UploadFile.Status.DELETED
    upload_file.save(update_fields=["status", "updated_at"])
    logger.info("Upload file deleted: pk=%s", upload_file.pk)
    return upload_file


def create_batch(user, idempotency_key=""):
    """Create a new upload batch.

    Args:
        user: The User instance creating the batch (or None).
        idempotency_key: Optional client-provided key to prevent
            duplicate batch creation.

    Returns:
        An UploadBatch instance.
    """
    batch = UploadBatch.objects.create(
        created_by=user,
        idempotency_key=idempotency_key,
    )
    logger.info("Upload batch created: pk=%s user=%s", batch.pk, user.pk if user else None)
    return batch


@transaction.atomic
def finalize_batch(batch):
    """Finalize a batch based on its files' statuses.

    Transitions batch to:
    - COMPLETE: all files are STORED or PROCESSED
    - PARTIAL: some files are STORED/PROCESSED, some FAILED
    - FAILED: all files are FAILED (or no files)

    Args:
        batch: An UploadBatch instance.

    Returns:
        The updated UploadBatch instance.
    """
    file_statuses = list(
        batch.files.values_list("status", flat=True)
    )

    if not file_statuses:
        batch.status = UploadBatch.Status.FAILED
    else:
        success_statuses = {UploadFile.Status.STORED, UploadFile.Status.PROCESSED}
        successes = sum(1 for s in file_statuses if s in success_statuses)
        failures = sum(1 for s in file_statuses if s == UploadFile.Status.FAILED)

        if failures == 0:
            batch.status = UploadBatch.Status.COMPLETE
        elif successes == 0:
            batch.status = UploadBatch.Status.FAILED
        else:
            batch.status = UploadBatch.Status.PARTIAL

    batch.save(update_fields=["status", "updated_at"])
    logger.info("Upload batch finalized: pk=%s status=%s", batch.pk, batch.status)
    return batch
```

**Verify**:
```bash
source ~/.virtualenvs/inventlily-d22a143/bin/activate && python -c "
from uploads.services.uploads import (
    validate_file, compute_sha256, create_upload_file,
    mark_file_processed, mark_file_failed, mark_file_deleted,
    create_batch, finalize_batch,
)
print('All 8 service functions imported successfully.')
"
```

---

### Step 7: Write services for UploadSession and UploadPart

**Files**: `uploads/services/sessions.py` (new file)

**Details**: Create a new service module for session and part management. These services are separated from `uploads.py` because they represent a different domain concern (chunked upload lifecycle vs. file creation/status). This follows the convention in `aikb/services.md`: "One module per domain concern."

```python
"""Upload session services for chunked upload lifecycle management."""

import logging
import math

from django.db import transaction

from uploads.models import UploadFile, UploadPart, UploadSession

logger = logging.getLogger(__name__)


def create_upload_session(upload_file, total_size_bytes, chunk_size_bytes=None):
    """Create an upload session for chunked file upload.

    Args:
        upload_file: An UploadFile instance to associate the session with.
        total_size_bytes: Total expected file size in bytes.
        chunk_size_bytes: Target chunk size in bytes. Defaults to 5 MB.

    Returns:
        An UploadSession instance.
    """
    if chunk_size_bytes is None:
        chunk_size_bytes = 5_242_880  # 5 MB

    total_parts = math.ceil(total_size_bytes / chunk_size_bytes)

    session = UploadSession.objects.create(
        file=upload_file,
        total_size_bytes=total_size_bytes,
        chunk_size_bytes=chunk_size_bytes,
        total_parts=total_parts,
    )
    logger.info(
        "Upload session created: pk=%s file=%s parts=%d",
        session.pk,
        upload_file.pk,
        total_parts,
    )
    return session


def record_upload_part(session, part_number, offset_bytes, size_bytes, sha256=""):
    """Record a received chunk within an upload session.

    Args:
        session: An UploadSession instance.
        part_number: 1-indexed chunk ordinal.
        offset_bytes: Byte offset of this part in the file.
        size_bytes: Size of this part in bytes.
        sha256: Optional SHA-256 hash of the chunk.

    Returns:
        An UploadPart instance with status RECEIVED.
    """
    part = UploadPart.objects.create(
        session=session,
        part_number=part_number,
        offset_bytes=offset_bytes,
        size_bytes=size_bytes,
        sha256=sha256,
        status=UploadPart.Status.RECEIVED,
    )

    # Update session progress counters
    UploadSession.objects.filter(pk=session.pk).update(
        completed_parts=models.F("completed_parts") + 1,
        bytes_received=models.F("bytes_received") + size_bytes,
        status=UploadSession.Status.IN_PROGRESS,
    )

    logger.info(
        "Upload part recorded: session=%s part=%d size=%d",
        session.pk,
        part_number,
        size_bytes,
    )
    return part


@transaction.atomic
def complete_upload_session(session):
    """Complete an upload session after all parts are received.

    Validates that all expected parts have been received, then
    transitions the session to COMPLETE.

    Args:
        session: An UploadSession instance.

    Returns:
        The updated UploadSession instance.

    Raises:
        ValueError: If not all parts have been received.
    """
    session.refresh_from_db()
    received_count = session.parts.filter(
        status=UploadPart.Status.RECEIVED,
    ).count()

    if received_count < session.total_parts:
        raise ValueError(
            f"Cannot complete session {session.pk}: "
            f"received {received_count} of {session.total_parts} parts."
        )

    session.status = UploadSession.Status.COMPLETE
    session.save(update_fields=["status", "updated_at"])

    # Transition the associated file to STORED
    UploadFile.objects.filter(
        pk=session.file_id,
        status=UploadFile.Status.UPLOADING,
    ).update(status=UploadFile.Status.STORED)

    logger.info("Upload session completed: pk=%s", session.pk)
    return session
```

**Note**: The `record_upload_part` function uses `models.F()` for atomic counter updates. The import `from django.db import models` is needed — add it to the import block or use `from django.db.models import F` directly.

**Corrected import block:**
```python
import logging
import math

from django.db import models, transaction

from uploads.models import UploadFile, UploadPart, UploadSession
```

**Verify**:
```bash
source ~/.virtualenvs/inventlily-d22a143/bin/activate && python -c "
from uploads.services.sessions import (
    create_upload_session,
    record_upload_part,
    complete_upload_session,
)
print('All 3 session service functions imported successfully.')
"
```

---

### Step 8: Update the cleanup task

**Files**: `uploads/tasks.py` (rewrite — replace entire file)

**Details**: Replace the existing `cleanup_expired_ingest_files_task` with `cleanup_expired_upload_files_task`. Key changes:
- Model: `IngestFile` → `UploadFile` (lazy import per task conventions in `aikb/tasks.md`)
- Task name: `uploads.tasks.cleanup_expired_upload_files_task`
- The cleanup logic pattern is preserved: batch deletion of expired records with physical file removal via `upload.file.delete()` (FileField retained per Q5)
- The cleanup task filters by `created_at__lt=cutoff` (same as current) — status is not relevant for TTL-based cleanup

```python
"""Celery tasks for the uploads app."""

import logging
from datetime import timedelta

from django.utils import timezone

from celery import shared_task

logger = logging.getLogger(__name__)

BATCH_SIZE = 1000


@shared_task(
    name="uploads.tasks.cleanup_expired_upload_files_task",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def cleanup_expired_upload_files_task(self):
    """Delete upload files older than FILE_UPLOAD_TTL_HOURS.

    Processes at most BATCH_SIZE (1000) expired records per run to
    stay within CELERY_TASK_TIME_LIMIT (300s). Logs the remaining
    count for operational visibility.

    Returns:
        dict: {"deleted": int, "remaining": int}
    """
    from django.conf import settings

    from uploads.models import UploadFile

    ttl_hours = getattr(settings, "FILE_UPLOAD_TTL_HOURS", 24)
    cutoff = timezone.now() - timedelta(hours=ttl_hours)
    expired_qs = UploadFile.objects.filter(created_at__lt=cutoff)
    total_expired = expired_qs.count()

    if total_expired == 0:
        logger.info("No expired upload files to clean up.")
        return {"deleted": 0, "remaining": 0}

    batch_pks = list(
        expired_qs.order_by("pk").values_list("pk", flat=True)[:BATCH_SIZE]
    )
    batch = UploadFile.objects.filter(pk__in=batch_pks)

    deleted_files = 0
    for upload in batch.iterator():
        try:
            upload.file.delete(save=False)
            deleted_files += 1
        except FileNotFoundError:
            deleted_files += 1  # File already gone, still count it

    deleted_count, _ = batch.delete()
    remaining = max(0, total_expired - deleted_count)

    logger.info(
        "Cleaned up %d expired upload files (%d files removed), "
        "%d remaining.",
        deleted_count,
        deleted_files,
        remaining,
    )
    return {"deleted": deleted_count, "remaining": remaining}
```

**Verify**:
```bash
source ~/.virtualenvs/inventlily-d22a143/bin/activate && python -c "
from uploads.tasks import cleanup_expired_upload_files_task
print('Task name:', cleanup_expired_upload_files_task.name)
assert cleanup_expired_upload_files_task.name == 'uploads.tasks.cleanup_expired_upload_files_task'
print('Task imported and name verified.')
"
```

---

### Step 9: Write tests for models and services

**Files**: `uploads/tests/test_services.py` (rewrite — replace entire file), `uploads/tests/test_tasks.py` (rewrite — replace entire file), `uploads/tests/test_models.py` (new file)

**Details**: Replace all existing tests. The `conftest.py` `user` fixture (at `conftest.py:6-15`) remains unchanged.

#### uploads/tests/test_models.py (new file)

Tests for model creation, UUID v7 PKs, status choices, cascade rules, and constraints:

- **UUID v7 PK tests**: Verify `UploadBatch`, `UploadFile`, `UploadSession`, `UploadPart` all get UUID v7 PKs (version 7, `isinstance(pk, uuid.UUID)`)
- **Cascade tests**: Delete user → verify `uploaded_by=None` on UploadFile (SET_NULL), delete file → verify session deleted (CASCADE), delete session → verify parts deleted (CASCADE), delete batch → verify file.batch=None (SET_NULL)
- **UniqueConstraint test**: Two parts with same `(session, part_number)` → `IntegrityError`
- **JSONField default test**: New UploadFile has `metadata == {}`
- **Status choices test**: Verify each model's Status class has expected values

#### uploads/tests/test_services.py (rewrite)

Tests for all 8 service functions in `uploads/services/uploads.py`:

- `validate_file`: 6 tests (valid file, oversized, unknown extension, disallowed type, allowed_types=None, custom max_size) — same coverage as existing tests
- `compute_sha256`: 1 test (known input → known hash)
- `create_upload_file`: 3 tests (valid → STORED with sha256, oversized → FAILED, with batch association)
- `mark_file_processed`: 2 tests (STORED → PROCESSED, non-STORED raises ValueError)
- `mark_file_failed`: 1 test (any status → FAILED with error message)
- `mark_file_deleted`: 1 test (deletes physical file + sets DELETED status)
- `create_batch`: 1 test (creates batch with INIT status)
- `finalize_batch`: 3 tests (all stored → COMPLETE, mixed → PARTIAL, all failed → FAILED)

#### uploads/tests/test_sessions.py (new file)

Tests for 3 service functions in `uploads/services/sessions.py`:

- `create_upload_session`: 2 tests (default chunk size, custom chunk size, verifies total_parts calculation)
- `record_upload_part`: 2 tests (records part with RECEIVED status, updates session counters)
- `complete_upload_session`: 2 tests (all parts received → COMPLETE + file STORED, missing parts raises ValueError)

#### uploads/tests/test_tasks.py (rewrite)

Tests for `cleanup_expired_upload_files_task`:

- Same 5 test scenarios as existing (no expired, expired deleted, missing file, non-expired kept, batch limit)
- Updated to use `UploadFile` model with new field names (`uploaded_by`, `content_type`, `size_bytes`)

**Verify**:
```bash
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest uploads/tests/ -v --tb=short 2>&1 | tail -30
# Expected: all tests pass
```

---

### Step 10: Run linter and formatter

**Files**: All modified files

**Details**: Run Ruff linter and formatter on all modified files. Fix any issues. The Ruff configuration is in `pyproject.toml:10-48`: target Python 3.12, 88-char line length, isort rules enforced.

**Verify**:
```bash
source ~/.virtualenvs/inventlily-d22a143/bin/activate && ruff check uploads/ common/utils.py && ruff format --check uploads/ common/utils.py
# Expected: no issues found
```

---

### Step 11: Run Django system check

**Files**: None (verification only)

**Details**: Ensure Django is fully satisfied with the model definitions, admin registrations, and migrations.

**Verify**:
```bash
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check --deploy 2>&1 | head -20
# Expected: System check identified no issues (or only expected deployment warnings)

# Also verify no pending migrations
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py makemigrations --check --dry-run
# Expected: No changes detected
```

---

## Testing

### Test Matrix

| Category | Test File | Count | What's Tested |
|----------|-----------|-------|---------------|
| Models | `uploads/tests/test_models.py` | ~10 | UUID v7 PKs, cascades, constraints, JSONField, status choices |
| Upload services | `uploads/tests/test_services.py` | ~18 | validate_file, compute_sha256, create_upload_file, mark_file_*, create_batch, finalize_batch |
| Session services | `uploads/tests/test_sessions.py` | ~6 | create_upload_session, record_upload_part, complete_upload_session |
| Tasks | `uploads/tests/test_tasks.py` | ~5 | cleanup_expired_upload_files_task (TTL, batching, missing files) |
| **Total** | | **~39** | |

### Running Tests

```bash
# Run all upload tests
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest uploads/tests/ -v

# Run specific test file
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest uploads/tests/test_models.py -v

# Run with coverage
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest uploads/tests/ -v --tb=short
```

### Key Test Scenarios

1. **UUID v7 ordering**: Create 2 UploadFiles sequentially, verify `pk` values are time-ordered (`pk1 < pk2` when compared as strings)
2. **Cascade SET_NULL**: Create user → create UploadFile → delete user → verify `upload_file.uploaded_by is None`
3. **Cascade CASCADE**: Create UploadFile → create UploadSession → delete UploadFile → verify session is gone
4. **UniqueConstraint**: Create 2 UploadParts with same `(session, part_number)` → `IntegrityError`
5. **SHA-256 computation**: Upload file with known content → verify hash matches `hashlib.sha256(content).hexdigest()`
6. **Batch finalization**: Create batch with 3 files (2 STORED, 1 FAILED) → finalize → verify PARTIAL status
7. **Session completion**: Create session with 3 parts → record all 3 → complete → verify file transitions to STORED

---

## Rollback Plan

If the implementation needs to be reverted:

1. **Git revert**: All changes are in a single PEP, so `git revert <commit>` reverts cleanly
2. **Database**: Since there's no production data, drop the new tables and recreate the old one:
   ```bash
   # Revert code
   git revert <commit>
   # Reset migrations
   source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py migrate uploads zero
   source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py migrate uploads
   ```
3. **Dependencies**: `uuid_utils` was already in `requirements.in` before this PEP — no dependency rollback needed
4. **aikb files**: Revert to git HEAD versions

---

## aikb Impact Map

| File | Impact | What to Update |
|------|--------|----------------|
| `aikb/models.md` | **Major rewrite** | Replace `IngestFile` section with 4 new models (`UploadBatch`, `UploadFile`, `UploadSession`, `UploadPart`). Document all fields, status choices, lifecycle diagrams, indexes, constraints, FK cascade rules. Update Entity Relationship Summary diagram. |
| `aikb/services.md` | **Major rewrite** | Replace `uploads/services/uploads.py` section. Document 8 functions in `uploads.py` (`validate_file`, `compute_sha256`, `create_upload_file`, `mark_file_processed`, `mark_file_failed`, `mark_file_deleted`, `create_batch`, `finalize_batch`) and 3 functions in `sessions.py` (`create_upload_session`, `record_upload_part`, `complete_upload_session`). Add `sessions.py` section. |
| `aikb/tasks.md` | **Update** | Rename `cleanup_expired_ingest_files_task` to `cleanup_expired_upload_files_task`. Update task name, model references, and description. |
| `aikb/admin.md` | **Major update** | Replace `IngestFileAdmin` section with 4 admin classes (`UploadBatchAdmin`, `UploadFileAdmin`, `UploadSessionAdmin`, `UploadPartAdmin`). Document `list_display`, `list_filter`, `readonly_fields`, `list_select_related` for each. |
| `aikb/architecture.md` | **Minor update** | Update `uploads/` section in Django App Structure tree to reflect new model names and new service modules. Update Background Processing section to reference `cleanup_expired_upload_files_task`. |
| `aikb/conventions.md` | **Minor update** | Add note about UUID v7 PK convention with `common.utils.uuid7` wrapper. Mention `uuid_utils` compatibility issue and the wrapper pattern. |
| `aikb/dependencies.md` | **No change** | `uuid_utils` is already documented in `requirements.in`. No new dependencies added. |

---

## Final Verification

### Acceptance Criteria Checks

| # | Criterion (from summary.md) | Verification Command |
|---|---------------------------|---------------------|
| 1 | 4 models created: UploadBatch, UploadFile, UploadSession, UploadPart | `source ~/.virtualenvs/inventlily-d22a143/bin/activate && python -c "from uploads.models import UploadBatch, UploadFile, UploadSession, UploadPart; print('All 4 models imported')"` |
| 2 | All models use UUID v7 primary keys | `source ~/.virtualenvs/inventlily-d22a143/bin/activate && python -c "from uploads.models import UploadBatch, UploadFile, UploadSession, UploadPart; import uuid; models = [UploadBatch, UploadFile, UploadSession, UploadPart]; [print(f'{m.__name__}: UUID v7 PK, version={m().pk.version}') for m in models]"` |
| 3 | All models inherit from TimeStampedModel | `source ~/.virtualenvs/inventlily-d22a143/bin/activate && python -c "from uploads.models import UploadBatch, UploadFile, UploadSession, UploadPart; from common.models import TimeStampedModel; assert all(issubclass(m, TimeStampedModel) for m in [UploadBatch, UploadFile, UploadSession, UploadPart]); print('All inherit TimeStampedModel')"` |
| 4 | UploadFile has sha256, metadata, content_type fields | `source ~/.virtualenvs/inventlily-d22a143/bin/activate && python -c "from uploads.models import UploadFile; fields = {f.name for f in UploadFile._meta.get_fields()}; assert {'sha256', 'metadata', 'content_type'}.issubset(fields); print('Fields present:', sorted(fields))"` |
| 5 | UploadPart has UniqueConstraint on (session, part_number) | `source ~/.virtualenvs/inventlily-d22a143/bin/activate && python -c "from uploads.models import UploadPart; constraints = UploadPart._meta.constraints; print('Constraints:', [(c.name, c.fields) for c in constraints]); assert any(c.fields == ('session', 'part_number') for c in constraints)"` |
| 6 | User FKs use SET_NULL | `source ~/.virtualenvs/inventlily-d22a143/bin/activate && python -c "from uploads.models import UploadBatch, UploadFile; from django.db.models import SET_NULL; assert UploadFile._meta.get_field('uploaded_by').remote_field.on_delete is SET_NULL; assert UploadBatch._meta.get_field('created_by').remote_field is not None; print('SET_NULL verified on user FKs')"` |
| 7 | All services implemented and importable | `source ~/.virtualenvs/inventlily-d22a143/bin/activate && python -c "from uploads.services.uploads import validate_file, compute_sha256, create_upload_file, mark_file_processed, mark_file_failed, mark_file_deleted, create_batch, finalize_batch; from uploads.services.sessions import create_upload_session, record_upload_part, complete_upload_session; print('All 11 service functions imported')"` |
| 8 | Cleanup task updated for new model | `source ~/.virtualenvs/inventlily-d22a143/bin/activate && python -c "from uploads.tasks import cleanup_expired_upload_files_task; print('Task:', cleanup_expired_upload_files_task.name)"` |
| 9 | All admin classes registered | `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from django.contrib import admin; from uploads.models import UploadBatch, UploadFile, UploadSession, UploadPart; assert all(admin.site.is_registered(m) for m in [UploadBatch, UploadFile, UploadSession, UploadPart]); print('All 4 admin classes registered')"` |

### Integration Checks

```bash
# Full test suite (all apps)
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest -v --tb=short

# Django system check
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check

# No pending migrations
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py makemigrations --check --dry-run

# Linter clean
source ~/.virtualenvs/inventlily-d22a143/bin/activate && ruff check .

# Formatter clean
source ~/.virtualenvs/inventlily-d22a143/bin/activate && ruff format --check .
```

### Regression Checks

```bash
# Verify existing conftest.py user fixture still works
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest conftest.py -v 2>&1 | head -5

# Verify accounts app unaffected
source ~/.virtualenvs/inventlily-d22a143/bin/activate && python -c "from accounts.models import User; print('User model OK')"

# Verify frontend app unaffected
source ~/.virtualenvs/inventlily-d22a143/bin/activate && python -c "from frontend.views.dashboard import dashboard; print('Dashboard view OK')"

# Verify Celery app starts (autodiscovery)
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from boot.celery import app; print('Celery app OK, tasks:', list(app.tasks.keys())[:5])"
```

---

## Completion Checklist

- [ ] Step 1: UUID v7 wrapper added to `common/utils.py`
- [ ] Step 2: Old migrations deleted
- [ ] Step 3: 4 models written in `uploads/models.py`
- [ ] Step 4: Fresh migration generated and applied
- [ ] Step 5: Admin classes written for all 4 models
- [ ] Step 6: Upload services written (`uploads/services/uploads.py`)
- [ ] Step 7: Session services written (`uploads/services/sessions.py`)
- [ ] Step 8: Cleanup task updated (`uploads/tasks.py`)
- [ ] Step 9: Tests written (models, services, sessions, tasks)
- [ ] Step 10: Linter and formatter pass
- [ ] Step 11: Django system check passes
- [ ] All acceptance criteria verified
- [ ] Integration checks pass
- [ ] Regression checks pass
- [ ] aikb files updated (per Impact Map)
- [ ] PEP status updated to Implemented
