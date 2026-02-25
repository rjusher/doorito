# PEP 0002: Rename FileUpload to IngestFile

| Field | Value |
|-------|-------|
| **PEP** | 0002 |
| **Title** | Rename FileUpload to IngestFile |
| **Author** | Doorito Team |
| **Status** | Implementing |
| **Risk** | Medium |
| **Created** | 2026-02-25 |
| **Updated** | 2026-02-25 |
| **Related PEPs** | PEP 0001 (File Upload Infrastructure — the feature being renamed) |

---

## Problem Statement

The `uploads` app currently defines a model called `FileUpload`, which implies a simple file upload action. As Doorito evolves, uploaded files will serve as ingestion inputs — documents, spreadsheets, images, and data files that downstream processes parse, transform, or consume. The name `FileUpload` centers on the *mechanism* (uploading) rather than the *purpose* (ingesting content for processing).

This naming mismatch will compound as more features build on top of the upload infrastructure:
- Service functions like `create_upload` / `consume_upload` read as generic file-handling utilities rather than domain-oriented ingestion operations.
- The admin class `FileUploadAdmin` and task `cleanup_expired_uploads_task` carry the same mechanical framing.
- New developers (and AI agents) reading `FileUpload` won't immediately understand the model's role in a data-ingestion pipeline.

Renaming now — while the model is freshly introduced (PEP 0001) and has zero production data — is far cheaper than renaming later after foreign keys, API contracts, and downstream consumers accumulate.

## Proposed Solution

Rename the model and all related code artifacts from the `FileUpload` naming convention to `IngestFile`:

| Current Name | New Name |
|---|---|
| `FileUpload` (model) | `IngestFile` (model) |
| `FileUploadAdmin` (admin) | `IngestFileAdmin` (admin) |
| `file_upload` (db_table) | `ingest_file` (db_table) |
| `create_upload` (service) | `create_ingest_file` (service) |
| `consume_upload` (service) | `consume_ingest_file` (service) |
| `validate_file` (service) | `validate_file` (unchanged — generic and appropriate) |
| `cleanup_expired_uploads_task` (task) | `cleanup_expired_ingest_files_task` (task) |

Key components of the change:
1. **Model rename** — `FileUpload` → `IngestFile` with updated `db_table`, `verbose_name`, indexes, and `Meta`.
2. **Database migration** — Rename table from `file_upload` to `ingest_file`, rename indexes.
3. **Service function renames** — `create_upload` → `create_ingest_file`, `consume_upload` → `consume_ingest_file`.
4. **Admin rename** — `FileUploadAdmin` → `IngestFileAdmin`.
5. **Task rename** — `cleanup_expired_uploads_task` → `cleanup_expired_ingest_files_task`.
6. **Test updates** — All 17 existing tests updated to use new names.
7. **Documentation updates** — `aikb/` files, `CLAUDE.md`, and settings references updated.

The `uploads` app directory itself is **not** renamed in this PEP (see Out of Scope).

## Rationale

**Domain clarity over mechanical description.** The name `IngestFile` communicates that files uploaded into the system are inputs to be processed — not just blobs being stored. This aligns with the lifecycle already expressed in the status field (`pending → ready → consumed`), where "consumed" implies ingestion by a downstream process.

**Rename while cost is minimal.** PEP 0001 was just implemented. There are no production databases, no external API consumers, and no downstream models with foreign keys to `FileUpload`. The total blast radius is ~13 files with ~91 references — a manageable, well-scoped change.
<!-- Amendment 2026-02-25: Corrected reference count from ~50 to ~91 based on codebase grep analysis (see discussions.md) -->

**Convention alignment.** The name `IngestFile` follows the project's PascalCase singular model naming convention (`User`, `IngestFile`) and describes *what the entity is* rather than *how it got there*.

## Alternatives Considered

### Alternative 1: Keep FileUpload, rename later
- **Description**: Leave the current naming and defer the rename until a clearer domain model emerges.
- **Pros**: No work now; avoids premature naming decisions.
- **Cons**: Rename cost grows with every new FK, service call, and downstream consumer. The "right time" rarely comes — technical debt accrues silently.
- **Why rejected**: The model was just created with zero consumers. This is the lowest-cost window for renaming.

