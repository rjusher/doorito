# PEP 0002: Rename FileUpload to IngestFile — Research

| Field | Value |
|-------|-------|
| **PEP** | 0002 |
| **Summary** | [summary.md](summary.md) |
| **Plan** | [plan.md](plan.md) |

---

## Current State Analysis

The `uploads` app was introduced by PEP 0001 and provides temporary file upload infrastructure. It is the only app in the project with a concrete domain model (besides `accounts.User`).

### Model: `FileUpload`
Defined in `uploads/models.py:8`. Inherits from `TimeStampedModel`. Has a status lifecycle (`pending → ready → consumed` or `pending → failed`) tracked via a `TextChoices` enum (`FileUpload.Status`). The model uses `db_table = "file_upload"` with two indexes:
- `file_upload_user_id_c50e60_idx` — composite on `["user", "-created_at"]`
- `file_upload_status_20c17f_idx` — single on `["status"]`

The FK to `User` uses `related_name="uploads"`, meaning `user.uploads.all()` is the reverse accessor. No code currently uses this accessor.

### Services: `uploads/services/uploads.py`
Three functions:
- `validate_file(file, max_size=None)` — validates size and MIME type (stays unchanged per summary)
- `create_upload(user, file)` — creates a `FileUpload` record with READY or FAILED status
- `consume_upload(file_upload)` — atomically transitions READY → CONSUMED

All three reference `FileUpload` directly via `from uploads.models import FileUpload` (line 9). The `create_upload` and `consume_upload` functions use `FileUpload.objects.create(...)`, `FileUpload.objects.filter(...)`, and `FileUpload.Status.*` extensively.

### Admin: `uploads/admin.py`
`FileUploadAdmin` (line 9) registered with `@admin.register(FileUpload)`. Standard ModelAdmin with list_display, filters, search, readonly fields, select_related, and date_hierarchy.

### Task: `uploads/tasks.py`
`cleanup_expired_uploads_task` (line 21) with explicit `name="uploads.tasks.cleanup_expired_uploads_task"` (line 16). Uses lazy import of `FileUpload` inside the task body (line 33). Queries `FileUpload.objects.filter(created_at__lt=cutoff)` for expired records.

### Tests
- `uploads/tests/test_services.py` — 11 tests across 3 classes (`TestValidateFile`, `TestCreateUpload`, `TestConsumeUpload`). Imports `FileUpload`, `consume_upload`, `create_upload`, `validate_file` (line 8-9). References `FileUpload.Status.*` in assertions (14 occurrences).
- `uploads/tests/test_tasks.py` — 5 tests in `TestCleanupExpiredUploadsTask`. Has a `make_upload` fixture (line 20) that creates `FileUpload` instances directly. Imports `FileUpload` (line 9) and `cleanup_expired_uploads_task` (line 10).

### Data Flow
1. User uploads a file → `create_upload(user, file)` → validates via `validate_file()` → creates `FileUpload` record (READY or FAILED)
2. Downstream process consumes → `consume_upload(file_upload)` → atomic update to CONSUMED
3. Cleanup task → `cleanup_expired_uploads_task()` → deletes expired records + files from disk

### Documentation
Five `aikb/` files reference `FileUpload` or related names: `models.md`, `services.md`, `tasks.md`, `admin.md`, `architecture.md`. `CLAUDE.md` references `cleanup_expired_uploads_task` once (line 249).

## Key Files & Functions

### Source Files to Modify

