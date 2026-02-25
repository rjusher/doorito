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

### PEP 0001: File Upload Infrastructure
- **Implemented**: 2026-02-25
- **Commit(s)**: (uncommitted — to be included in finalization commit)
- **Summary**: Introduced the `uploads` Django app providing temporary file upload infrastructure. Added a `FileUpload` model (inheriting `TimeStampedModel`) with status lifecycle tracking (pending → ready → consumed / failed), user FK, file storage at `media/uploads/%Y/%m/`, and metadata fields (original_filename, file_size, mime_type, error_message). Implemented three service functions: `validate_file` (size and MIME type validation against configurable limits), `create_upload` (validation + storage with automatic status transition), and `consume_upload` (atomic race-condition-safe consumption). Added `cleanup_expired_uploads_task` Celery task for TTL-based deletion of expired uploads (batched at 1000 records). Registered `FileUploadAdmin` with full CRUD, filtering, and search. Added 17 unit tests covering all services and task scenarios. Added three new settings: `FILE_UPLOAD_MAX_SIZE`, `FILE_UPLOAD_TTL_HOURS`, `FILE_UPLOAD_ALLOWED_TYPES`.

### Skeleton Extraction
- **Implemented**: 2026-02-24
- **Summary**: Stripped the original Inventlily project into a clean Django skeleton called Doorito. Removed all domain apps (catalog, selling, orders, core), multi-tenancy, RBAC, Redis, WebSockets, REST API, and domain-specific features. Retained Django + django-configurations, PostgreSQL, Celery (Postgres broker), WhiteNoise, Tailwind CSS v4, HTMX + Alpine.js, Click CLI, Docker Compose, PEPs, and aikb systems.
