# Implemented PEPs

This file tracks all PEPs that have been fully implemented. Once a PEP is implemented, its files are removed from `PEPs/` and only this reference and the git history remain.

## Log

<!-- Add entries in reverse chronological order (newest first) -->
<!-- Keep only the latest 10 entries here; archive older ones to PAST_YYYYMMDD.md -->
<!-- Template:
### PEP NNNN: Title
- **Implemented**: YYYY-MM-DD
- **Commit(s)**: `abc1234`, `def5678`
- **Summary**: Brief description of what was implemented and its impact.
-->

### PEP 0002: Rename FileUpload to IngestFile
- **Implemented**: 2026-02-25
- **Commit(s)**: `c0ab09a` (model, admin, migration), remaining changes uncommitted (to be included in finalization commit)
- **Summary**: Renamed the `FileUpload` model to `IngestFile` across the entire `uploads` app to better reflect the model's role as an ingestion input rather than a simple upload artifact. Renamed the database table from `file_upload` to `ingest_file` via a Django migration (`RenameModel`, `AlterModelTable`, `RenameIndex`, `AlterField`). Renamed service functions `create_upload` → `create_ingest_file` and `consume_upload` → `consume_ingest_file`. Renamed admin class `FileUploadAdmin` → `IngestFileAdmin`. Renamed Celery task `cleanup_expired_uploads_task` → `cleanup_expired_ingest_files_task`. Updated all 17 tests to use new naming. Updated all `aikb/` documentation files and `CLAUDE.md` to reflect the new names. The `uploads` app directory, settings (`FILE_UPLOAD_*`), media storage path, and `validate_file` function were intentionally left unchanged (out of scope). Pure rename/refactor with no behavior changes.

### PEP 0001: File Upload Infrastructure
- **Implemented**: 2026-02-25
- **Commit(s)**: (uncommitted — to be included in finalization commit)
- **Summary**: Introduced the `uploads` Django app providing temporary file upload infrastructure. Added a `FileUpload` model (inheriting `TimeStampedModel`) with status lifecycle tracking (pending → ready → consumed / failed), user FK, file storage at `media/uploads/%Y/%m/`, and metadata fields (original_filename, file_size, mime_type, error_message). Implemented three service functions: `validate_file` (size and MIME type validation against configurable limits), `create_upload` (validation + storage with automatic status transition), and `consume_upload` (atomic race-condition-safe consumption). Added `cleanup_expired_uploads_task` Celery task for TTL-based deletion of expired uploads (batched at 1000 records). Registered `FileUploadAdmin` with full CRUD, filtering, and search. Added 17 unit tests covering all services and task scenarios. Added three new settings: `FILE_UPLOAD_MAX_SIZE`, `FILE_UPLOAD_TTL_HOURS`, `FILE_UPLOAD_ALLOWED_TYPES`.

### Skeleton Extraction
- **Implemented**: 2026-02-24
- **Summary**: Stripped the original Inventlily project into a clean Django skeleton called Doorito. Removed all domain apps (catalog, selling, orders, core), multi-tenancy, RBAC, Redis, WebSockets, REST API, and domain-specific features. Retained Django + django-configurations, PostgreSQL, Celery (Postgres broker), WhiteNoise, Tailwind CSS v4, HTMX + Alpine.js, Click CLI, Docker Compose, PEPs, and aikb systems.