| File | Lines | What Changes |
|------|-------|-------------|
| `uploads/models.py` | 58 lines | Class `FileUpload` → `IngestFile` (L8), `db_table` (L47), `verbose_name`/`verbose_name_plural` (L48-49), module docstring (L1) |
| `uploads/services/uploads.py` | 133 lines | Import (L9), function names `create_upload` → `create_ingest_file` (L54), `consume_upload` → `consume_ingest_file` (L102), all `FileUpload.*` references (L68, 74, 84, 90, 119, 121, 122), parameter name `file_upload` → `ingest_file` (L102, 110, 120, 126, 127, 130, 131, 132), docstrings, log messages, module docstring (L1) |
| `uploads/admin.py` | 32 lines | Import (L5), `@admin.register` (L8), class name `FileUploadAdmin` → `IngestFileAdmin` (L9), docstring (L10) |
| `uploads/tasks.py` | 67 lines | Explicit task `name=` string (L16), function name (L21), lazy import (L33), all `FileUpload.*` references (L33, 37, 47), docstring (L22), log messages (L41, 60-65) |
| `uploads/tests/test_services.py` | 141 lines | Import (L8-9), all `FileUpload.Status.*` references (L74, 89, 114, 117, 137), function import names (L9), test class names (`TestCreateUpload`, `TestConsumeUpload`), test docstrings |
| `uploads/tests/test_tasks.py` | 103 lines | Import (L9-10), fixture `make_upload` body (L21-35), all `FileUpload.*` references (L9, 23, 25, 35, 60, 74, 83, 101), test class name, test docstrings |

### Migration File to Create

A new migration `uploads/migrations/0002_rename_fileupload_ingestfile.py` (auto-generated or hand-crafted) with:
- `RenameModel(old_name="FileUpload", new_name="IngestFile")`
- `AlterModelTable` for `db_table` change (`file_upload` → `ingest_file`)
- `RenameIndex` for both indexes (old prefix `file_upload_*` → new prefix `ingest_file_*`)
- `AlterModelOptions` for `verbose_name` / `verbose_name_plural`

### Documentation Files to Update

| File | What Changes |
|------|-------------|
| `aikb/models.md` | `FileUpload` → `IngestFile` throughout (L26-27, 40, 63), status choices header, ER summary |
| `aikb/services.md` | Function names and references (L53-57) |
| `aikb/tasks.md` | Task name and references (L54-62) |
| `aikb/admin.md` | Class name and code block (L26-34) |
| `aikb/architecture.md` | Tree diagram (L64-68), background processing section (L134) |
| `CLAUDE.md` | Task reference on L249 |

### Files NOT Modified

| File | Reason |
|------|--------|
| `uploads/migrations/0001_initial.py` | Existing migrations are never edited |
| `uploads/__init__.py` | Empty file, no exports |
| `uploads/services/__init__.py` | Empty file, no exports |
| `uploads/apps.py` | App is still named `uploads`; `UploadsConfig` stays as-is |
| `conftest.py` | Only defines `user` fixture, no `FileUpload` references |
| `boot/settings.py` | Settings `FILE_UPLOAD_*` stay unchanged (describes config, not model) |
| `boot/urls.py` | No upload-related URL patterns |
| `aikb/conventions.md` | No direct `FileUpload` references |
| `aikb/specs-roadmap.md` | References "File upload infrastructure" (app name, not model name) |

## Technical Constraints

### Database Schema

1. **Single migration in history.** The `uploads` app has exactly one migration (`0001_initial.py`) that created the `FileUpload` model with `db_table = "file_upload"`. The rename migration will be `0002`.

2. **Auto-generated index names.** Django auto-named the indexes as `file_upload_user_id_c50e60_idx` and `file_upload_status_20c17f_idx`. These contain a hash suffix derived from the field names, not the table name. After `RenameModel`, Django will expect new index names with the `ingest_file_` prefix. `RenameIndex` operations are needed.

3. **No foreign keys from other models.** `FileUpload` is only referenced by `User` via the reverse FK. No other models have FKs pointing to it. This makes the rename zero-risk from a relational integrity standpoint.

4. **Django content types.** `RenameModel` automatically updates the `django_content_type` table (changing `model` from `fileupload` to `ingestfile`). This is handled by Django's migration framework.

5. **No data migration needed.** All data stays in place — this is purely a schema rename (table name, index names, content type).

### Migration Generation Strategy

Running `makemigrations` after renaming the model class and updating `db_table`/`verbose_name`/indexes will likely auto-detect the rename. However, Django's migration autodetector may:
- Generate a `RenameModel` + separate `AlterModelTable` + `AlterModelOptions`
- Or generate a `DeleteModel` + `CreateModel` if it doesn't detect the rename

