# PEP 0003: Extend Data Models — Research

| Field | Value |
|-------|-------|
| **PEP** | 0003 |
| **Summary** | [summary.md](summary.md) |
| **Plan** | [plan.md](plan.md) |

---

## Current State Analysis

### Existing Model: IngestFile

The `uploads` app has a single model, `IngestFile` (renamed from `FileUpload` by PEP 0002, currently mid-implementation). Defined in `uploads/models.py`:

- **Primary key**: Auto-increment `BigAutoField` (inherited from `DEFAULT_AUTO_FIELD` in `boot/settings.py:144`)
- **Base class**: `TimeStampedModel` → provides `created_at` (auto_now_add) and `updated_at` (auto_now)
- **File storage**: Django `FileField` with `upload_to="uploads/%Y/%m/"` — files stored locally under `MEDIA_ROOT/uploads/YYYY/MM/`
- **User FK**: `ForeignKey(AUTH_USER_MODEL, on_delete=CASCADE, related_name="ingest_files")` — non-nullable, cascading deletes
- **Status**: TextChoices with 4 values: `pending`, `ready`, `consumed`, `failed`
- **Additional fields**: `original_filename` (CharField 255), `file_size` (PositiveBigIntegerField), `mime_type` (CharField 100), `error_message` (TextField, blank)
- **Indexes**: Composite `["user", "-created_at"]`, single `["status"]`
- **db_table**: `"ingest_file"`

### PEP 0002 Implementation Status

PEP 0002 (Rename FileUpload → IngestFile) is in `Implementing` status. The model class in `uploads/models.py` has been renamed, but **several files still reference the old `FileUpload` name**:

| File | Status |
|------|--------|
| `uploads/models.py` | **Renamed** — class is `IngestFile` |
| `uploads/admin.py:5,8` | Still imports/registers `FileUpload` |
| `uploads/services/uploads.py:9,68,84` | Still imports/uses `FileUpload` |
| `uploads/tasks.py:33,37,44,47` | Still imports/uses `FileUpload` |
| `uploads/tests/test_services.py:8` | Still imports `FileUpload` |
| `uploads/tests/test_tasks.py:9,25,35,60` | Still imports/uses `FileUpload` |
| `aikb/models.md`, `aikb/admin.md` | Still document `FileUpload` |

**Implication**: PEP 0003 depends on PEP 0002 being fully completed. The plan must not assume PEP 0002 is done — it should either (a) require PEP 0002 completion as a prerequisite gate, or (b) incorporate the remaining rename work.

### Existing Services

`uploads/services/uploads.py` provides three functions:
1. **`validate_file(file, max_size=None)`** — Validates size/MIME, returns `(mime_type, file_size)` tuple
2. **`create_upload(user, file)`** — Creates IngestFile via `FileField` + `objects.create()`
3. **`consume_upload(file_upload)`** — Atomic status transition `READY → CONSUMED`

All three are tightly coupled to Django's `FileField` and the current 4-status lifecycle. PEP 0003's redesign (abstract storage pointers, new status set, batch support) will make these services obsolete or require complete rewrites. However, the PEP summary explicitly states services/endpoints are **out of scope** — only models are being created.

### Existing Task

`uploads/tasks.py` defines `cleanup_expired_uploads_task` which:
- Queries expired IngestFile records by `created_at`
- Calls `upload.file.delete(save=False)` to remove physical files (depends on `FileField`)
- Deletes database records in batches of 1000

This task **will break** when `FileField` is replaced with abstract storage pointers. The `file.delete()` call relies on Django's storage backend integration, which won't exist on the redesigned model.

### Existing Tests

17 tests across two files:
- `uploads/tests/test_services.py` — 10 tests covering `validate_file`, `create_upload`, `consume_upload`
- `uploads/tests/test_tasks.py` — 5 tests covering `cleanup_expired_uploads_task` with fixtures using `FileUpload.objects.create()`

All tests use `SimpleUploadedFile` and `FileField` semantics. They will need to be either rewritten or replaced.

