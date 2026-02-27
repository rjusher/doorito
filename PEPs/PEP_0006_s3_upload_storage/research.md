# PEP 0006: S3 Upload Storage — Research

| Field | Value |
|-------|-------|
| **PEP** | 0006 |
| **Summary** | [summary.md](summary.md) |
| **Plan** | [plan.md](plan.md) |

---

## Current State Analysis

### Storage Configuration

Both `Dev` and `Production` settings classes use `FileSystemStorage` as the default storage backend (`boot/settings.py` lines 206–213 and 236–243 respectively). They are declared independently (not inherited from `Base`), so each must be modified separately.

```python
# Identical in both Dev (line 206) and Production (line 236)
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
```

Media files are stored at `BASE_DIR / "media"` (line 112) with URL prefix `"media/"` (line 111). The `media/` directory is gitignored.

There is a duplicate `## Storage` section in `aikb/architecture.md` (lines 122–125 and 127–132) that should be consolidated during finalization.

### Upload Data Flow

1. **Entry point**: `create_upload_file(user, file, batch=None)` in `uploads/services/uploads.py` (line 76)
2. **Validation**: `validate_file(file)` checks size against `settings.FILE_UPLOAD_MAX_SIZE` (50 MB) and MIME type against `settings.FILE_UPLOAD_ALLOWED_TYPES`
3. **Hashing**: `compute_sha256(file)` reads file in 64 KB chunks, seeks back to start
4. **Storage**: `UploadFile.objects.create(file=file, ...)` — Django's `FileField.save()` delegates to the configured storage backend. The `upload_to="uploads/%Y/%m/"` parameter (model line 78) generates date-based paths
5. **Success**: Returns `UploadFile` with `status=STORED`, `sha256` set
6. **Failure**: Returns `UploadFile` with `status=FAILED`, `error_message` populated

The function currently does **not** use `transaction.atomic()` — the `UploadFile.objects.create()` call is auto-committed. There is no outbox event emission.

### File Deletion Flow

- **Manual**: `mark_file_deleted(upload_file)` calls `upload_file.file.delete(save=False)` (line 190), wrapped in `contextlib.suppress(FileNotFoundError)`
- **Cleanup task**: `cleanup_expired_upload_files_task` (uploads/tasks.py line 21) iterates expired files, calls `upload.file.delete(save=False)` (line 52), then bulk-deletes DB records

Both paths use Django's storage API (`file.delete()`), which correctly delegates to whatever backend is configured. **No code changes needed for cleanup**.

### Outbox Infrastructure

`emit_event()` in `common/services/outbox.py` (line 18) creates an `OutboxEvent` row and schedules delivery via `transaction.on_commit()`. The documented pattern (lines 28–32) requires callers to wrap both the state change and `emit_event()` in `transaction.atomic()`:

```python
with transaction.atomic():
    obj = create_something(...)
    emit_event("Something", str(obj.pk), "something.created", {...})
```

The `idempotency_key` auto-generates as `f"{aggregate_type}:{aggregate_id}"` (line 47). The `OutboxEvent` model has a `UniqueConstraint` on `(event_type, idempotency_key)` (common/models.py line 60).

---

## Key Files & Functions

### Files to Modify

| File | Lines | What Changes |
|------|-------|--------------|
| `requirements.in` | After line 32 | Add `django-storages[s3]>=1.14` |
| `boot/settings.py` | Lines 178 (after `FILE_UPLOAD_ALLOWED_TYPES`), 236–243 (`Production.STORAGES`) | Add S3 settings to `Base`; change `Production.STORAGES` default backend |
| `uploads/services/uploads.py` | Lines 111–128 (success path of `create_upload_file`) | Wrap in `transaction.atomic()`, add `emit_event()` call |
| `.env.example` | After line 51 | Add S3 environment variables |
| `docker-compose.yml` | Lines 8–12 (web), 36–38 (celery-worker), 48–50 (celery-beat) | Add S3 env vars to all services |

### Files Used as Reference (no modifications)

| File | Why |
|------|-----|
| `common/services/outbox.py` | `emit_event()` signature and transactional usage pattern (lines 18–74) |
| `common/utils.py` | `safe_dispatch()` context manager (lines 52–72), used by `emit_event` |
| `common/models.py` | `OutboxEvent` model, `UniqueConstraint` on `(event_type, idempotency_key)` (line 60) |
| `uploads/models.py` | `UploadFile` model, `file = FileField(upload_to="uploads/%Y/%m/")` (line 78), `Status` choices (lines 56–61) |
| `uploads/tasks.py` | `cleanup_expired_upload_files_task` — uses `file.delete(save=False)` (line 52), no changes needed |
| `uploads/tests/test_services.py` | Test patterns: `user` fixture, `SimpleUploadedFile`, `tmp_path`, `settings` override |
| `common/tests/test_services.py` | Test patterns: `OutboxEvent` assertions, `make_outbox_event` factory fixture |
| `conftest.py` | Root `user` fixture (lines 6–15) |
| `common/tests/conftest.py` | `make_outbox_event` factory fixture |

