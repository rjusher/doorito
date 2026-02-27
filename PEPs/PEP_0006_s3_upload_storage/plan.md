# PEP 0006: S3 Upload Storage — Implementation Plan

| Field | Value |
|-------|-------|
| **PEP** | 0006 |
| **Summary** | [summary.md](summary.md) |
| **Estimated Effort** | S |

---

## Context Files

Read these files before implementation to understand existing patterns and the code being extended:

- `aikb/dependencies.md` — Current dependency management workflow (`.in` → `.txt` compile pattern with `uv`)
- `aikb/services.md` §Uploads App — `create_upload_file` function signature and behavior (this is the function being modified)
- `aikb/models.md` §OutboxEvent — Outbox event model fields, especially `aggregate_type`, `aggregate_id`, `event_type`, `payload`, `idempotency_key`
- `aikb/tasks.md` §Task Conventions — Task patterns, queue routing, celery-beat schedule format
- `aikb/deployment.md` — Docker Compose services, environment variables, `.env.example` structure
- `aikb/architecture.md` §Storage — Current storage configuration (local filesystem for media, WhiteNoise for static)
- `boot/settings.py` — Settings classes; lines 206–213 (`Dev.STORAGES`) and 236–243 (`Production.STORAGES`) are the exact locations being modified; lines 110–112 for `MEDIA_URL`/`MEDIA_ROOT`; lines 120–136 for Celery pattern using `values.*` wrappers
- `uploads/services/uploads.py` — `create_upload_file()` function (lines 76–129) — this is where the `emit_event` call will be added
- `uploads/models.py` — `UploadFile` model (lines 48–102) — `file` FileField at line 78, status choices at lines 56–61
- `common/services/outbox.py` — `emit_event()` signature and transactional usage pattern (lines 18–74)
- `common/utils.py` — `safe_dispatch()` context manager (lines 52–72, used by `emit_event`)
- `requirements.in` — Current production dependencies (will add `django-storages[s3]`)
- `.env.example` — Current environment variable template (will add S3 variables)
- `docker-compose.yml` — Production Docker services (will add S3 env vars to web, celery-worker, celery-beat)
- `docker-compose.dev.yml` — Dev Docker override (no changes needed — Dev keeps FileSystemStorage)
- `uploads/tests/test_services.py` — Existing test patterns for upload services (fixtures, `SimpleUploadedFile`, `tmp_path`, `settings` override)
- `common/tests/test_services.py` — Existing test patterns for `emit_event` (assertion style, fixture usage)
- `conftest.py` — Root `user` fixture (lines 6–15)
- `common/tests/conftest.py` — `make_outbox_event` factory fixture

## Prerequisites

- [x] PostgreSQL database is running (required for tests): `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check --database default`
- [x] Current tests pass: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest --tb=short -q`
- [x] PEP 0004 (Event Outbox Infrastructure) is implemented — required for `emit_event` service: `grep -q "emit_event" common/services/outbox.py && echo "OK"`

## Implementation Steps

### Step 1: Add `django-storages[s3]` dependency

- [x] **Step 1a**: Add `django-storages[s3]` to `requirements.in`
  - Files: `requirements.in` — add new line after the `django-htmx` entry (line 32)
  - Details: Add `django-storages[s3]>=1.14` as a new section. The `[s3]` extra pulls in `boto3` automatically. No need to list `boto3` separately.
  - Content to add:
    ```
    # Cloud storage (S3-compatible backends)
    django-storages[s3]>=1.14
    ```
  - Verify: `grep 'django-storages\[s3\]' requirements.in`

- [x] **Step 1b**: Compile lockfiles and install
  - Files: `requirements.txt` (generated), `requirements-dev.txt` (generated)
  - Details: Run the standard `uv pip compile` workflow with `--generate-hashes`:
    ```bash
    source ~/.virtualenvs/inventlily-d22a143/bin/activate
    uv pip compile --generate-hashes requirements.in -o requirements.txt
    uv pip compile --generate-hashes requirements-dev.in -o requirements-dev.txt
    uv pip install -r requirements-dev.txt
    ```
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && python -c "import storages; print(storages.__version__)"` and `source ~/.virtualenvs/inventlily-d22a143/bin/activate && python -c "import boto3; print(boto3.__version__)"`