### Database Migration State

Single migration: `uploads/migrations/0001_initial.py` creates the `file_upload` table (PEP 0002's rename migration hasn't been created yet). Since there is no production data (per the summary), the approach of dropping and recreating is viable.

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
| `uploads/models.py` | Complete rewrite — 5 new models replace 1 existing model |
| `uploads/admin.py` | New admin classes for all 5 models (or subset worth exposing) |
| `uploads/migrations/` | New migration(s) — drop old table, create 5 new tables |
| `uploads/apps.py` | Possibly unchanged, but verify `default_auto_field` doesn't conflict with UUID PKs |

### Files Affected (Existing Code Breakage)

| File | Impact |
|------|--------|
| `uploads/services/uploads.py` | All 3 functions assume `FileField` and old status set — will break. PEP says services are out of scope, so these need to be either deleted, stubbed, or left broken with a TODO. |
| `uploads/tasks.py` | `cleanup_expired_uploads_task` calls `upload.file.delete()` — will break without `FileField`. |
| `uploads/tests/test_services.py` | 10 tests rely on `FileField` and old model shape — will fail. |
| `uploads/tests/test_tasks.py` | 5 tests rely on `FileField` and old model shape — will fail. |
| `conftest.py` | `user` fixture is fine (no upload references). |

### Files for Pattern Reference

| File | What to Learn |
|------|--------------|
| `common/models.py:6-13` | `TimeStampedModel` — pattern for abstract base (PEP departs from this) |
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

### 1. UUID Primary Keys vs DEFAULT_AUTO_FIELD

`boot/settings.py:144` sets `DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"` and `uploads/apps.py:9` repeats this. Every new model that wants a UUID PK must explicitly declare:

```python
id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
```

This is not inheritable via `DEFAULT_AUTO_FIELD` — Django's auto field mechanism only applies when no explicit PK is defined. Each of the 5 models needs this field.

### 2. No Production Data — Clean Slate

The summary confirms "There is no production data. The existing table will be dropped and recreated." This means:
- No data migration is needed
- The old `0001_initial.py` migration can be effectively superseded by squashing or by a new migration that drops the old table and creates the new schema
- The PEP 0002 rename migration (not yet created) becomes moot if the table is being dropped anyway

### 3. FileField Removal Consequences

Replacing `FileField` with abstract storage pointers (`storage_backend`, `storage_bucket`, `storage_key`) means:
- **No automatic file upload handling** — Django won't save files to `MEDIA_ROOT` on `model.save()`
- **No `upload.file.delete()`** — The cleanup task's file deletion logic breaks
- **No `upload.file.url`** — Templates/views can't use `{{ upload.file.url }}`
- **Storage interaction becomes explicit** — A service layer must handle file writes/reads/deletes using the storage pointer fields

This is intentional (the PEP explicitly defers storage backend implementation), but it means existing services and tasks must be updated or removed.

### 4. JSONField Requirements

Two models use `JSONField`:
- `IngestFile.metadata` — Flexible non-sensitive file metadata
- `PortalEventOutbox.payload` — Event data

Django's `JSONField` works natively with PostgreSQL's `jsonb` column type. No additional dependencies needed. Considerations:
- `default=dict` is the standard default for optional JSON fields
- PostgreSQL supports GIN indexes on jsonb for key lookups (not needed initially)
- No schema validation at the database level — application-level validation if needed

### 5. Foreign Key Cascade Rules

The proposed cascade rules differ from the current model:

| Relationship | Current | Proposed | Implication |
|-------------|---------|----------|-------------|
| User → IngestFile | `CASCADE` | `SET_NULL` (nullable) | Files survive user deletion; queries must handle `uploaded_by=None` |
| User → UploadBatch | N/A | `SET_NULL` (nullable) | Batches survive user deletion |
| IngestFile → UploadSession | N/A | `CASCADE` (1:1) | Deleting a file deletes its session |
| UploadSession → UploadPart | N/A | `CASCADE` | Deleting a session deletes all parts |
| IngestFile → PortalEventOutbox | N/A | `CASCADE` | Deleting a file deletes its outbox entries |
| UploadBatch → IngestFile | N/A | `SET_NULL` (nullable) | Files survive batch deletion |

