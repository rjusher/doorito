# PEP 0003: Extend Data Models — Research

| Field | Value |
|-------|-------|
| **PEP** | 0003 |
| **Summary** | [summary.md](summary.md) |
| **Plan** | [plan.md](plan.md) |

---

## Current State Analysis

### Existing Model: IngestFile

The `uploads` app has a single model, `IngestFile` (renamed from `FileUpload` by PEP 0002, now finalized). Defined in `uploads/models.py`:

- **Primary key**: Auto-increment `BigAutoField` (inherited from `DEFAULT_AUTO_FIELD` in `boot/settings.py:144`)
- **Base class**: `TimeStampedModel` → provides `created_at` (auto_now_add) and `updated_at` (auto_now)
- **File storage**: Django `FileField` with `upload_to="uploads/%Y/%m/"` — files stored locally under `MEDIA_ROOT/uploads/YYYY/MM/`
- **User FK**: `ForeignKey(AUTH_USER_MODEL, on_delete=CASCADE, related_name="ingest_files")` — non-nullable, cascading deletes
- **Status**: TextChoices with 4 values: `pending`, `ready`, `consumed`, `failed`
- **Additional fields**: `original_filename` (CharField 255), `file_size` (PositiveBigIntegerField), `mime_type` (CharField 100), `error_message` (TextField, blank)
- **Indexes**: Composite `["user", "-created_at"]`, single `["status"]`
- **db_table**: `"ingest_file"`

PEP 0003 will redesign this model as `UploadFile` with UUID v7 PK, additional metadata fields, new status lifecycle (UPLOADING, STORED, PROCESSED, FAILED, DELETED), and nullable user FK. The Django `FileField` is retained.

### PEP 0002 Status

PEP 0002 (Rename FileUpload → IngestFile) is **finalized**. All code references have been updated to use the `IngestFile` name. PEP 0003 further renames the model to `UploadFile` for consistency with the `Upload*` naming convention across all new models.

### Existing Services

`uploads/services/uploads.py` provides three functions:
1. **`validate_file(file, max_size=None)`** — Validates size/MIME, returns `(mime_type, file_size)` tuple
2. **`create_upload(user, file)`** — Creates IngestFile via `FileField` + `objects.create()`
3. **`consume_upload(file_upload)`** — Atomic status transition `READY → CONSUMED`

PEP 0003 includes service signatures in scope (resolved Q11). These services will be replaced with new functions matching the redesigned models (e.g., `create_upload_file`, `mark_file_stored`, `mark_file_processed`, `create_batch`, `finalize_batch`).

### Existing Task

`uploads/tasks.py` defines `cleanup_expired_uploads_task` which:
- Queries expired IngestFile records by `created_at`
- Calls `upload.file.delete(save=False)` to remove physical files (depends on `FileField`)
- Deletes database records in batches of 1000

Since `FileField` is retained in the redesigned model (resolved Q5), the cleanup task pattern remains viable but will need updates for the new model name and status lifecycle.

### Existing Tests

17 tests across two files:
- `uploads/tests/test_services.py` — 10 tests covering `validate_file`, `create_upload`, `consume_upload`
- `uploads/tests/test_tasks.py` — 5 tests covering `cleanup_expired_uploads_task` with fixtures using `IngestFile.objects.create()`

Tests will need updates for the new model name, status values, and service signatures.

### Database Migration State

Single migration: `uploads/migrations/0001_initial.py` creates the `ingest_file` table. PEP 0002's rename migration has been applied. Since there is no production data (per the summary), the approach of dropping and recreating is viable.

### Settings Configuration

`boot/settings.py` (Base class) defines three upload-related settings at lines 139-141:
- `FILE_UPLOAD_MAX_SIZE = 52_428_800` (50 MB)
- `FILE_UPLOAD_TTL_HOURS = 24`
- `FILE_UPLOAD_ALLOWED_TYPES = None`

The cleanup task reads `FILE_UPLOAD_TTL_HOURS`. `FILE_UPLOAD_MAX_SIZE` and `FILE_UPLOAD_ALLOWED_TYPES` are used by `validate_file()`. These settings remain relevant for the new models (chunk size validation, TTL-based cleanup) but may need augmentation.