### Step 2: Configure S3 storage backend in settings

- [x] **Step 2a**: Add S3 settings to `Base` class
  - Files: `boot/settings.py` — add new settings block in `Base` class after `FILE_UPLOAD_ALLOWED_TYPES` (after line 178)
  - Details: Add S3 configuration values using `values.*` wrappers consistent with existing patterns (see `CELERY_BROKER_URL` at line 121 for the `values.Value(..., environ_name=...)` pattern). All settings should have safe defaults (empty strings) so that `Dev` configuration works without S3 env vars.
  - Settings to add:
    ```python
    # S3 storage settings (used by Production for media file storage)
    AWS_STORAGE_BUCKET_NAME = values.Value(
        "", environ_name="AWS_STORAGE_BUCKET_NAME"
    )
    AWS_S3_ENDPOINT_URL = values.Value(
        "", environ_name="AWS_S3_ENDPOINT_URL"
    )
    AWS_S3_REGION_NAME = values.Value(
        "", environ_name="AWS_S3_REGION_NAME"
    )
    AWS_ACCESS_KEY_ID = values.Value(
        "", environ_name="AWS_ACCESS_KEY_ID"
    )
    AWS_SECRET_ACCESS_KEY = values.Value(
        "", environ_name="AWS_SECRET_ACCESS_KEY"
    )
    AWS_QUERYSTRING_AUTH = values.BooleanValue(
        True, environ_name="AWS_QUERYSTRING_AUTH"
    )
    AWS_QUERYSTRING_EXPIRE = values.IntegerValue(
        3600, environ_name="AWS_QUERYSTRING_EXPIRE"
    )
    AWS_S3_FILE_OVERWRITE = values.BooleanValue(
        False, environ_name="AWS_S3_FILE_OVERWRITE"
    )
    ```
  <!-- Amendment 2026-02-27: Added AWS_S3_FILE_OVERWRITE=False per discussions.md Q1 resolution. Without this, files with the same name in the same month silently overwrite each other on S3. -->
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from django.conf import settings; print(settings.AWS_STORAGE_BUCKET_NAME)"`

- [x] **Step 2b**: Update `Production.STORAGES` to use `S3Boto3Storage`
  - Files: `boot/settings.py` — modify `Production.STORAGES` (lines 236–243)
  - Details: Replace `FileSystemStorage` with `storages.backends.s3boto3.S3Boto3Storage` for the `"default"` backend. Keep `staticfiles` backend unchanged (WhiteNoise).
  - Before:
    ```python
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }
    ```
  - After:
    ```python
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }
    ```
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from django.conf import settings; print(settings.STORAGES['default']['BACKEND'])"` should print `django.core.files.storage.FileSystemStorage` (Dev unchanged)

- [x] **Step 2c**: Verify Dev settings remain unchanged
  - Files: `boot/settings.py` — `Dev.STORAGES` (lines 206–213) must NOT be modified
  - Details: `Dev` class retains `FileSystemStorage` as the default backend. No changes to `Dev` class.
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from django.conf import settings; assert settings.STORAGES['default']['BACKEND'] == 'django.core.files.storage.FileSystemStorage', 'Dev should use FileSystemStorage'; print('OK: Dev uses FileSystemStorage')"` and `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check`

### Step 3: Emit outbox event on file stored

