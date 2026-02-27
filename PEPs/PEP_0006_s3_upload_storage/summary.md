# PEP 0006: S3 Upload Storage

| Field | Value |
|-------|-------|
| **PEP** | 0006 |
| **Title** | S3 Upload Storage |
| **Author** | Doorito Team |
| **Status** | Proposed |
| **Risk** | Medium |
| **Created** | 2026-02-27 |
| **Updated** | 2026-02-27 |
| **Related PEPs** | PEP 0003 (Upload Infrastructure) |
| **Depends On** | — |
| **Enables** | — |

---

## Problem Statement

Doorito's upload infrastructure (PEP 0003) currently stores all uploaded files on the local filesystem at `media/uploads/%Y/%m/`. This is fine for single-server development, but has significant limitations for production:

- **No horizontal scaling**: Files on one server's disk are not accessible from other application instances behind a load balancer.
- **No durability guarantees**: Local disk has no built-in redundancy — a disk failure loses all uploads.
- **No CDN integration**: Serving files directly from the app server is slow for end users and increases server load.
- **Container incompatibility**: Docker containers use ephemeral storage by default. Files are lost on container restart unless a persistent volume is mounted, and even then, volume sharing across multiple containers is fragile.
- **No lifecycle management**: No automatic expiration, archival, or tiered storage for old uploads.

The `STORAGES["default"]` backend is `FileSystemStorage` in both `Dev` and `Production` configurations. There is no S3 or cloud storage integration.

## Proposed Solution

Replace the default file storage backend for uploads with an S3-compatible storage backend using **django-storages[s3]** (which wraps `boto3`). This enables any S3-compatible provider: AWS S3, MinIO (self-hosted), DigitalOcean Spaces, Backblaze B2, Cloudflare R2, etc.

Additionally, wire the upload services into the existing OutboxEvent infrastructure so that when a file reaches `STORED` status, an outbox event is emitted containing the file's full shareable S3 URL. This enables downstream webhook consumers (e.g., external systems with access to the same bucket) to receive notification with a direct link to the stored file.

### Key Components