### Alternative 2: Rename the app directory from `uploads/` to `ingest/`
- **Description**: Rename both the model *and* the Django app directory to fully align naming.
- **Pros**: Complete naming consistency (`ingest.IngestFile`).
- **Cons**: Renaming a Django app directory is significantly more invasive — it affects `INSTALLED_APPS`, migration history, content types, admin URLs, import paths across the entire codebase, and potentially the `django_migrations` table. Much higher risk for marginal naming benefit.
- **Why rejected**: The model rename alone achieves the primary goal (domain-aligned naming). An app rename can be considered separately if needed, but the `uploads` app name is still accurate — the app *handles uploads* that produce `IngestFile` records.

### Alternative 3: Use UploadedFile or FileIngest
- **Description**: Choose a different target name instead of `IngestFile`.
- **Pros**: `UploadedFile` is a common Django convention; `FileIngest` puts "File" first for consistency with `FileUpload`.
- **Cons**: `UploadedFile` conflicts with Django's `django.core.files.uploadedfile.UploadedFile` — confusing for developers and autocomplete. `FileIngest` reads awkwardly as a noun ("a file ingest" vs. "an ingest file").
- **Why rejected**: `IngestFile` is the clearest noun form — "a file being ingested" — and avoids namespace conflicts.

## Impact Assessment

### Affected Components
- **Models**: `FileUpload` → `IngestFile` (uploads app)
- **Services**: `uploads/services/uploads.py` — `create_upload` → `create_ingest_file`, `consume_upload` → `consume_ingest_file`
- **Admin**: `FileUploadAdmin` → `IngestFileAdmin` (uploads app)
- **Tasks**: `cleanup_expired_uploads_task` → `cleanup_expired_ingest_files_task` (uploads app)
- **Tests**: `uploads/tests/test_services.py`, `uploads/tests/test_tasks.py` — all references updated
- **CLI**: None affected
- **API**: None (no API endpoints exist)

### Migration Impact
- **Database migration required**: Yes — `ALTER TABLE "file_upload" RENAME TO "ingest_file"` plus index renames.
- **Data migration needed**: No — pure schema rename, no data transformation.
- **Backward compatibility**: Breaking for any code importing `FileUpload` by name (all internal — no external consumers).

### Performance Impact
- **Query performance**: None — table rename is metadata-only in PostgreSQL.
- **Cache implications**: None.
- **Task queue implications**: The Celery task name string changes. Since there is no production deployment and tasks run eagerly in dev, this has no impact.

## Out of Scope

- **Renaming the `uploads/` app directory** — This is a higher-risk change involving `INSTALLED_APPS`, migration history, content types, and import paths. It may be proposed as a separate PEP if desired.
- **Renaming the `uploads/services/uploads.py` module** — The service module file name is fine; only the function names within it change.
- **Renaming settings** — `FILE_UPLOAD_MAX_SIZE`, `FILE_UPLOAD_TTL_HOURS`, and `FILE_UPLOAD_ALLOWED_TYPES` remain unchanged. These describe upload *configuration*, not the model, and are still accurate.
- **Changing the media storage path** — Files will continue to be stored under `media/uploads/%Y/%m/`. The storage path reflects the upload mechanism, not the model name.
- **Functional changes** — No behavior changes. This is a pure rename/refactor.

## Acceptance Criteria

- [ ] The `IngestFile` model exists in `uploads/models.py` with `db_table = "ingest_file"`
- [ ] No references to `FileUpload` or `FileUploadAdmin` remain in Python source files (excluding migrations)
- [ ] A database migration renames the table from `file_upload` to `ingest_file`
- [ ] `python manage.py check` passes with no errors
- [ ] `python manage.py migrate` applies the rename migration successfully
- [ ] All 17 existing tests pass with the new naming (`pytest uploads/tests/ -v`)
- [ ] `ruff check .` passes with no lint errors
- [ ] All `aikb/` documentation files reflect the new naming
- [ ] `CLAUDE.md` reflects the new naming where applicable

## Status History

| Date | From | To | Notes |
|------|------|----|-------|
| 2026-02-25 | — | Proposed | Initial creation |
| 2026-02-25 | Proposed | Implementing | Begin implementation |
