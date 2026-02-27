# PEP 0006: S3 Upload Storage — Discussions

| Field | Value |
|-------|-------|
| **PEP** | 0006 |
| **Summary** | [summary.md](summary.md) |
| **Plan** | [plan.md](plan.md) |

---

## Resolved Questions

### Q: Should `AWS_S3_FILE_OVERWRITE` be set to `False`?
- **Resolved**: 2026-02-27
- **Answer**: Yes. Add `AWS_S3_FILE_OVERWRITE = values.BooleanValue(False, environ_name="AWS_S3_FILE_OVERWRITE")` to the `Base` settings class alongside the other S3 settings.
- **Rationale**: django-storages defaults `AWS_S3_FILE_OVERWRITE=True`, which means `Storage.get_available_name()` returns filenames as-is without deduplication. Since `UploadFile.file` uses `upload_to="uploads/%Y/%m/"` (no UUID or user ID in the path), two files with the same name uploaded in the same month would silently overwrite each other on S3. `FileSystemStorage` always deduplicates by appending a random suffix. Setting `AWS_S3_FILE_OVERWRITE=False` preserves this deduplication behavior on S3. One-line addition with no downside. Also add it to `.env.example` and `docker-compose.yml`.

### Q: Which backend class path — `S3Boto3Storage` (shim) or `S3Storage` (canonical)?
- **Resolved**: 2026-02-27
- **Answer**: Use `storages.backends.s3boto3.S3Boto3Storage` (the shim path).
- **Rationale**: Both paths are functionally identical — `s3boto3.py` re-exports from `s3.py`. The shim path `S3Boto3Storage` is far more commonly seen in Django documentation, tutorials, StackOverflow answers, and existing codebases. Using the more recognizable path reduces friction for developers who encounter it. If django-storages ever deprecates the shim, it would be a simple one-line path change. Low-impact decision, not worth bikeshedding.

### Q: Should the `file.stored` event payload include `batch_id`?
- **Resolved**: 2026-02-27
- **Answer**: No. Keep the payload minimal: `file_id`, `original_filename`, `content_type`, `size_bytes`, `sha256`, `url`.
- **Rationale**: The batch relationship is a concern of the upload domain, not the storage event. Consumers who need the batch can look up the file by `file_id`. Including `batch_id` would couple the event schema to the batch concept, which not all upload paths use (single-file uploads have `batch=None`). If a `batch.complete` event is needed in the future, it can be emitted separately from `finalize_batch`. Keeping payloads lean also avoids bloating the outbox table.

### Q: Does `MEDIA_URL` need to change for S3?
- **Resolved**: 2026-02-27
- **Answer**: No. `MEDIA_URL` remains `"media/"` in `Base`.
- **Rationale**: When `S3Boto3Storage` is active, `file.url` generates URLs from the S3 bucket URL (and optionally signs them), completely ignoring `MEDIA_URL`. `MEDIA_URL` is only used by `FileSystemStorage` to construct local URLs. Leaving it unchanged means Dev still works. If both backends were active simultaneously (e.g., a custom per-field backend), `MEDIA_URL` would only apply to the filesystem-backed fields. No change needed.

### Q: Will existing tests break due to `transaction.atomic()` + `emit_event` changes?
- **Resolved**: 2026-02-27
- **Answer**: No. Existing tests are unaffected.
- **Rationale**: pytest-django wraps `@pytest.mark.django_db` tests in a transaction that is rolled back at the end. The `transaction.atomic()` block in `create_upload_file` creates a savepoint within this test transaction. When the savepoint releases, `on_commit` hooks (used by `emit_event` to dispatch the delivery task) are not fired — they only fire when the outermost transaction commits, which never happens in tests. So: (1) `OutboxEvent` rows are created in the DB (visible within the test), (2) no delivery task is triggered, (3) all rows are rolled back after the test. Existing tests that don't query `OutboxEvent` see no behavioral difference.