The safest approach: rename the model class first, run `makemigrations`, then inspect the generated migration to ensure it uses `RenameModel` (not delete+create). If it doesn't detect the rename, manually craft the migration.

### Celery Task Name

The `@shared_task` decorator has an explicit `name="uploads.tasks.cleanup_expired_uploads_task"` string (L16 of `uploads/tasks.py`). This is independent of the Python function name — Celery uses this string for task routing and result tracking. It must be updated to `"uploads.tasks.cleanup_expired_ingest_files_task"`. Since there's no production deployment and tasks run eagerly in dev, there's no backward-compatibility concern.

### Test Dependencies

Tests use `pytest` with `@pytest.mark.django_db`. The `user` fixture comes from the root `conftest.py`. The `make_upload` fixture in `test_tasks.py` creates `FileUpload` instances directly (not via services). Both fixtures need updating to reference `IngestFile`.

## Pattern Analysis

### Model Naming Convention
The project follows PascalCase singular naming for models: `User`, `TimeStampedModel`, `MoneyField`. `IngestFile` follows this convention correctly. The `db_table` convention is snake_case: `user`, `file_upload` → `ingest_file`.

### Service Function Naming
Service functions use snake_case: `create_upload`, `consume_upload`, `validate_file`. The proposed `create_ingest_file` and `consume_ingest_file` follow this convention. `validate_file` stays unchanged (generic and appropriate).

### Task Naming
Tasks use snake_case with `_task` suffix: `cleanup_expired_uploads_task` → `cleanup_expired_ingest_files_task`. Follows the convention.

### Admin Naming
Admin classes use the pattern `{ModelName}Admin`: `UserAdmin`, `FileUploadAdmin` → `IngestFileAdmin`. Follows the convention.

### Similar Rename Patterns
No prior renames exist in this codebase. However, Django's `RenameModel` operation is well-documented and widely used. The `accounts.User` model uses `db_table = "user"` as an example of explicit table naming.

### Patterns to Follow
- `accounts/models.py` — model with explicit `db_table` and `Meta` class
- `accounts/admin.py` — simple admin registration pattern
- The existing `uploads/` structure itself is the pattern to follow — just with different names

### Patterns to Avoid
- Do NOT edit `0001_initial.py` — create a new migration
- Do NOT rename the `uploads/` directory or `UploadsConfig` — explicitly out of scope
- Do NOT rename `FILE_UPLOAD_*` settings — explicitly out of scope
- Do NOT rename the `uploads/services/uploads.py` module file — explicitly out of scope

## External Research

### Django `RenameModel` Operation
Django's `migrations.RenameModel(old_name, new_name)` handles:
- Renaming the database table (respects `db_table` if set)
- Updating `django_content_type` entries
- Updating internal migration state

When `db_table` is explicitly set (as it is here), `RenameModel` alone does **not** rename the actual database table — it only updates Django's internal state. The table rename happens via `AlterModelTable` (or by changing `db_table` in the model and letting `makemigrations` detect it).

**Important nuance:** If `db_table` was not explicitly set, `RenameModel` would rename the table automatically (from `uploads_fileupload` to `uploads_ingestfile`). But since `db_table = "file_upload"` is explicit, changing it to `"ingest_file"` requires a separate `AlterModelTable` operation in the migration.

### Django `RenameIndex` Operation
Available since Django 4.1. Syntax: `migrations.RenameIndex(model_name, new_name, old_name)`. The `old_name` values can be found in `0001_initial.py` (lines 75 and 78).

### `makemigrations` Behavior for Renames
When Django detects that a model has been renamed (class name changed, but fields are identical), it will prompt: "Did you rename the <app>.<OldModel> model to <NewModel>?" and generate a `RenameModel` operation. This interactive prompt works when run manually but requires `--no-input` consideration in scripts (where it defaults to delete+create — undesirable).

## Risk & Edge Cases

