# Service Layer Reference

Doorito uses a service layer pattern to encapsulate business logic outside of models and views.

## Design Principles

1. **Models are data containers** -- they define fields, relationships, and simple computed properties.
2. **Services contain business logic** -- validation, multi-model coordination, side effects.
3. **Views/Admin call services** -- never perform complex logic directly.
4. **CLI commands delegate to services** -- all Click commands should call service functions.
5. **Tasks call services** -- Celery tasks should be thin wrappers around service calls.

## Convention

Services live in `{app}/services/` directories:

```
{app}/
└── services/
    ├── __init__.py
    └── {domain}.py    # One module per domain concern
```

Service functions are plain Python functions (not classes):

```python
# Example service function
def create_widget(store, name, price, created_by=None):
    """Create a new widget with validation."""
    # Business logic here
    return widget
```

## Current State

The `uploads` app has two service modules, separated by domain concern:
- `uploads/services/uploads.py` -- File validation, creation, and status transitions; batch management
- `uploads/services/sessions.py` -- Chunked upload session lifecycle management

When adding services to a new app, follow the same pattern:

1. Create `{app}/services/__init__.py`
2. Create `{app}/services/{domain}.py` with the service functions
3. Import and call from views, admin, CLI, and tasks

---

## Uploads App

### uploads/services/uploads.py

Upload handling services for file validation, creation, status transitions, and batch management. Contains 8 functions.

**`validate_file(file, max_size=None)`**
Validate an uploaded file's size and MIME type. Returns `(content_type, size_bytes)` tuple. Raises `ValidationError` with code `file_too_large` or `file_type_not_allowed`. Uses `mimetypes.guess_type()` for MIME detection (extension-based, falls back to `application/octet-stream`). Checks against `settings.FILE_UPLOAD_MAX_SIZE` (default 50 MB) and `settings.FILE_UPLOAD_ALLOWED_TYPES` (`None` = accept all).

**`compute_sha256(file)`**
Compute SHA-256 hash of a file. Reads in 64 KB chunks. Seeks to start before and after hashing so the file can be saved by Django's `FileField` afterward. Returns hex-encoded hash string (64 characters).

**`create_upload_file(user, file, batch=None)`**
Validate, hash, and store an upload file. Returns an `UploadFile` instance with `status=STORED` (success, with `sha256` computed) or `status=FAILED` (validation error with `error_message` populated). Optionally associates the file with an `UploadBatch`.

**`mark_file_processed(upload_file)`**
Transition an upload file from STORED to PROCESSED. Uses atomic `filter(pk=..., status=STORED).update(status=PROCESSED)` to prevent race conditions. Raises `ValueError` if the upload file is not in STORED status. Returns the refreshed `UploadFile` instance.

**`mark_file_failed(upload_file, error="")`**
Transition an upload file to FAILED status with an error message. Saves via `update_fields` for efficiency. Returns the updated `UploadFile` instance.

**`mark_file_deleted(upload_file)`**
Transition an upload file to DELETED status and remove the physical file via `file.delete(save=False)`. Handles `FileNotFoundError` gracefully. Returns the updated `UploadFile` instance.

**`create_batch(user, idempotency_key="")`**
Create a new upload batch with INIT status. Returns an `UploadBatch` instance.

**`finalize_batch(batch)`**
Finalize a batch based on its files' statuses. Uses `@transaction.atomic`. Transitions to: COMPLETE (all files STORED/PROCESSED), PARTIAL (some succeeded, some failed), or FAILED (all failed or no files). Returns the updated `UploadBatch` instance.

---

### uploads/services/sessions.py

Chunked upload session lifecycle management. Contains 3 functions.

**`create_upload_session(upload_file, total_size_bytes, chunk_size_bytes=None)`**
Create an upload session for chunked file upload. Calculates `total_parts` via `math.ceil(total_size_bytes / chunk_size_bytes)`. Default chunk size is 5 MB. Returns an `UploadSession` instance.

**`record_upload_part(session, part_number, offset_bytes, size_bytes, sha256="")`**
Record a received chunk within an upload session. Creates an `UploadPart` with RECEIVED status. Uses `F()` expressions for atomic counter updates on the session (`completed_parts`, `bytes_received`) and transitions session to IN_PROGRESS. Returns an `UploadPart` instance.

**`complete_upload_session(session)`**
Complete an upload session after all parts are received. Uses `@transaction.atomic`. Validates that received part count matches `total_parts`. Transitions session to COMPLETE and the associated `UploadFile` from UPLOADING to STORED. Raises `ValueError` if not all parts have been received. Returns the updated `UploadSession` instance.