- [x] **Step 3a**: Add `emit_event` call to `create_upload_file`
  - Files: `uploads/services/uploads.py` — modify `create_upload_file()` function (lines 76–129)
  - Details: After the successful `UploadFile.objects.create(...)` call (line 111) that creates a file with `status=STORED`, wrap the creation and event emission in `transaction.atomic()` and call `emit_event()` following the pattern documented in `common/services/outbox.py` lines 28–32. The event should only be emitted for successful uploads (status=STORED), not failed ones.
  - Add import at top of file (after line 10, `from django.db import transaction`):
    ```python
    from common.services.outbox import emit_event
    ```
    Note: `transaction` is already imported at line 10.
  - Modify the success path (lines 111–128) to:
    ```python
    with transaction.atomic():
        upload = UploadFile.objects.create(
            uploaded_by=user,
            file=file,
            original_filename=file.name,
            content_type=content_type,
            size_bytes=size_bytes,
            sha256=sha256,
            batch=batch,
            status=UploadFile.Status.STORED,
        )
        emit_event(
            aggregate_type="UploadFile",
            aggregate_id=str(upload.pk),
            event_type="file.stored",
            payload={
                "file_id": str(upload.pk),
                "original_filename": upload.original_filename,
                "content_type": upload.content_type,
                "size_bytes": upload.size_bytes,
                "sha256": upload.sha256,
                "url": upload.file.url,
            },
        )
    ```
  - The `idempotency_key` defaults to `"UploadFile:{pk}"` via `emit_event`'s auto-generation (see `common/services/outbox.py` line 47).
  - The `upload.file.url` call delegates to the configured storage backend: `FileSystemStorage` returns a local path in Dev; `S3Boto3Storage` returns a pre-signed or direct URL in Production (controlled by `AWS_QUERYSTRING_AUTH`).
  - Verify: `grep -A 20 "def create_upload_file" uploads/services/uploads.py | grep "emit_event"` and `grep "from common.services.outbox import emit_event" uploads/services/uploads.py`

### Step 4: Update environment configuration files

- [x] **Step 4a**: Update `.env.example` with S3 variables
  - Files: `.env.example` — add S3 section at the end (after the Celery section, line 52)
  - Details: Add commented-out S3 environment variables with descriptions, following the existing format pattern.
  - Content to add:
    ```
    # S3 Storage (Production only — Dev uses local filesystem)
    # Required when DJANGO_CONFIGURATION=Production
    # AWS_STORAGE_BUCKET_NAME=my-bucket-name
    # AWS_S3_ENDPOINT_URL=https://s3.amazonaws.com
    # AWS_S3_REGION_NAME=us-east-1
    # AWS_ACCESS_KEY_ID=your-access-key
    # AWS_SECRET_ACCESS_KEY=your-secret-key
    # AWS_QUERYSTRING_AUTH=True
    # AWS_QUERYSTRING_EXPIRE=3600
    # AWS_S3_FILE_OVERWRITE=False
    ```
  - Verify: `grep "AWS_STORAGE_BUCKET_NAME" .env.example`

- [x] **Step 4b**: Document S3 env vars in `docker-compose.yml`
  - Files: `docker-compose.yml` — add S3 env vars to `web`, `celery-worker`, and `celery-beat` services
  - Details: Add S3 environment variables (with empty defaults so the compose file works without them for Dev). These are passed through from the host's `.env` or environment. Use the `${VAR:-}` syntax for optional variables (empty string default).
  - Add to `web.environment` (after `WEB_PORT` line):
    ```yaml
    - AWS_STORAGE_BUCKET_NAME=${AWS_STORAGE_BUCKET_NAME:-}
    - AWS_S3_ENDPOINT_URL=${AWS_S3_ENDPOINT_URL:-}
    - AWS_S3_REGION_NAME=${AWS_S3_REGION_NAME:-}
    - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID:-}
    - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY:-}
    - AWS_QUERYSTRING_AUTH=${AWS_QUERYSTRING_AUTH:-True}
    - AWS_QUERYSTRING_EXPIRE=${AWS_QUERYSTRING_EXPIRE:-3600}
    - AWS_S3_FILE_OVERWRITE=${AWS_S3_FILE_OVERWRITE:-False}
    ```
  - Add the same block to `celery-worker.environment` and `celery-beat.environment` (they need access to S3 for the cleanup task which calls `file.delete()`).
  - Verify: `grep -c "AWS_STORAGE_BUCKET_NAME" docker-compose.yml` should return `3` (one per service)