### Low Risk
1. **Zero external consumers.** No API endpoints, no external packages, no downstream FKs. All references are internal to the `uploads` app and `aikb/` docs.
2. **Zero production data.** No production database exists. The migration risk is purely development-environment.
3. **Fully reversible.** `migrate uploads 0001` will reverse the rename migration.

### Medium Risk
4. **Migration auto-detection.** `makemigrations` may not detect the rename and instead generate delete+create, which would lose any existing development data. **Mitigation:** Inspect the generated migration before applying it. If it uses `DeleteModel` + `CreateModel`, manually replace with `RenameModel` + `AlterModelTable` + `RenameIndex` + `AlterModelOptions`.
5. **Index name generation.** If the migration doesn't include explicit `RenameIndex` operations, the old index names will persist in the database while the model expects new names. This can cause `migrate` to fail or leave orphaned indexes. **Mitigation:** Verify index names in the generated migration.

### Edge Cases
6. **`related_name="uploads"` on the User FK.** After the rename, `user.uploads.all()` still works but is semantically misaligned. The discussions.md has an open thread recommending rename to `ingest_files`. This would require a `AlterField` in the migration. Since there are zero consumers of this reverse accessor, the cost is minimal either way.
7. **PEP 0003 dependency.** `PEPs/PEP_0003_extend_data_models/summary.md` references both `FileUpload` and `IngestFile`. After this PEP is implemented, PEP 0003's summary will have stale `FileUpload` references. This is acceptable — PEP 0003 is still in Proposed status and can be updated.
8. **Log message grep-ability.** If operators have log monitoring that greps for "upload" or "Upload", the new log messages ("Ingest file created", "Ingest file consumed") will not match. This is a non-issue for a development-only project.

### What Could Go Wrong
9. **Missed reference.** A `FileUpload` or `file_upload` string could be missed somewhere. **Mitigation:** Run a comprehensive grep after all changes and verify zero remaining references (excluding migrations and PEP files).
10. **Test fixture breakage.** The `make_upload` fixture in `test_tasks.py` creates `FileUpload` objects directly. If the import is missed, tests will fail with `ImportError`. **Mitigation:** Run the full test suite as a verification step.

## Recommendations

### Implementation Order

1. **Model first** — Rename class, update `Meta` (`db_table`, `verbose_name`, `verbose_name_plural`, indexes). This is the foundational change.
2. **Generate migration** — Run `makemigrations` and inspect output. Verify it uses `RenameModel`. Manually add `RenameIndex` operations if missing.
3. **Apply migration** — Run `migrate` and verify the table/indexes exist with new names.
4. **Services** — Rename functions, update imports, fix parameter names, update docstrings and log messages. Run `ruff check` after.
5. **Admin** — Rename class and imports. Quick and mechanical.
6. **Task** — Rename function, update `name=` string, update lazy imports, fix docstrings/log messages.
7. **Tests** — Update all imports, class names, fixture bodies, docstrings. Run `pytest uploads/tests/ -v` to verify.
8. **Documentation** — Update `aikb/` files and `CLAUDE.md`. This is purely cosmetic and risk-free.

### Things to Verify During Implementation

- After `makemigrations`: inspect migration for `RenameModel` (not `DeleteModel`+`CreateModel`)
- After `makemigrations`: verify both `RenameIndex` operations are present
- After `migrate`: verify table `ingest_file` exists and `file_upload` does not
- After all code changes: `grep -rn "FileUpload\|file_upload\|create_upload\|consume_upload\|cleanup_expired_uploads" --include="*.py" --exclude-dir=migrations --exclude-dir=PEPs` should return zero results
- After all code changes: `python manage.py check` passes
- After all code changes: `ruff check .` passes
- After all code changes: `pytest uploads/tests/ -v` — all 17 tests pass (16 existing + fixture rename verification)

### Open Question: `related_name`

The discussions.md open thread recommends renaming `related_name="uploads"` to `related_name="ingest_files"`. This research supports **option 1 (rename)** given:
- Zero current consumers of `user.uploads`
- The migration is trivial (one `AlterField` operation)
- It prevents a future rename with higher cost
- It aligns with the naming consistency goal of this PEP

However, this is a scope decision that should be resolved before planning.