---

## Key Files & Functions

### Files to Modify (Model Changes)

| File | What Changes |
|------|-------------|
| `uploads/models.py` | Redesign — rename IngestFile to UploadFile, add 3 new models (UploadBatch, UploadSession, UploadPart) |
| `uploads/admin.py` | New admin classes for all 4 models |
| `uploads/migrations/` | New migration(s) — drop old table, create 4 new tables |
| `uploads/apps.py` | Possibly unchanged, but verify `default_auto_field` doesn't conflict with UUID PKs |

### Files Affected (Existing Code Updates)

| File | Impact |
|------|--------|
| `uploads/services/uploads.py` | All 3 functions will be replaced with new service signatures for the redesigned models. |
| `uploads/tasks.py` | `cleanup_expired_uploads_task` needs updates for new model name and status lifecycle. |
| `uploads/tests/test_services.py` | Tests need rewriting for new model shape and service signatures. |
| `uploads/tests/test_tasks.py` | Tests need updates for new model name and status values. |
| `conftest.py` | `user` fixture is fine (no upload references). |

### Files for Pattern Reference

| File | What to Learn |
|------|--------------|
| `common/models.py:6-13` | `TimeStampedModel` — base class for all new models |
| `common/fields.py` | `MoneyField` — example of custom field with `deconstruct()` |
| `common/utils.py:10-22` | `generate_reference()` — reference generation pattern |
| `accounts/models.py` | `User` model — FK target, `db_table` convention |
| `boot/settings.py:144` | `DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"` — must be overridden per-model for UUID PKs |

### Configuration Files

| File | Relevance |
|------|-----------|
| `boot/settings.py:139-141` | Upload settings that may need new entries for chunk size defaults, etc. |
| `uploads/apps.py:9` | `default_auto_field = "django.db.models.BigAutoField"` — UUID models will need explicit `id = UUIDField(primary_key=True)` on each model |

---

## Technical Constraints

### 1. UUID v7 Primary Keys

`boot/settings.py:144` sets `DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"` and `uploads/apps.py:9` repeats this. Every new model that wants a UUID PK must explicitly declare:

```python
id = models.UUIDField(primary_key=True, default=uuid_utils.uuid7, editable=False)
```

UUID v7 (RFC 9562) provides time-sorted ordering, which is better than UUID v4 for database index performance. The `uuid_utils` package (v0.14.1, Rust-based) provides the `uuid7()` function since Python 3.12 lacks native UUID v7 support (added in Python 3.14). Each of the 4 models needs this field.

### 2. No Production Data — Clean Slate

The summary confirms "There is no production data. The existing table will be dropped and recreated." This means:
- No data migration is needed
- The old migration(s) can be superseded by a new migration that drops the old table and creates the new schema
- PEP 0002's rename migration becomes moot since the table is being dropped anyway

### 3. FileField Retained

The redesigned UploadFile model **retains Django's `FileField`** (resolved in discussions.md Q5). This means:
- Django's automatic file upload handling (`model.save()` writes to `MEDIA_ROOT`) continues to work
- `upload.file.delete()` works for cleanup tasks
- `upload.file.url` works for templates/views
- The existing storage interaction pattern is preserved

The abstract storage pointer design (storage_backend, storage_bucket, storage_key) was considered but rejected in favor of keeping FileField for simplicity and compatibility with existing Django patterns.

### 4. JSONField Requirements

One model uses `JSONField`:
- `UploadFile.metadata` — Flexible non-sensitive file metadata

Django's `JSONField` works natively with PostgreSQL's `jsonb` column type. No additional dependencies needed. Considerations:
- `default=dict` is the standard default for optional JSON fields
- PostgreSQL supports GIN indexes on jsonb for key lookups (not needed initially)
- No schema validation at the database level — application-level validation if needed

### 5. Foreign Key Cascade Rules

The proposed cascade rules differ from the current model:

| Relationship | Current | Proposed | Implication |
|-------------|---------|----------|-------------|
| User → UploadFile | `CASCADE` | `SET_NULL` (nullable) | Files survive user deletion; queries must handle `uploaded_by=None` |
| User → UploadBatch | N/A | `SET_NULL` (nullable) | Batches survive user deletion |
| UploadFile → UploadSession | N/A | `CASCADE` (1:1) | Deleting a file deletes its session |
| UploadSession → UploadPart | N/A | `CASCADE` | Deleting a session deletes all parts |
| UploadBatch → UploadFile | N/A | `SET_NULL` (nullable) | Files survive batch deletion |

The `SET_NULL` on user FKs is a deliberate design choice for data preservation. This requires `null=True` on the FK fields.

### 6. UniqueConstraint Usage

One model requires a composite unique constraint:
- `UploadPart`: `UniqueConstraint(fields=["session", "part_number"])` — prevents duplicate chunk numbers

Django's `UniqueConstraint` (preferred over `unique_together` since Django 4.1) lives in `Meta.constraints`. This constraint also creates an implicit database index.

### 7. Celery Task Serialization

Celery is configured with JSON serialization (`CELERY_TASK_SERIALIZER = "json"` in `boot/settings.py:129`). UUID primary keys must be passed as strings to tasks, not as `uuid.UUID` objects. This is a consideration for any future tasks that reference these models by PK.

---

## Pattern Analysis

### Patterns to Follow

**1. TextChoices for status fields** (established in `uploads/models.py:24-28`)
```python
class Status(models.TextChoices):
    PENDING = "pending", "Pending"
    ...
```
All 4 models in the PEP use status fields. Each should define its own `Status` inner class following this pattern. Per `aikb/conventions.md`, use `TextChoices`, not `IntegerChoices`.

**2. `db_table` explicit naming** (established in `uploads/models.py:47`, `accounts/models.py:10`)
Every model specifies `db_table` explicitly. The new models should follow suit: `upload_batch`, `upload_file`, `upload_session`, `upload_part`.

**3. `verbose_name` / `verbose_name_plural`** (established in `uploads/models.py:48-49`)
Every model should define these in `Meta` for admin interface clarity.

**4. `__str__` method** (established in `uploads/models.py:56-57`, `accounts/models.py:14-15`)
Every model should have a meaningful `__str__` for admin/debugging.

**5. Module-level docstrings** (per `aikb/conventions.md`)
The models module and each class should have docstrings.

**6. Index naming** — Django auto-generates index names. The existing model uses auto-generated names. Let Django auto-generate for the new models as well.

**7. Admin patterns** (per `aikb/admin.md`)
Use `list_select_related` to optimize FKs, `list_filter` for status fields, `readonly_fields` for auto-computed fields, `date_hierarchy` for time-based models.

**8. TimeStampedModel inheritance** (resolved Q3, per `aikb/models.md`)
All 4 models inherit from `TimeStampedModel`, providing `created_at` (auto_now_add) and `updated_at` (auto_now). Models needing additional timestamp fields add them alongside the inherited ones.

### Patterns to Depart From

**1. Non-nullable user FK with CASCADE** — Current pattern is `ForeignKey(AUTH_USER_MODEL, CASCADE)`. PEP changes to `SET_NULL` with `null=True`. This is intentional for data preservation.

**2. Auto-increment PK** — Current pattern uses `BigAutoField` via `DEFAULT_AUTO_FIELD`. PEP uses explicit UUID v7 PKs on all models for better distributed ID generation and time-sorted ordering.

### Patterns to Avoid

**1. Putting business logic in models** — Per `aikb/services.md`, business logic belongs in services. The models should be pure data containers with field definitions, Meta options, and `__str__`. Status transition logic, validation rules, and file handling should go in services.

**2. Over-indexing** — Only add indexes that match known query patterns. The summary identifies key indexes (sha256 on UploadFile, composite unique constraints). Don't add speculative indexes.

---

## External Research

### UUID v7 (RFC 9562)

PEP 0003 uses UUID v7 for all primary keys via `uuid_utils.uuid7()`. UUID v7 provides:
- **Time-sorted ordering** — the first 48 bits encode a Unix timestamp, so UUIDs sort chronologically
- **Better B-tree index performance** — sequential inserts avoid random page splits (unlike UUID v4)
- **Distributed ID generation** — no central sequence needed