### Q: Can `Production` configuration be verified with `manage.py check` locally?
- **Resolved**: 2026-02-27
- **Answer**: No, not reliably. The acceptance criterion "python manage.py check passes with both Dev and Production configurations" is aspirational for local development. Verification should focus on `Dev` locally; `Production` check belongs in CI/staging.
- **Rationale**: The `Production` class inherits `SECRET_KEY = values.SecretValue()` from `Base`, which raises `ValueError` if `DJANGO_SECRET_KEY` is not set. It also requires `ALLOWED_HOSTS` and `DATABASE_URL`. Running `manage.py check` with `DJANGO_CONFIGURATION=Production` locally requires setting all of these env vars. The plan correctly only verifies Dev locally (Step 2c, Final Verification). The summary acceptance criterion should be read as: Dev is verified locally; Production is verified in a deployed environment. No plan amendment needed — the plan already does the right thing.

### Q: Does `django-storages` need to be added to `INSTALLED_APPS`?
- **Resolved**: 2026-02-27
- **Answer**: No. `django-storages` is a storage backend library, not a Django app.
- **Rationale**: `S3Boto3Storage` is used purely as a storage backend class referenced in `STORAGES["default"]["BACKEND"]`. It has no models, migrations, management commands, or template tags that require app registration. The plan correctly omits any `INSTALLED_APPS` change. Confirmed via django-storages documentation.

### Q: Should `AWS_DEFAULT_ACL` or `AWS_LOCATION` be exposed as configurable settings?
- **Resolved**: 2026-02-27
- **Answer**: No. Omit them from the plan. The defaults are correct for most setups.
- **Rationale**: `AWS_DEFAULT_ACL=None` (no ACL header sent, relies on bucket policy) is the correct default — explicitly setting ACLs is discouraged by AWS for new buckets. `AWS_LOCATION=""` (no key prefix) is correct because `upload_to="uploads/%Y/%m/"` already provides path structure. Operators who need multi-environment prefixes (e.g., `staging/`) or custom ACLs can add these settings themselves without a plan change. Keeping the settings surface area minimal reduces configuration complexity. These can always be added later if a use case arises.

### Q: Is there a risk of orphaned files if `emit_event()` raises inside the `transaction.atomic()` block?
- **Resolved**: 2026-02-27
- **Answer**: Theoretically yes, but the risk is negligible and consistent with accepted Django behavior.
- **Rationale**: `FileField.save()` writes to storage (disk/S3) as a side effect outside the database transaction. If `emit_event()` raises (e.g., a database constraint violation), `transaction.atomic()` rolls back both the `UploadFile` and `OutboxEvent` rows, but the physical file persists on storage (orphaned — no DB record points to it). However, this scenario is practically impossible: the `idempotency_key` is `"UploadFile:{uuid7}"` where the UUID is freshly generated, so a duplicate key constraint violation cannot occur. The only failure mode would be a database connectivity issue, which would also prevent the `UploadFile.objects.create()` from succeeding in the first place. This is the same trade-off documented in `aikb/services.md` and `research.md` §Transaction Semantics. No mitigation needed.

### Q: Is `django-storages[s3]>=1.14` compatible with Django 6.0?
- **Resolved**: 2026-02-27
- **Answer**: Practically yes, though not officially declared. Safe to proceed.
- **Rationale**: django-storages 1.14.6 (April 2025) officially lists compatibility up to Django 5.1. However, the library only uses Django's `Storage` API (`STORAGES` dict, `Storage.save()`, `Storage.url()`, etc.), which has been stable since Django 4.2 and unchanged in Django 6.0. The plan includes `python manage.py check` verification after installation (Step 2c), which will catch any import or configuration errors. If incompatibility surfaces, it would be a simple version bump or patch. Risk 3 in `research.md` covers this analysis. The `>=1.14` floor is correct — no upper bound needed since `requirements.txt` pins exact versions via hash locking.

## Design Decisions

### Decision: S3 settings in `Base` class, not `Production`
- **Date**: 2026-02-27
- **Context**: S3 configuration values (`AWS_STORAGE_BUCKET_NAME`, etc.) need to be accessible in Production for the S3 backend. They could be placed in the `Production` class or in the `Base` class.
- **Decision**: Place all S3 settings in `Base` with empty-string/sensible defaults. Only `Production.STORAGES` references the S3 backend.
- **Alternatives rejected**:
  - **Settings in `Production` only**: Would break the `values.*` pattern. The existing convention (Celery settings, file upload settings) puts all `values.*` definitions in `Base`, even if only Production uses certain values. Keeping S3 settings in `Base` is consistent and allows Dev to override them for local MinIO testing.
  - **Settings in `STORAGES["default"]["OPTIONS"]`**: django-storages supports passing settings as `OPTIONS` keys (e.g., `"bucket_name"` instead of `AWS_STORAGE_BUCKET_NAME`). But this doesn't work with `values.*` wrappers (OPTIONS is a plain dict, not a class attribute). Global settings via `values.*` is the project's established pattern.