### Key Function Signatures

- `emit_event(aggregate_type, aggregate_id, event_type, payload, *, idempotency_key=None)` → `OutboxEvent`
- `create_upload_file(user, file, batch=None)` → `UploadFile`
- `UploadFile.file.url` → delegates to storage backend (local path in Dev, S3 URL in Production)

---

## Technical Constraints

### OutboxEvent Uniqueness

The `UniqueConstraint(fields=["event_type", "idempotency_key"])` means each `(event_type, idempotency_key)` pair must be unique. Since `create_upload_file` creates a new `UploadFile` with a UUID v7 PK each time, the auto-generated key `f"UploadFile:{uuid}"` will always be unique. No conflict risk.

### S3 File Overwrite Behavior

**Critical finding**: django-storages `S3Boto3Storage` defaults to `AWS_S3_FILE_OVERWRITE=True`. This means `Storage.get_available_name()` returns the filename as-is without deduplication. If two users upload `document.pdf` in the same month, the second upload **overwrites** the first on S3.

By contrast, `FileSystemStorage` defaults to deduplication — it appends random characters to avoid collision (e.g., `document_abc123.pdf`).

Since the `upload_to="uploads/%Y/%m/"` path contains no unique identifier (no UUID, no user ID), name collisions are realistic in production. The plan should explicitly set `AWS_S3_FILE_OVERWRITE=False` to preserve Django's deduplication behavior on S3.

### Transaction Semantics and File Storage

Django's `FileField.save()` writes to storage (disk or S3) as a side effect **outside** the database transaction. If `transaction.atomic()` wraps the DB write and it rolls back, the file remains on storage (orphaned). This is standard Django behavior and not specific to S3. The trade-off is accepted — orphaned files are cleaned up by TTL-based cleanup tasks.

The plan correctly wraps `UploadFile.objects.create()` + `emit_event()` in `transaction.atomic()`. If `emit_event()` fails (e.g., duplicate idempotency key due to a bug), both the `UploadFile` and `OutboxEvent` rows roll back, but the physical file persists. This is the intended pattern per `aikb/services.md`.

### S3 URL Generation

- `AWS_QUERYSTRING_AUTH=True` (default): `file.url` returns a pre-signed URL with time-limited access. URL changes on every call (new signature). Not suitable for caching or embedding in long-lived references.
- `AWS_QUERYSTRING_AUTH=False`: `file.url` returns a direct URL. Requires the bucket to allow public reads (via bucket policy or ACL).

The outbox event payload will contain `upload.file.url` at event creation time. If pre-signed URLs are used, the URL will eventually expire. Consumers should use the URL promptly or have their own S3 access.

### No Database Migrations

No model changes. `UploadFile.file` is a `FileField` — the storage backend is a runtime setting, not a schema attribute. Switching backends requires no migrations.

### Dependency Size

`django-storages[s3]` pulls in `boto3`, which in turn pulls in `botocore`. These are large packages (~100 MB installed). This increases Docker image size and dependency resolution time.

---

## Pattern Analysis

### Settings Pattern (`values.*` wrappers)

Existing Celery settings in `Base` class (boot/settings.py lines 120–136) use `values.Value(default, environ_name="...")` for environment variable binding:

```python
CELERY_BROKER_URL = values.Value(
    "sqla+postgresql://doorito:doorito@localhost:5432/doorito",
    environ_name="CELERY_BROKER_URL",
)
```

S3 settings should follow the same pattern. The plan correctly proposes using `values.Value`, `values.BooleanValue`, and `values.IntegerValue` with `environ_name` parameters.

**Note**: django-storages reads settings as global Django settings (e.g., `AWS_STORAGE_BUCKET_NAME`). The `values.*` wrappers resolve at class instantiation time, making the values available as plain attributes on the settings object. This is compatible with django-storages' `getattr(settings, 'AWS_STORAGE_BUCKET_NAME')` pattern.

### Storage Backend Class Path

The plan uses `storages.backends.s3boto3.S3Boto3Storage`. This path works but is a backwards-compatibility shim. The canonical path since django-storages 1.14 is `storages.backends.s3.S3Storage`. Both are functionally identical — `s3boto3.py` re-exports from `s3.py`. The shim path is more commonly seen in documentation and tutorials, so either is acceptable.