Implementation: `uuid_utils` package (v0.14.1, Rust-based). Python 3.12 lacks native UUID v7 (added in Python 3.14 via PEP 766). In PostgreSQL, UUIDs map to a native 128-bit `uuid` column type. Django admin, serializers, and URL resolvers handle UUID PKs natively.

### Chunked Upload Design

The `UploadSession` + `UploadPart` models follow the tus.io / S3 multipart upload pattern:
- Client negotiates a session (knows total size, gets chunk size)
- Client uploads parts independently (possibly in parallel)
- Server tracks part completion via `UploadPart` records
- Server assembles parts after all are received

The `idempotency_key` and `upload_token` on `UploadSession` support client-side retry safety and lightweight auth — common in chunked upload protocols.

---

## Risk & Edge Cases

### 1. PEP 0002 Dependency (Resolved)

PEP 0002 is finalized. The model is currently named `IngestFile`. PEP 0003 further renames it to `UploadFile` and drops/recreates the table, so PEP 0002's table-level changes are effectively superseded.

### 2. Updating Existing Services and Tasks

**Risk**: The redesigned UploadFile changes the status set and user FK behavior. Existing services and tasks need updates.

**Mitigation**: PEP 0003 includes service signatures in scope (resolved Q11). Services will be replaced with new functions, and the cleanup task updated for the new model name and status lifecycle. Since `FileField` is retained, the cleanup task's file deletion pattern (`upload.file.delete()`) still works.

### 3. Migration Strategy

**Risk**: With PEP 0002's rename migration applied, the migration chain needs care.

**Mitigation**: Since there's no production data, the cleanest approach is:
- Delete all existing migrations in `uploads/migrations/`
- Write the 4 new models
- Run `makemigrations` to generate a clean `0001_initial.py`
- This avoids any migration chain complications

### 4. UUID PK and Celery Serialization

**Risk**: If a Celery task receives a UUID PK, it arrives as a string after JSON deserialization. Lookups like `Model.objects.get(id=task_arg)` work because Django/PostgreSQL handles string-to-UUID coercion, but explicit `uuid.UUID()` conversion is safer.

**Edge case**: Passing `uuid.UUID` objects to `.delay()` fails with default JSON serializer. Always convert to `str()` first.

### 5. UploadPart temp_storage_key Lifecycle

**Risk**: `temp_storage_key` points to a temporary location for the chunk before assembly. If assembly fails or is abandoned, orphaned temporary files could accumulate.

**Mitigation**: The cleanup task (to be redesigned) should handle abandoned sessions and their parts. The `UploadSession.status` field (`aborted`/`failed`) serves as the trigger.

---

## Recommendations

### 1. Fresh Migration — Delete and Recreate

Since there's no production data:
1. Delete existing migrations in `uploads/migrations/`
2. Write the 4 new models
3. Run `makemigrations` to generate a clean `0001_initial.py`

This is the cleanest path — no rename migrations, no schema diffs, no migration chain issues.

### 2. Admin Classes for All Models

All 4 models should get admin classes:
- `UploadBatchAdmin` — list by status, created_by, timestamps
- `UploadFileAdmin` — replace existing, list by status, batch, uploaded_by
- `UploadSessionAdmin` — list by status, file reference, progress
- `UploadPartAdmin` — list by session, part_number, status

### 3. Settings Additions

Consider adding new settings for chunk upload defaults:
- `FILE_UPLOAD_CHUNK_SIZE` — default chunk size (5 MB per the summary)
- `UPLOAD_SESSION_TTL_HOURS` — TTL for abandoned upload sessions

These are optional and could be deferred, but defining them in `boot/settings.py` alongside existing upload settings would be consistent.

### 4. Verify During Implementation

- [ ] `python manage.py makemigrations` generates clean migration with all 4 tables
- [ ] `python manage.py migrate` applies successfully
- [ ] `python manage.py check` passes with no warnings
- [ ] `ruff check .` passes (especially import order and unused imports after deletions)
- [ ] UUID fields work correctly in Django admin (create, view, filter)
- [ ] JSONField defaults work (`default=dict` in migration)
- [ ] UniqueConstraints generate correct database indexes
- [ ] All FK cascade rules work as expected (test with shell: create user, create batch, delete user, verify batch.created_by is None)