### Step 5: Write tests for the outbox event emission

- [x] **Step 5a**: Add tests for `file.stored` outbox event in `create_upload_file`
  - Files: `uploads/tests/test_services.py` — add new test class `TestCreateUploadFileOutboxEvent` after `TestCreateUploadFile` (after line 123)
  - Details: Test that successful uploads emit an outbox event, and failed uploads do not. Follow existing test patterns in `uploads/tests/test_services.py` (use `user` fixture from root `conftest.py`, `SimpleUploadedFile`, `tmp_path`, `settings`). Import `OutboxEvent` from `common.models`.
  - New test class:
    ```python
    @pytest.mark.django_db
    class TestCreateUploadFileOutboxEvent:
        """Tests for outbox event emission in create_upload_file."""

        def test_stored_file_emits_outbox_event(self, user, tmp_path, settings):
            """Successful upload emits file.stored outbox event."""
            settings.MEDIA_ROOT = tmp_path
            content = b"pdf content"
            file = SimpleUploadedFile("document.pdf", content)
            upload = create_upload_file(user, file)

            assert upload.status == UploadFile.Status.STORED
            event = OutboxEvent.objects.get(event_type="file.stored")
            assert event.aggregate_type == "UploadFile"
            assert event.aggregate_id == str(upload.pk)
            assert event.status == OutboxEvent.Status.PENDING
            assert event.payload["file_id"] == str(upload.pk)
            assert event.payload["original_filename"] == "document.pdf"
            assert event.payload["content_type"] == "application/pdf"
            assert event.payload["size_bytes"] == len(content)
            assert event.payload["sha256"] == upload.sha256
            assert "url" in event.payload

        def test_stored_file_event_payload_url(self, user, tmp_path, settings):
            """Outbox event URL matches the file's storage URL."""
            settings.MEDIA_ROOT = tmp_path
            file = SimpleUploadedFile("report.pdf", b"content")
            upload = create_upload_file(user, file)

            event = OutboxEvent.objects.get(event_type="file.stored")
            assert event.payload["url"] == upload.file.url

        def test_failed_file_does_not_emit_outbox_event(self, user, tmp_path, settings):
            """Failed upload does not emit any outbox event."""
            settings.MEDIA_ROOT = tmp_path
            settings.FILE_UPLOAD_MAX_SIZE = 1
            file = SimpleUploadedFile("big.pdf", b"too large content")
            upload = create_upload_file(user, file)

            assert upload.status == UploadFile.Status.FAILED
            assert not OutboxEvent.objects.filter(event_type="file.stored").exists()

        def test_outbox_event_idempotency_key(self, user, tmp_path, settings):
            """Outbox event uses default idempotency key format."""
            settings.MEDIA_ROOT = tmp_path
            file = SimpleUploadedFile("doc.pdf", b"content")
            upload = create_upload_file(user, file)

            event = OutboxEvent.objects.get(event_type="file.stored")
            assert event.idempotency_key == f"UploadFile:{upload.pk}"
    ```
  - Add import at top of test file: `from common.models import OutboxEvent`
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest uploads/tests/test_services.py::TestCreateUploadFileOutboxEvent -v`

### Step 6: Run full test suite

- [x] **Step 6**: Verify all tests pass
  - Details: Run the complete test suite to catch any regressions.
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest --tb=short -q`

## Testing

- [ ] Unit tests for outbox event emission — Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest uploads/tests/test_services.py::TestCreateUploadFileOutboxEvent -v`
- [ ] Existing upload service tests still pass — Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest uploads/tests/test_services.py -v`
- [ ] Existing outbox tests still pass — Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest common/tests/test_services.py -v`
- [ ] Full test suite passes — Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest --tb=short -q`
- [ ] Django system check passes (Dev) — Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check`
- [ ] Linting passes — Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && ruff check .`