The `SET_NULL` on user FKs is a deliberate design choice for data preservation. This requires `null=True` on the FK fields.

### 6. UniqueConstraint Usage

Two models require composite unique constraints:
- `UploadPart`: `UniqueConstraint(fields=["session", "part_number"])` — prevents duplicate chunk numbers
- `PortalEventOutbox`: `UniqueConstraint(fields=["event_type", "idempotency_key"])` — prevents duplicate events

Django's `UniqueConstraint` (preferred over `unique_together` since Django 4.1) lives in `Meta.constraints`. These constraints also create implicit database indexes.

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
All 5 models in the PEP use status fields. Each should define its own `Status` inner class following this pattern. Per `aikb/conventions.md`, use `TextChoices`, not `IntegerChoices`.

**2. `db_table` explicit naming** (established in `uploads/models.py:47`, `accounts/models.py:10`)
Every model specifies `db_table` explicitly. The new models should follow suit: `upload_batch`, `ingest_file`, `upload_session`, `upload_part`, `portal_event_outbox`.

**3. `verbose_name` / `verbose_name_plural`** (established in `uploads/models.py:48-49`)
Every model should define these in `Meta` for admin interface clarity.

**4. `__str__` method** (established in `uploads/models.py:56-57`, `accounts/models.py:14-15`)
Every model should have a meaningful `__str__` for admin/debugging.

**5. Module-level docstrings** (per `aikb/conventions.md`)
The models module and each class should have docstrings.

**6. Index naming** — Django auto-generates index names. The existing model uses auto-generated names (e.g., `file_upload_user_id_c50e60_idx`). Let Django auto-generate for the new models as well.

**7. Admin patterns** (per `aikb/admin.md`)
Use `list_select_related` to optimize FKs, `list_filter` for status fields, `readonly_fields` for auto-computed fields, `date_hierarchy` for time-based models.

### Patterns to Depart From

**1. TimeStampedModel inheritance** — The PEP proposes `models.Model` with explicit timestamp fields instead of inheriting from `TimeStampedModel`. This is a deliberate departure: the existing `TimeStampedModel` uses `auto_now_add` and `auto_now`, which don't allow explicit timestamp setting. Some new models (e.g., `PortalEventOutbox.delivered_at`) need nullable/explicit timestamps that don't fit the auto pattern.

However, for models that need standard `created_at`/`updated_at` (like `UploadBatch`, `IngestFile`), using `TimeStampedModel` and adding extra timestamp fields would be more DRY and consistent with the project convention. The plan should decide whether to depart from `TimeStampedModel` globally or selectively.

**2. Non-nullable user FK with CASCADE** — Current pattern is `ForeignKey(AUTH_USER_MODEL, CASCADE)`. PEP changes to `SET_NULL` with `null=True`. This is intentional for data preservation.

**3. FileField for storage** — Current pattern uses Django's `FileField`. PEP replaces with abstract pointer fields. This is the core design change.

### Patterns to Avoid

**1. Putting business logic in models** — Per `aikb/services.md`, business logic belongs in services. The models should be pure data containers with field definitions, Meta options, and `__str__`. Status transition logic, validation rules, and file handling should go in services (even though services are out of scope for this PEP).

**2. Over-indexing** — Only add indexes that match known query patterns. The summary identifies key indexes (sha256 on IngestFile, composite unique constraints). Don't add speculative indexes.

---

## External Research

### Django 6.0 UUID Primary Keys

