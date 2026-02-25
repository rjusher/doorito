# Service Layer Reference

Doorito uses a service layer pattern to encapsulate business logic outside of models and views. **No services have been implemented yet** -- this file documents the conventions for when they are added.

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
# Example future service function
def create_widget(store, name, price, created_by=None):
    """Create a new widget with validation."""
    # Business logic here
    return widget
```

## Current State

The first service module exists in the `uploads` app. When adding services to a new app, follow the same pattern:

1. Create `{app}/services/__init__.py`
2. Create `{app}/services/{domain}.py` with the service functions
3. Import and call from views, admin, CLI, and tasks

---

## Uploads App

### uploads/services/uploads.py

Upload handling services for file validation, creation, and consumption.

**`validate_file(file, max_size=None)`**
Validate an uploaded file's size and MIME type. Returns `(mime_type, file_size)` tuple. Raises `ValidationError` with code `file_too_large` or `file_type_not_allowed`. Uses `mimetypes.guess_type()` for MIME detection (extension-based, falls back to `application/octet-stream`). Checks against `settings.FILE_UPLOAD_MAX_SIZE` (default 50 MB) and `settings.FILE_UPLOAD_ALLOWED_TYPES` (`None` = accept all).

**`create_upload(user, file)`**
Validate and store a file upload. Returns a `FileUpload` instance with `status=READY` (success) or `status=FAILED` (validation error with `error_message` populated). Transitions directly — `PENDING` is reserved for future async validation.

**`consume_upload(file_upload)`**
Mark an upload as consumed by a downstream process. Uses atomic `filter(pk=..., status=READY).update(status=CONSUMED)` to prevent race conditions. Raises `ValueError` if the upload is not in READY status. Returns the refreshed `FileUpload` instance.