## Rollback Plan

This PEP is fully rollback-safe:

1. **No database migrations**: No model changes. No migration files are created or applied.
2. **Settings revert**: Change `Production.STORAGES["default"]["BACKEND"]` back to `django.core.files.storage.FileSystemStorage` and remove the S3 settings from `Base`.
3. **Service revert**: Remove the `transaction.atomic()` block and `emit_event()` call from `create_upload_file()` in `uploads/services/uploads.py`, restoring the original direct `UploadFile.objects.create()` call.
4. **Dependencies revert**: Remove `django-storages[s3]>=1.14` from `requirements.in` and recompile lockfiles.
5. **Environment revert**: Remove S3 env vars from `.env.example` and `docker-compose.yml`.
6. **Existing outbox events**: Any `file.stored` events already emitted will be processed and cleaned up by the existing outbox delivery/cleanup tasks (no manual cleanup needed).

## aikb Impact Map

- [ ] `aikb/models.md` — N/A (no model changes)
- [ ] `aikb/services.md` — Update `create_upload_file` description in §uploads/services/uploads.py to document that it now emits a `file.stored` outbox event (with payload fields: `file_id`, `original_filename`, `content_type`, `size_bytes`, `sha256`, `url`) when a file is successfully stored. Add note about `transaction.atomic()` wrapping.
- [ ] `aikb/tasks.md` — N/A (no task changes)
- [ ] `aikb/signals.md` — N/A (no signal changes)
- [ ] `aikb/admin.md` — N/A (no admin changes)
- [ ] `aikb/cli.md` — N/A (no CLI changes)
- [ ] `aikb/architecture.md` — Update §Storage section (lines 122–132) to document the dual storage configuration: Dev uses local `FileSystemStorage`, Production uses `S3Boto3Storage` via `django-storages[s3]`. List the S3 settings available. Update the duplicate §Storage section (lines 127–132) to merge into one consistent section.
- [ ] `aikb/conventions.md` — N/A (no new conventions introduced)
- [ ] `aikb/dependencies.md` — Add `django-storages[s3]` and `boto3` (transitive) to the Production Dependencies table under a new "Cloud Storage" section. Version: `>=1.14`. Purpose: S3-compatible media file storage backend.
- [ ] `aikb/deployment.md` — Add S3 environment variables to the §Environment Variables table: `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_ENDPOINT_URL`, `AWS_S3_REGION_NAME`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_QUERYSTRING_AUTH`, `AWS_QUERYSTRING_EXPIRE`. Add note that S3 is only used in Production configuration.
- [ ] `aikb/specs-roadmap.md` — Move "S3 / cloud storage for media files" from "What's Not Built Yet" to "What's Ready" (as "S3 media storage (Production)").
- [ ] `CLAUDE.md` — Update §Storage Configuration section to document the dual-backend setup. Add S3 env vars to the §Environment Variables implicit list. Update §File Upload Settings to mention that `UploadFile.file` URL generation depends on the storage backend.

## Final Verification

### Acceptance Criteria

- [ ] **`django-storages[s3]` and `boto3` are listed in `requirements.in` and compiled into `requirements.txt`**
  - Verify: `grep 'django-storages\[s3\]' requirements.in && grep 'django-storages' requirements.txt && grep 'boto3' requirements.txt`

- [ ] **`Production` settings class configures `S3Boto3Storage` as the `"default"` storage backend**
  - Verify: `grep 'S3Boto3Storage' boot/settings.py`

- [ ] **All S3 settings are configurable via environment variables using `values.*` wrappers**
  - Verify: `grep -c "values\.\(Value\|BooleanValue\|IntegerValue\).*AWS" boot/settings.py` should return `8`

- [ ] **`Dev` settings class retains `FileSystemStorage` as the default backend**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "from django.conf import settings; assert settings.STORAGES['default']['BACKEND'] == 'django.core.files.storage.FileSystemStorage'; print('OK')"`

