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

### PEP 0007: File Portal Pipeline
- **Implemented**: 2026-02-27
- **Commit(s)**: `ee97a2b`
- **Summary**: Implemented the end-to-end file portal pipeline connecting upload infrastructure, outbox events, and webhook delivery into a working system. Added a `WebhookEndpoint` model (`common/models.py`) for configuring webhook destinations with URL, HMAC-SHA256 secret, event type filtering, and active/inactive toggle. Created `common/services/webhook.py` with `compute_signature()` and `deliver_to_endpoint()` for HTTP POST delivery with `X-Webhook-Signature`, `X-Webhook-Event`, and `X-Webhook-Delivery` headers. Rewrote `process_pending_events()` with a three-phase approach (fetch with row locks, deliver via HTTP outside transactions, update results) supporting exponential backoff with jitter, `SoftTimeLimitExceeded` handling, and batch size of 20. Added an upload page at `/app/upload/` with drag-and-drop interface using Alpine.js and HTMX for file upload via `create_upload_file()` service. `create_upload_file()` now emits `file.stored` outbox events on success. Added `notify_expiring_files()` service and hourly `notify_expiring_files_task` to emit `file.expiring` events before TTL-based file cleanup, with idempotency via the outbox unique constraint. Fixed `retry_failed_events` admin action to reset `attempts=0`. Added `httpx>=0.27` dependency, `FILE_UPLOAD_EXPIRY_NOTIFY_HOURS` setting, `WebhookEndpointAdmin`, sidebar upload navigation links, and 39 new tests (119 total).

### PEP 0006: S3 Upload Storage
- **Implemented**: 2026-02-27
- **Commit(s)**: `9da4e00`
- **Summary**: Added S3-compatible media file storage for Production using `django-storages[s3]` (with `boto3`). The `Production` settings class now uses `S3Boto3Storage` as the default storage backend, while `Dev` retains `FileSystemStorage` for local development. All S3 settings (`AWS_STORAGE_BUCKET_NAME`, `AWS_S3_ENDPOINT_URL`, `AWS_S3_REGION_NAME`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_QUERYSTRING_AUTH`, `AWS_QUERYSTRING_EXPIRE`, `AWS_S3_FILE_OVERWRITE`) are configurable via environment variables using `values.*` wrappers, compatible with any S3-compatible provider (AWS S3, MinIO, R2, Spaces). Additionally, `create_upload_file` now emits a `file.stored` outbox event (via `emit_event`) containing the file's shareable URL and metadata (`file_id`, `original_filename`, `content_type`, `size_bytes`, `sha256`, `url`) when a file is successfully stored. S3 env vars are documented in `.env.example` and passed through in `docker-compose.yml` for all three services (web, celery-worker, celery-beat). Four new tests cover outbox event emission. No database migrations required.

### PEP 0004: Event Outbox Infrastructure
- **Implemented**: 2026-02-27
- **Commit(s)**: `6be51f9`
- **Summary**: Implemented a generic transactional outbox in the `common` app for reliable at-least-once event delivery. Added `OutboxEvent` model (`common/models.py`) with UUID v7 PK, aggregate/payload pattern (no FK to specific models), 3-state lifecycle (PENDING/DELIVERED/FAILED), retry tracking (`attempts`, `max_attempts`, `next_attempt_at`), `DjangoJSONEncoder` payload, partial index on pending events, and `UniqueConstraint(event_type, idempotency_key)` for deduplication. Created `common/services/outbox.py` with three service functions: `emit_event()` (writes event in caller's transaction, dispatches delivery via `transaction.on_commit()` wrapped in `safe_dispatch()`), `process_pending_events()` (batch-locked delivery with `select_for_update(skip_locked=True)`), and `cleanup_delivered_events()` (retention-based cleanup of terminal events). Added two Celery tasks: `deliver_outbox_events_task` (on-demand + 5-minute sweep) and `cleanup_delivered_outbox_events_task` (7-day retention, 6-hour crontab). Registered `OutboxEventAdmin` with monitoring fields and a `retry_failed_events` action. Added `OUTBOX_SWEEP_INTERVAL_MINUTES` and `OUTBOX_RETENTION_HOURS` settings. Wrote 49 tests covering models, services, and tasks (80 total across project).

### PEP 0005: Celery Beat Infrastructure
- **Implemented**: 2026-02-26
- **Commit(s)**: (uncommitted — to be included in finalization commit)
- **Summary**: Added `django-celery-beat` (v2.6–3.0) with the DatabaseScheduler to enable periodic task scheduling. Registered `django_celery_beat` in `INSTALLED_APPS`, applied its migrations (6 tables for schedule storage in PostgreSQL), and configured `CELERY_BEAT_SCHEDULER` to use the database scheduler. Added a `CELERY_BEAT_SCHEDULE` `@property` on the `Base` settings class that defines the initial schedule: `cleanup_expired_upload_files_task` running every 6 hours via crontab (at 00:00, 06:00, 12:00, 18:00 UTC), with the interval configurable through `CLEANUP_UPLOADS_INTERVAL_HOURS`. Added `celery-beat` role to `docker-entrypoint.sh`, a `celery-beat` service to both `docker-compose.yml` (production) and `docker-compose.dev.yml` (dev, in the `celery` profile), and a `beat:` process to `Procfile.dev`. Updated all relevant `aikb/` documentation files (`tasks.md`, `dependencies.md`, `deployment.md`, `architecture.md`, `specs-roadmap.md`) and `CLAUDE.md`. This unblocks PEP 0004 (Event Outbox Infrastructure) which requires periodic sweep scheduling.

### PEP 0003: Extend Data Models
- **Implemented**: 2026-02-26
- **Commit(s)**: `56767cc`
- **Summary**: Redesigned the uploads data layer from a single `IngestFile` model into four interconnected models supporting batched, chunked file uploads. Added `UploadBatch` (groups files into logical batches with idempotency support), `UploadFile` (redesigned from `IngestFile` with UUID v7 PK, SHA-256 content hash, JSONField metadata, SET_NULL user FK, and a richer status lifecycle: uploading→stored→processed/deleted/failed), `UploadSession` (one-to-one with `UploadFile`, tracks chunked upload progress with byte counters and part tracking), and `UploadPart` (individual chunks with UniqueConstraint on session+part_number). Added `uuid7()` wrapper in `common/utils.py` for Django-compatible UUID v7 generation. Implemented 11 service functions across two modules: `uploads/services/uploads.py` (file validation, creation, status transitions, batch management) and `uploads/services/sessions.py` (session creation, part recording, session completion). Updated the cleanup task to `cleanup_expired_upload_files_task`. Registered 4 admin classes with optimized list displays. Wrote 40 tests covering models, services, sessions, and tasks.

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