### Docker env_file + environment Pattern

The existing `docker-compose.yml` uses `env_file: .env` for shared variables and `environment:` list for service-specific overrides (lines 6–12). S3 vars should go in the `environment:` block with `${VAR:-default}` syntax, consistent with `DATABASE_URL` and `CELERY_BROKER_URL` patterns.

The `docker-compose.dev.yml` override should NOT receive S3 vars — Dev uses `FileSystemStorage`.

### Test Pattern for Upload Services

Existing tests in `uploads/tests/test_services.py` follow a consistent pattern:
- `@pytest.mark.django_db` class decorator
- `user` fixture from root `conftest.py`
- `tmp_path` and `settings` fixtures for isolated file storage
- `settings.MEDIA_ROOT = tmp_path` to redirect file writes
- `SimpleUploadedFile("name.pdf", b"content")` for test files
- Direct assertion on model fields

The new outbox event tests should follow the same pattern, adding `OutboxEvent` queries for assertions. The `make_outbox_event` fixture from `common/tests/conftest.py` is not needed here (we're testing that `create_upload_file` creates the event, not creating events directly).

### Outbox Event Pattern (`emit_event` in services)

Currently, `emit_event` is only called in test code. This would be its **first production usage** from a service function. The pattern is well-documented in `common/services/outbox.py` (lines 28–32):

```python
with transaction.atomic():
    obj = create_something(...)
    emit_event("Something", str(obj.pk), "something.created", {...})
```

The `upload` object must be created first (to have a PK), then `emit_event` is called within the same atomic block. The `transaction.on_commit()` hook ensures delivery dispatch happens only after the outer transaction commits.

---

## External Research

### django-storages

- **Latest version**: 1.14.6 (released April 2025)
- **Canonical backend path**: `storages.backends.s3.S3Storage` (preferred over `storages.backends.s3boto3.S3Boto3Storage`, which is a shim)
- **INSTALLED_APPS**: Not required. django-storages is a storage backend library, not a Django app
- **Django compatibility**: Classifiers list up to Django 5.1. Django 6.0 is not yet in classifiers, but the library only uses Django's storage API, which is stable. Practically compatible.
- **Configuration methods**: Global Django settings (e.g., `AWS_STORAGE_BUCKET_NAME`), or `STORAGES["default"]["OPTIONS"]` dict keys (e.g., `bucket_name`). Both work; global settings are simpler with `values.*` wrappers.
- **Key defaults**:
  - `AWS_QUERYSTRING_AUTH=True` (pre-signed URLs)
  - `AWS_QUERYSTRING_EXPIRE=3600` (1 hour)
  - `AWS_S3_FILE_OVERWRITE=True` (no dedup — **must override to False**)
  - `AWS_DEFAULT_ACL=None` (private, no ACL header sent)
  - `AWS_LOCATION=""` (no prefix)

### boto3

- Pulled in automatically by `django-storages[s3]` extra
- Minimum required: boto3 >= 1.4.4
- Credential chain: explicit keys → env vars → IAM roles → `~/.aws/credentials`
- No special version pinning needed; `django-storages[s3]>=1.14` handles it

### S3-Compatible Providers

The `AWS_S3_ENDPOINT_URL` setting enables any S3-compatible provider:
- **AWS S3**: No `endpoint_url` needed (default)
- **MinIO** (local dev): `http://localhost:9000`
- **Cloudflare R2**: `https://<account_id>.r2.cloudflarestorage.com`
- **DigitalOcean Spaces**: `https://<region>.digitaloceanspaces.com`
- **Backblaze B2**: `https://s3.<region>.backblazeb2.com`

---

## Risk & Edge Cases

### Risk 1: S3 File Overwrite (HIGH)

**Problem**: `AWS_S3_FILE_OVERWRITE` defaults to `True`. With `upload_to="uploads/%Y/%m/"`, two files named `report.pdf` uploaded in the same month would collide. The second silently overwrites the first on S3, corrupting data.

**Mitigation**: Set `AWS_S3_FILE_OVERWRITE=False` in the S3 settings. This makes `S3Storage.get_available_name()` append random characters, matching `FileSystemStorage` behavior.

### Risk 2: Pre-Signed URL Expiration in Outbox Event

**Problem**: When `AWS_QUERYSTRING_AUTH=True`, `upload.file.url` returns a pre-signed URL valid for `AWS_QUERYSTRING_EXPIRE` seconds (default 3600). If the outbox event is delivered late (e.g., retries, queue backlog), the URL in the payload may be expired.

**Mitigation**: Document this behavior. Consumers with direct S3 access can generate their own URLs using the `file_id` and known bucket/path. Alternatively, set `AWS_QUERYSTRING_EXPIRE` to a longer value or use `AWS_QUERYSTRING_AUTH=False` with a public bucket policy.

### Risk 3: Django 6.0 Compatibility Not Officially Declared

**Problem**: django-storages 1.14.6 lists compatibility up to Django 5.1. Django 6.0 support is not yet in classifiers.

**Mitigation**: The library uses only the `Storage` API, which has been stable since Django 4.2. The risk of breakage is low. Verify by running `python manage.py check` with both Dev and Production configurations after installation.

### Risk 4: Large Dependency Footprint

**Problem**: `boto3` + `botocore` add ~100 MB to the installed environment and Docker image.

**Mitigation**: Accepted trade-off. boto3 is the standard AWS SDK. No lighter alternative exists for S3 operations.

### Risk 5: Production Settings Require S3 Env Vars

**Problem**: `Production` class will use `S3Boto3Storage`, which requires `AWS_STORAGE_BUCKET_NAME` to be set. If missing, file operations will fail at runtime (not at startup).

**Mitigation**: Empty string defaults in `Base` prevent startup errors. Add a Django system check or startup validation in a future PEP if needed. Document required env vars clearly in `.env.example` and deployment docs.

### Edge Case: Failed Upload Does Not Emit Event

The `create_upload_file` function creates a `status=FAILED` record in the validation-error path (lines 91–107). The plan correctly places `emit_event` only in the success path. No event should be emitted for failed uploads. Tests should verify this.

### Edge Case: Chunked Upload Sessions

`complete_upload_session()` in `uploads/services/sessions.py` transitions an `UploadFile` from UPLOADING to STORED. The plan's `emit_event` is in `create_upload_file`, which sets status to STORED directly. Chunked uploads that go through the session lifecycle (UPLOADING → STORED via `complete_upload_session`) will **not** emit an outbox event. If events are needed for chunked uploads too, `complete_upload_session` would also need an `emit_event` call. This is noted as a potential gap — the PEP summary doesn't mention chunked uploads, so this may be intentionally deferred.

### Edge Case: `user=None`

`create_upload_file` accepts `user=None` (nullable FK on `UploadFile.uploaded_by`). The `emit_event` call should handle this gracefully. The payload should not include `uploaded_by` or should include `null` — the plan's proposed payload does not include a user field, which is correct.

---

## Recommendations

### 1. Add `AWS_S3_FILE_OVERWRITE=False` to Settings

The plan does not include this setting, but it is critical. Without it, filename collisions will silently overwrite files on S3. Add to `Base` class:
```python
AWS_S3_FILE_OVERWRITE = values.BooleanValue(
    False, environ_name="AWS_S3_FILE_OVERWRITE"
)
```

### 2. Use the Canonical Backend Path

Consider using `storages.backends.s3.S3Storage` instead of `storages.backends.s3boto3.S3Boto3Storage`. The latter is a compatibility shim. Both work identically, but the canonical path is cleaner. The shim path is more commonly documented, so this is a minor preference.

### 3. Document the Pre-Signed URL Expiration Issue

Add a note in `aikb/services.md` that the `url` field in the `file.stored` event payload may be a time-limited pre-signed URL when `AWS_QUERYSTRING_AUTH=True`. Consumers should use the URL promptly or have their own S3 credentials.

### 4. Verify Django 6.0 Compatibility After Installation

After adding `django-storages[s3]`, run `python manage.py check` with both `Dev` and `Production` configurations to confirm no issues with Django 6.0.

### 5. Consider `complete_upload_session` Event Gap

Decide whether chunked uploads (which reach STORED via `complete_upload_session()` rather than `create_upload_file()`) should also emit `file.stored` events. If so, add an `emit_event` call to `complete_upload_session` in `uploads/services/sessions.py`. If not, document this as intentional.

### 6. Implementation Order

The plan's implementation order is sound:
1. Dependencies first (install and verify import)
2. Settings configuration (no runtime effect until Production backend changes)
3. Service modification (emit_event)
4. Environment files (documentation and Docker)
5. Tests (verify everything)
6. Full test suite (regression check)

### 7. Things to Verify During Implementation

- `python -c "import storages; print(storages.__version__)"` after install
- `python -c "import boto3; print(boto3.__version__)"` after install
- `python manage.py check` with Dev configuration (should pass — no S3 needed)
- Existing upload tests still pass after adding `emit_event` (the `transaction.atomic()` wrapping changes the auto-commit behavior)
- Ruff linting passes (new imports, indentation changes)