- [ ] **`python manage.py check` passes with Dev configuration**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check`

- [ ] **Existing upload services work without code changes**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest uploads/tests/test_services.py::TestMarkFileProcessed uploads/tests/test_services.py::TestMarkFileDeleted uploads/tests/test_services.py::TestMarkFileFailed -v`

- [ ] **Existing cleanup task works without code changes**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest uploads/tests/test_tasks.py -v`

- [ ] **S3 URL generation settings are configurable via environment variables**
  - Verify: `grep "AWS_QUERYSTRING_AUTH" boot/settings.py && grep "AWS_QUERYSTRING_EXPIRE" boot/settings.py`

- [ ] **`create_upload_file` emits an OutboxEvent with event type `file.stored`**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest uploads/tests/test_services.py::TestCreateUploadFileOutboxEvent::test_stored_file_emits_outbox_event -v`

- [ ] **The `file.stored` outbox event payload includes all required fields**
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest uploads/tests/test_services.py::TestCreateUploadFileOutboxEvent::test_stored_file_emits_outbox_event uploads/tests/test_services.py::TestCreateUploadFileOutboxEvent::test_stored_file_event_payload_url -v`

- [ ] **`.env.example` is updated with S3 environment variables**
  - Verify: `grep "AWS_STORAGE_BUCKET_NAME" .env.example && grep "AWS_S3_ENDPOINT_URL" .env.example && grep "AWS_QUERYSTRING_AUTH" .env.example`

- [ ] **`aikb/` documentation is updated to reflect the new storage configuration**
  - Verify: `grep -l "S3\|s3\|django-storages" aikb/*.md | wc -l` should return at least 4 files

- [ ] **Docker environment supports the new S3 env vars**
  - Verify: `grep -c "AWS_STORAGE_BUCKET_NAME" docker-compose.yml` should return `3`

### Integration Checks

- [ ] **Full upload → outbox event workflow (Dev with FileSystemStorage)**
  - Steps:
    1. Run `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "
    import django; django.setup()
    from django.core.files.uploadedfile import SimpleUploadedFile
    from uploads.services.uploads import create_upload_file
    from common.models import OutboxEvent
    from accounts.models import User
    import tempfile, os
    os.environ.setdefault('MEDIA_ROOT', tempfile.mkdtemp())
    user = User.objects.create_user('integ_test', 'integ@test.com', 'pass')
    f = SimpleUploadedFile('test.pdf', b'integration test content')
    upload = create_upload_file(user, f)
    assert upload.status == 'stored'
    event = OutboxEvent.objects.get(event_type='file.stored')
    assert event.payload['file_id'] == str(upload.pk)
    assert event.payload['url'] == upload.file.url
    print('Integration test passed: upload + outbox event workflow OK')
    User.objects.filter(username='integ_test').delete()
    "`
  - Expected: Prints "Integration test passed" with no errors

- [ ] **Failed upload does not emit event**
  - Steps: Run the `test_failed_file_does_not_emit_outbox_event` test
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest uploads/tests/test_services.py::TestCreateUploadFileOutboxEvent::test_failed_file_does_not_emit_outbox_event -v`

### Regression Checks

- [ ] `python manage.py check` passes
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check`
- [ ] `ruff check .` passes
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && ruff check .`
- [ ] Full test suite passes
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest --tb=short -q`
- [ ] Existing upload service tests unaffected
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest uploads/tests/ -v`
- [ ] Existing outbox tests unaffected
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -m pytest common/tests/ -v`

## Completion

- [ ] **Update `PEPs/IMPLEMENTED/LATEST.md`** — Add entry with PEP number, title, commit hash(es), and summary
- [ ] **Update `PEPs/INDEX.md`** — Remove the PEP row
- [ ] **Remove PEP directory** — Delete `PEPs/PEP_0006_s3_upload_storage/`