### Decision: `emit_event` only in the `create_upload_file` success path
- **Date**: 2026-02-27
- **Context**: The plan places `emit_event("file.stored", ...)` inside `create_upload_file()` after the `UploadFile.objects.create()` call with `status=STORED`. The failure path (validation error, `status=FAILED`) does not emit an event.
- **Decision**: Correct. Only emit on the STORED success path. Failed uploads should not generate outbox events.
- **Alternatives rejected**:
  - **Emit on failure too** (e.g., `file.upload_failed`): Adds complexity for no clear consumer use case. Failed uploads are an internal concern. If failure notifications are needed later, they can be added in a separate PEP.

### Decision: Pre-signed URL snapshot in outbox event payload
- **Date**: 2026-02-27
- **Context**: When `AWS_QUERYSTRING_AUTH=True` (default), `upload.file.url` returns a pre-signed URL with a time-limited signature (default 3600s). This URL is captured at event emission time and embedded in the `file.stored` outbox event payload. If the event is consumed after the URL expires (e.g., outbox backlog, consumer downtime), the URL will be invalid.
- **Decision**: Accept this behavior and document it. The outbox sweep interval is 5 minutes and events are typically delivered within seconds of emission. The 3600s default expiration provides ample buffer. Consumers with direct S3 access can reconstruct URLs from the `file_id` and known bucket/path convention (`uploads/%Y/%m/`). Adding URL regeneration logic to the event system would over-engineer this feature.
- **Alternatives rejected**:
  - **Store S3 key instead of URL**: Breaks the abstraction. The payload should be backend-agnostic. In Dev (FileSystemStorage), there is no S3 key.
  - **Regenerate URL at delivery time**: Would require the outbox delivery service to know about storage backends. Violates separation of concerns.
  - **Always use `AWS_QUERYSTRING_AUTH=False`**: Requires public bucket policy, which is a security trade-off the operator should decide, not the application.