Django's `UUIDField` with `primary_key=True` and `default=uuid.uuid4` is the standard approach. In PostgreSQL, this maps to a native `uuid` column type. Key considerations:
- UUID v4 (random) is the default. For time-sorted ordering, UUID v7 is available in Python 3.12+ via the `uuid` module, but Django doesn't natively support v7 as a default.
- UUIDs are 128-bit (16 bytes) vs 64-bit (8 bytes) for BigAutoField — slightly larger indexes but negligible for this scale.
- Django admin, serializers, and URL resolvers handle UUID PKs natively.

### Transactional Outbox Pattern

The `PortalEventOutbox` model implements the transactional outbox pattern — a well-established pattern for reliable event delivery:
- Events are written to the outbox table in the same database transaction as the state change
- A separate process (poller or CDC) reads pending events and delivers them
- The `status` + `attempts` + `next_attempt_at` fields enable retry-with-backoff
- The `idempotency_key` + `event_type` unique constraint ensures exactly-once event creation

This is out of scope for this PEP (only the model schema is defined), but the field design matches standard implementations of this pattern.

### Chunked Upload Design

The `UploadSession` + `UploadPart` models follow the tus.io / S3 multipart upload pattern:
- Client negotiates a session (knows total size, gets chunk size)
- Client uploads parts independently (possibly in parallel)
- Server tracks part completion via `UploadPart` records
- Server assembles parts after all are received

The `idempotency_key` and `upload_token` on `UploadSession` support client-side retry safety and lightweight auth — common in chunked upload protocols.

---

## Risk & Edge Cases

### 1. PEP 0002 Dependency Conflict

**Risk**: PEP 0002 is mid-implementation. If PEP 0003 drops and recreates the `ingest_file` table, most of PEP 0002's remaining work (admin/service/task/test renames) becomes irrelevant for the model itself — but the service, task, and test renames are still needed for the code that wraps the model.

**Mitigation**: Either (a) complete PEP 0002 first then proceed with PEP 0003, or (b) acknowledge that PEP 0003 subsumes the model-level changes and only the code-level renames from PEP 0002 need completing. Option (b) is cleaner since the table is being dropped anyway.

### 2. Breaking Existing Services and Tasks

**Risk**: The redesigned IngestFile removes `FileField`, changes the status set, and changes the user FK behavior. This breaks:
- `uploads/services/uploads.py` — all 3 functions
- `uploads/tasks.py` — `cleanup_expired_uploads_task`
- `uploads/tests/` — all 17 tests

**Mitigation**: The PEP says services are out of scope, but it can't leave broken imports. Options:
- Delete the existing services/tasks/tests and note they'll be rebuilt in a future PEP
- Stub them with `pass` / `raise NotImplementedError`
- Create minimal replacement services that work with the new model shape

### 3. Migration Strategy

**Risk**: With PEP 0002's rename migration potentially in flight, the migration chain could get messy.

**Mitigation**: Since there's no production data, the cleanest approach is:
- Delete all existing migrations in `uploads/migrations/`
- Run `makemigrations` fresh to generate a single initial migration with all 5 models
- This avoids any migration chain complications

### 4. UUID PK and Celery Serialization

**Risk**: If a Celery task receives a UUID PK, it arrives as a string after JSON deserialization. Lookups like `Model.objects.get(id=task_arg)` work because Django/PostgreSQL handles string-to-UUID coercion, but explicit `uuid.UUID()` conversion is safer.

**Edge case**: Passing `uuid.UUID` objects to `.delay()` fails with default JSON serializer. Always convert to `str()` first.

### 5. Denormalized Counters on UploadBatch

**Risk**: `total_files`, `stored_files`, `failed_files` are denormalized counters. They can drift from reality if updates to IngestFile don't atomically update the batch counters.

**Edge case**: Concurrent uploads completing simultaneously could cause counter drift without `F()` expressions or `SELECT ... FOR UPDATE`.

**Mitigation**: This is a service-layer concern (out of scope), but the model design should note that these fields are denormalized and need careful update logic.

### 6. UploadPart temp_storage_key Lifecycle

**Risk**: `temp_storage_key` points to a temporary location for the chunk before assembly. If assembly fails or is abandoned, orphaned temporary files could accumulate.