1. **New dependency**: Add `django-storages[s3]` and `boto3` to `requirements.in`.
2. **S3 storage backend configuration**: Add `S3Boto3Storage` as the `"default"` storage backend in the `Production` settings class, configured via environment variables (`AWS_STORAGE_BUCKET_NAME`, `AWS_S3_ENDPOINT_URL`, `AWS_S3_REGION_NAME`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`).
3. **Dev stays on local filesystem**: The `Dev` class retains `FileSystemStorage` so development works without any S3 dependency. Optionally allow overriding via env vars for local MinIO testing.
4. **Upload path prefix**: Keep the existing `uploads/%Y/%m/` upload path structure as S3 key prefixes.
5. **Settings wiring**: S3 configuration values use `values.*` wrappers from `django-configurations` with sensible defaults and environment variable overrides, consistent with the existing settings pattern.
6. **URL generation settings**: Configure `AWS_QUERYSTRING_AUTH` (pre-signed URLs for private buckets vs direct URLs for public buckets) and `AWS_QUERYSTRING_EXPIRE` (pre-signed URL expiration time in seconds) to control how shareable URLs are generated.
7. **File overwrite protection**: Set `AWS_S3_FILE_OVERWRITE=False` to preserve Django's filename deduplication behavior on S3 (matching `FileSystemStorage`'s default). Without this, files with the same name in the same month silently overwrite each other.
8. **Outbox event on file stored**: Emit an `OutboxEvent` (event type `file.stored`) from `create_upload_file` when a file is successfully stored, including the file's shareable URL (`upload_file.file.url`) in the event payload. This leverages the existing outbox infrastructure (PEP 0004) to enable webhook-based notifications to external systems. Note: when `AWS_QUERYSTRING_AUTH=True`, the URL is a time-limited pre-signed URL captured at emission time.

### From the user's perspective

- **Development**: No change. Files are stored locally as before.
- **Production**: Upload files are stored in the configured S3 bucket instead of on the local filesystem. Django's storage API is the abstraction layer — the `UploadFile.file` FileField, the upload services, and the cleanup tasks all work unchanged because they use `file.delete()`, `file.save()`, etc., which delegate to the configured storage backend.

## Rationale

- **django-storages is the standard**: It is the most widely used Django library for cloud storage backends, well-maintained, and already supports S3-compatible APIs via `boto3`. It integrates directly with Django's `STORAGES` setting introduced in Django 4.2.
- **S3-compatible (not S3-only)**: By using `AWS_S3_ENDPOINT_URL`, the same configuration works for AWS S3, MinIO, R2, Spaces, and other S3-compatible providers — no vendor lock-in.
- **Minimal code changes**: Django's storage API abstraction means existing code (`FileField`, `file.delete()`, `file.save()`) does not need modification. The change is primarily in settings and dependencies.
- **Consistent with architecture**: The project already uses `django-configurations` with `values.*` for environment-driven config. Adding S3 settings follows the same pattern.

## Alternatives Considered

### Alternative 1: Custom storage backend wrapping `boto3` directly

- **Description**: Write a custom Django storage backend class that calls `boto3` directly, without using `django-storages`.
- **Pros**: No additional dependency; full control over behavior.
- **Cons**: Reimplements well-tested logic (multipart upload, retry, signing, streaming). Significant maintenance burden. Missing edge-case handling that `django-storages` has solved over years.
- **Why rejected**: `django-storages` is mature, actively maintained, and handles the complexity of S3 interactions. Reimplementing it would violate the "don't reinvent the wheel" principle.

### Alternative 2: Use Django's built-in `FileSystemStorage` with a network-mounted volume (NFS/EFS)

- **Description**: Mount an NFS or EFS volume at `media/` so all containers share the same filesystem.
- **Pros**: Zero code changes. Works with existing `FileSystemStorage`.
- **Cons**: NFS is slower for random I/O. EFS costs more than S3 for storage-heavy workloads. No CDN integration. No object lifecycle policies. Adds infrastructure complexity (mount points, availability zones, permissions). Doesn't work well with Kubernetes or serverless.
- **Why rejected**: Adds infrastructure complexity without the benefits of object storage (durability, CDN, lifecycle policies). S3 is the industry standard for file storage in cloud deployments.

### Alternative 3: Use `django-storages` with Google Cloud Storage or Azure Blob

- **Description**: Use a GCS or Azure backend instead of S3.
- **Pros**: Native integration with respective cloud providers.
- **Cons**: Vendor-specific. S3 API is the de-facto standard — even GCS and Azure offer S3-compatible gateways. Choosing S3 keeps options open.
- **Why rejected**: S3-compatible API is the most portable choice. If a project runs on GCP or Azure later, S3-compatible gateways or a backend swap in settings is all that's needed. Not worth coupling to a specific cloud from the start.

## Impact Assessment

### Affected Components

- **Settings**: `boot/settings.py` — add S3 storage configuration to `Production` (and optionally `Dev`)
- **Dependencies**: `requirements.in` — add `django-storages[s3]`
- **Services**: `uploads/services/uploads.py` — add `emit_event` call in `create_upload_file` to emit a `file.stored` outbox event with the shareable URL when a file is successfully stored. `uploads/services/sessions.py` — no changes required.
- **Tasks**: No changes required. `uploads/tasks.py` uses `upload.file.delete(save=False)` which delegates to the storage backend.
- **Models**: No changes required. `UploadFile.file` is a `FileField` which uses the default storage backend. The shareable URL is generated by `file.url` (delegated to the storage backend — `S3Boto3Storage` generates pre-signed or direct URLs depending on `AWS_QUERYSTRING_AUTH`).
- **Admin**: No changes required.
- **CLI**: No changes required.

### Migration Impact

- **Database migrations required?** No. No model changes.
- **Data migration needed?** No for new deployments. Existing files on local filesystem would need manual migration to S3 for in-place upgrades (out of scope for this PEP).
- **Backward compatibility**: Non-breaking. Dev environment is unchanged. Production requires new environment variables.

### Performance Impact

- **Upload latency**: Slightly higher for S3 vs local disk, but negligible for typical file sizes. Boto3 handles multipart uploads automatically for large files.
- **Download/serving**: Can be faster if an S3 CDN or CloudFront is placed in front. Even without CDN, S3 serves directly without consuming app server bandwidth.
- **Task queue**: No impact. Cleanup tasks use the same storage API.

## Out of Scope

- **Pre-signed URLs for direct browser-to-S3 uploads** — Deferred to a future PEP. This PEP routes uploads through Django (server-side) as they do today.
- **CDN configuration** (CloudFront, etc.) — Infrastructure concern, not application code.
- **Migrating existing local files to S3** — Operational task, not part of this PEP.
- **Static file storage on S3** — Static files stay on WhiteNoise. Only media/upload files move to S3.
- **Per-model custom storage backends** — All uploads use the single `default` storage backend. Custom per-field backends are not needed at this stage.
- **S3 object lifecycle policies** (auto-delete, transition to Glacier) — Configured in the S3 bucket directly, not in Django.

## Acceptance Criteria

- [ ] `django-storages[s3]` and `boto3` are listed in `requirements.in` and compiled into `requirements.txt`
- [ ] `Production` settings class configures `S3Boto3Storage` as the `"default"` storage backend via `STORAGES`
- [ ] All S3 settings (`AWS_STORAGE_BUCKET_NAME`, `AWS_S3_ENDPOINT_URL`, `AWS_S3_REGION_NAME`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_FILE_OVERWRITE`) are configurable via environment variables using `values.*` wrappers
- [ ] `Dev` settings class retains `FileSystemStorage` as the default backend (no S3 required for development)
- [ ] `python manage.py check` passes with both `Dev` and `Production` configurations
- [ ] Existing upload services (`create_upload_file`, `mark_file_deleted`) work without code changes (they use Django's storage API)
- [ ] Existing cleanup task (`cleanup_expired_upload_files_task`) works without code changes
- [ ] S3 URL generation settings (`AWS_QUERYSTRING_AUTH`, `AWS_QUERYSTRING_EXPIRE`) are configurable via environment variables
- [ ] `create_upload_file` emits an `OutboxEvent` with event type `file.stored` containing the file's shareable URL in the payload when a file is successfully stored
- [ ] The `file.stored` outbox event payload includes at minimum: `file_id`, `original_filename`, `content_type`, `size_bytes`, `sha256`, and `url` (the shareable link)
- [ ] `.env.example` is updated with the new S3 environment variables (commented out with descriptions)
- [ ] `aikb/` documentation is updated to reflect the new storage configuration
- [ ] Docker environment supports the new S3 env vars (documented in `docker-compose.yml` or `.env.example`)

## Status History

| Date | From | To | Notes |
|------|------|----|-------|
| 2026-02-27 | — | Proposed | Initial creation |
<!-- Amendment 2026-02-27: Added AWS_S3_FILE_OVERWRITE setting, pre-signed URL note, and renumbered key components per discussions.md resolutions -->