### Decision: Minimal S3 settings surface area
- **Date**: 2026-02-27
- **Context**: django-storages exposes many optional settings beyond the ones in the plan (`AWS_DEFAULT_ACL`, `AWS_LOCATION`, `AWS_S3_OBJECT_PARAMETERS`, `AWS_S3_CUSTOM_DOMAIN`, `AWS_S3_URL_PROTOCOL`, `AWS_S3_VERIFY`, etc.). The plan exposes 8 settings. The question is whether to expose more.
- **Decision**: Expose only the 8 settings in the plan: `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_ENDPOINT_URL`, `AWS_S3_REGION_NAME`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_QUERYSTRING_AUTH`, `AWS_QUERYSTRING_EXPIRE`, `AWS_S3_FILE_OVERWRITE`. These cover the essential configuration for any S3-compatible provider.
- **Alternatives rejected**:
  - **Expose all django-storages settings**: Bloats the settings file and `.env.example` with rarely-used options. Operators can add any additional setting to `boot/settings.py` themselves — django-storages reads them from Django settings globally. No code change needed to add a setting later.
  - **Expose `AWS_S3_CUSTOM_DOMAIN` for CDN**: CDN configuration is explicitly out of scope per the summary. Can be added as a one-liner when needed.

## Open Threads

### Thread: Should `complete_upload_session` also emit a `file.stored` event?
- **Raised**: 2026-02-27
- **Context**: There are two paths to `status=STORED`:
  1. `create_upload_file()` — single-shot upload, sets STORED directly (event emitted per plan)
  2. `complete_upload_session()` — chunked upload, transitions UPLOADING → STORED via `UploadFile.objects.filter(...).update(status=STORED)` (no event emitted)

  The plan only addresses path #1. Chunked uploads completing via path #2 will silently reach STORED without an outbox event. This means consumers relying on `file.stored` events will not be notified about chunked uploads.

  Additionally, `complete_upload_session` uses `.update()` (not `.save()`), so the UploadFile instance isn't refreshed — to emit an event, the code would need to `refresh_from_db()` first to get `file.url`.
- **Options**:
  - **A: Defer to a future PEP** — Keep scope narrow. Document that `file.stored` events are only emitted for single-shot uploads. Add chunked upload events in a follow-up PEP.
  - **B: Amend plan to include both paths** — Add `emit_event` to `complete_upload_session()` in `uploads/services/sessions.py`. Requires refactoring the `.update()` to `.save()` or adding a `refresh_from_db()` + `emit_event` after the update, within the existing `@transaction.atomic`.
  - **C: Extract a shared `_emit_file_stored_event(upload_file)` helper** — Both paths call it. Keeps the event emission logic DRY.
- **Analysis** (2026-02-27): Code review of `complete_upload_session()` (`uploads/services/sessions.py:82–119`) confirms the gap. The function is already wrapped in `@transaction.atomic`, so adding `emit_event` inside it is structurally easy. However, the `.update()` call at line 113–116 does not return the updated instance — a `session.file.refresh_from_db()` would be needed to get `file.url`. Option B would add ~8 lines of code. Option A keeps this PEP focused on the S3 storage backend (its primary purpose) and treats outbox events as a secondary enhancement. The `file.stored` event feature is already additive — adding it for one path is better than adding it for zero paths.
- **Recommendation**: **Option A** — Defer. Add a note to the `aikb/services.md` update documenting that `file.stored` events are emitted only for single-shot uploads via `create_upload_file`, not for chunked uploads via `complete_upload_session`. This creates a clear follow-up item.
- **Status**: Awaiting input — confirm whether to defer or include chunked upload events in this PEP.
<!-- Review: Defer to future PEP -->

### Thread: Should Production validate that S3 env vars are set at startup?
- **Raised**: 2026-02-27
- **Context**: The plan sets all S3 settings to empty-string defaults in `Base`. When `Production` is used with `S3Boto3Storage` as the default backend but without `AWS_STORAGE_BUCKET_NAME` set, `python manage.py check` will pass (Django doesn't verify storage connectivity). The first file upload will fail at runtime with a confusing boto3 error.
- **Options**:
  - **A: Accept and document** — The `.env.example` and deployment docs clearly list the required env vars. Operators who forget will see clear boto3 errors in logs. This is consistent with how `DATABASE_URL` works (no startup validation, fails at first query).
  - **B: Add a Django system check** — Register a custom check in `common/checks.py` that verifies `AWS_STORAGE_BUCKET_NAME` is non-empty when `STORAGES["default"]["BACKEND"]` is `S3Boto3Storage`. This catches misconfiguration at `manage.py check` time.
  - **C: Use `values.SecretValue`** — For `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`, use `values.SecretValue()` instead of `values.Value("")`. This raises `ValueError` at startup if the env var is not set. But this would break Dev (which doesn't need S3 creds).
- **Analysis** (2026-02-27): Reviewed how existing Production-required settings are handled. `DATABASE_URL` uses `values.DatabaseURLValue("sqlite:///db.sqlite3")` — a safe default that works in Dev and fails at first query in Production if misconfigured. `SECRET_KEY` uses `values.SecretValue()` — fails at startup if missing, but this is acceptable because it's always required. S3 settings are Production-only, so `SecretValue()` (Option C) would break Dev. Option B is robust but adds ~15 lines of code to `common/checks.py` and a registration in `common/apps.py` — scope creep for a medium-risk PEP. Option A is consistent with the `DATABASE_URL` precedent and keeps the PEP simple. The boto3 error on first upload (`NoCredentialsError` or `BucketNotFoundError`) is clear enough for operators.
- **Recommendation**: **Option A** — Accept and document. Add a comment in `.env.example` noting which S3 vars are required for Production. This is consistent with existing patterns and avoids scope creep. A Django system check can be added in a future PEP if misconfiguration proves to be a frequent issue.
- **Status**: Awaiting input — confirm whether Option A (accept and document) is acceptable.