**Mitigation**: The cleanup task (to be redesigned) should handle abandoned sessions and their parts. The `UploadSession.status` field (`aborted`/`failed`) serves as the trigger.

### 7. TimeStampedModel Decision

**Risk**: Departing from `TimeStampedModel` for all 5 models introduces inconsistency with the project convention ("All future models should inherit from TimeStampedModel" per `aikb/models.md`).

**Mitigation**: The PEP summary says `models.Model` with explicit timestamps, but this should be reconsidered. Most models only need standard `created_at`/`updated_at` — only `PortalEventOutbox` needs the extra `delivered_at`. Using `TimeStampedModel` as the base and adding extra fields is simpler and more consistent. If explicit control over `created_at` is needed (e.g., for backdating in tests), `auto_now_add` can be worked around with `update()` calls.

---

## Recommendations

### 1. Complete PEP 0002 First or Subsume It

PEP 0002's model-level rename is moot since the table is being dropped. However, the code-level renames (admin class name, service function names, task name, test references) still matter because PEP 0003 builds on that naming. **Recommendation**: Complete PEP 0002 fully before starting PEP 0003, or explicitly note in the plan that PEP 0003 step 1 is "finish PEP 0002 code renames."

### 2. Fresh Migration — Delete and Recreate

Since there's no production data:
1. Delete `uploads/migrations/0001_initial.py`
2. Write the 5 new models
3. Run `makemigrations` to generate a clean `0001_initial.py`

This is the cleanest path — no rename migrations, no schema diffs, no migration chain issues.

### 3. Reuse TimeStampedModel Where Possible

Consider keeping `TimeStampedModel` as the base class for models that only need standard timestamps (`UploadBatch`, `IngestFile`, `UploadSession`, `UploadPart`). Only `PortalEventOutbox` genuinely needs extra timestamp fields (`delivered_at`), and it can still inherit from `TimeStampedModel` and add them. This maintains project consistency and reduces boilerplate.

If the PEP author specifically wants explicit control over timestamps (e.g., for testing), this is a design decision for the discussions file.

### 4. Handle Existing Services/Tasks/Tests

The plan must address what happens to existing code that references the old model shape:
- **Services** (`validate_file`, `create_upload`, `consume_upload`): Delete or replace with stubs
- **Task** (`cleanup_expired_uploads_task`): Delete or rewrite for new model shape
- **Tests**: Delete — they test services that are being removed

A clean approach: delete the existing services, task, and tests, and add TODOs or a follow-up PEP for rebuilding them.

### 5. Admin Classes for New Models

All 5 models should get admin classes. At minimum:
- `UploadBatchAdmin` — list by status, created_by, timestamps
- `IngestFileAdmin` — replace existing, list by status, batch, uploaded_by
- `UploadSessionAdmin` — list by status, file reference, progress
- `UploadPartAdmin` — list by session, part_number, status
- `PortalEventOutboxAdmin` — list by event_type, status, attempts

### 6. Settings Additions

Consider adding new settings for chunk upload defaults:
- `FILE_UPLOAD_CHUNK_SIZE` — default chunk size (5 MB per the summary)
- `UPLOAD_SESSION_TTL_HOURS` — TTL for abandoned upload sessions

These are optional and could be deferred, but defining them in `boot/settings.py` alongside existing upload settings would be consistent.

### 7. Verify During Implementation

- [ ] `python manage.py makemigrations` generates clean migration with all 5 tables
- [ ] `python manage.py migrate` applies successfully
- [ ] `python manage.py check` passes with no warnings
- [ ] `ruff check .` passes (especially import order and unused imports after deletions)
- [ ] UUID fields work correctly in Django admin (create, view, filter)
- [ ] JSONField defaults work (`default=dict` in migration)
- [ ] UniqueConstraints generate correct database indexes
- [ ] All FK cascade rules work as expected (test with shell: create user, create batch, delete user, verify batch.created_by is None)
