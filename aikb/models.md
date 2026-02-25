# Data Models Reference

Complete reference of all Django models in Doorito.

## Abstract Base Models (common)

### TimeStampedModel
Abstract model inherited by most models in the project. Defined in `common/models.py`.
- `created_at` -- DateTimeField (auto_now_add)
- `updated_at` -- DateTimeField (auto_now)

### MoneyField
Custom DecimalField (max_digits=12, decimal_places=2, default=0.00) for monetary amounts. Defined in `common/fields.py`. Includes a `MinValueValidator(0.00)` by default. Reports itself as a plain `DecimalField` in `deconstruct()` to avoid migration churn.

---

## Accounts App

### User (AbstractUser)
Custom user model extending Django's AbstractUser. No additional fields beyond what AbstractUser provides. `db_table = "user"`. Returns `email or username` from `__str__()`.

---

## Uploads App

### IngestFile (TimeStampedModel)
Temporary ingest file with lifecycle tracking. Files are validated on upload, stored locally under `media/uploads/%Y/%m/`, and cleaned up after a configurable TTL. Defined in `uploads/models.py`. `db_table = "ingest_file"`.

**Fields:**
- `user` -- ForeignKey to `settings.AUTH_USER_MODEL` (CASCADE, `related_name="ingest_files"`)
- `file` -- FileField (`upload_to="uploads/%Y/%m/"`)
- `original_filename` -- CharField (max_length=255). Stored separately because Django may rename files on collision.
- `file_size` -- PositiveBigIntegerField (file size in bytes)
- `mime_type` -- CharField (max_length=100). Detected via `mimetypes.guess_type()`, falls back to `application/octet-stream`.
- `status` -- CharField (max_length=20, choices=Status.choices, default=PENDING)
- `error_message` -- TextField (blank=True). Populated on validation failure.
- `created_at` -- DateTimeField (auto_now_add, inherited from TimeStampedModel)
- `updated_at` -- DateTimeField (auto_now, inherited from TimeStampedModel)

**Status Choices (IngestFile.Status):**
- `PENDING` ("pending") -- Reserved for future async validation (e.g., virus scanning). Currently, `create_ingest_file` transitions directly to READY or FAILED.
- `READY` ("ready") -- Validated and available for consumption.
- `CONSUMED` ("consumed") -- A downstream process has retrieved and used the file.
- `FAILED` ("failed") -- Upload validation failed.

**Status lifecycle:** `pending → ready → consumed` or `pending → failed`

**Indexes:**
- Composite: `["user", "-created_at"]` (user's upload list)
- Single: `["status"]` (cleanup queries)

**Ordering:** `["-created_at"]`

**`__str__`:** `f"{self.original_filename} ({self.get_status_display()})"`

---

## Entity Relationship Summary

```
User (accounts.User, extends AbstractUser)
  ├── standard Django auth fields (username, email, password, etc.)
  └── IngestFile (uploads.IngestFile, via user FK, CASCADE)
        └── file, original_filename, file_size, mime_type, status, error_message
```

All future models should inherit from `TimeStampedModel` and use `MoneyField` for monetary amounts.
