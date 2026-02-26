# Data Models Reference

Complete reference of all Django models in Doorito.

## Abstract Base Models (common)

### TimeStampedModel
Abstract model inherited by most models in the project. Defined in `common/models.py`.
- `created_at` -- DateTimeField (auto_now_add)
- `updated_at` -- DateTimeField (auto_now)

### MoneyField
Custom DecimalField (max_digits=12, decimal_places=2, default=0.00) for monetary amounts. Defined in `common/fields.py`. Includes a `MinValueValidator(0.00)` by default. Reports itself as a plain `DecimalField` in `deconstruct()` to avoid migration churn.

## Utility Functions (common)

### uuid7()
Generates a UUID v7 (time-ordered, RFC 9562) as a stdlib `uuid.UUID`. Defined in `common/utils.py`. Wraps `uuid_utils.uuid7()` and converts to `uuid.UUID` via `uuid.UUID(bytes=_uuid_utils.uuid7().bytes)` for compatibility with Django's `UUIDField`. All models with UUID PKs use `default=uuid7`.

---

## Accounts App

### User (AbstractUser)
Custom user model extending Django's AbstractUser. No additional fields beyond what AbstractUser provides. `db_table = "user"`. Returns `email or username` from `__str__()`.

---

## Uploads App

All upload models use UUID v7 primary keys (via `common.utils.uuid7`), inherit from `TimeStampedModel`, and live in `uploads/models.py`.

### UploadBatch (TimeStampedModel)
Groups multiple uploaded files into a single logical batch for UX progress tracking. `db_table = "upload_batch"`.

**Fields:**
- `id` -- UUIDField (primary_key, default=uuid7)
- `created_by` -- ForeignKey to `settings.AUTH_USER_MODEL` (SET_NULL, nullable, `related_name="upload_batches"`)
- `status` -- CharField (max_length=20, choices=Status.choices, default=INIT)
- `idempotency_key` -- CharField (max_length=255, blank, db_index). Client-provided key to prevent duplicate batch creation.
- `created_at`, `updated_at` -- inherited from TimeStampedModel

**Status Choices (UploadBatch.Status):**
- `INIT` ("init") -- Batch created, no files added yet.
- `IN_PROGRESS` ("in_progress") -- Files are being uploaded.
- `COMPLETE` ("complete") -- All files stored/processed successfully.
- `PARTIAL` ("partial") -- Some files succeeded, some failed.
- `FAILED` ("failed") -- All files failed (or no files).

**Status lifecycle:** `init → in_progress → complete / partial / failed`

**Ordering:** `["-created_at"]`

**`__str__`:** `f"Batch {self.pk} ({self.get_status_display()})"`

---

### UploadFile (TimeStampedModel)
Canonical file record. Source of truth once the file reaches `stored` status. Redesigned from the original `IngestFile` model (PEP 0003). `db_table = "upload_file"`.

**Fields:**
- `id` -- UUIDField (primary_key, default=uuid7)
- `batch` -- ForeignKey to `UploadBatch` (SET_NULL, nullable, `related_name="files"`)
- `uploaded_by` -- ForeignKey to `settings.AUTH_USER_MODEL` (SET_NULL, nullable, `related_name="upload_files"`)
- `file` -- FileField (`upload_to="uploads/%Y/%m/"`)
- `original_filename` -- CharField (max_length=255). Stored separately because Django may rename files on collision.
- `content_type` -- CharField (max_length=100). Detected via `mimetypes.guess_type()`, falls back to `application/octet-stream`.
- `size_bytes` -- PositiveBigIntegerField (file size in bytes)
- `sha256` -- CharField (max_length=64, blank, db_index). Content hash for integrity verification.
- `metadata` -- JSONField (default=dict, blank). Flexible non-sensitive metadata (e.g., xml_root, sniffed_type).
- `status` -- CharField (max_length=20, choices=Status.choices, default=UPLOADING)
- `error_message` -- TextField (blank). Populated on validation failure.
- `created_at`, `updated_at` -- inherited from TimeStampedModel

**Status Choices (UploadFile.Status):**
- `UPLOADING` ("uploading") -- File upload in progress (chunked) or about to be stored.
- `STORED` ("stored") -- File validated, hashed, and stored. Available for downstream processing.
- `PROCESSED` ("processed") -- A downstream process has consumed the file.
- `FAILED` ("failed") -- Upload validation or processing failed.
- `DELETED` ("deleted") -- Physical file removed, record retained for audit.

**Status lifecycle:** `uploading → stored → processed / deleted` or `uploading → failed`

**Indexes:**
- Composite: `["uploaded_by", "-created_at"]` (user's upload list)
- Single: `["status"]` (cleanup and status queries)
- Single: `sha256` (db_index on field, for dedup lookups)

**Ordering:** `["-created_at"]`

**`__str__`:** `f"{self.original_filename} ({self.get_status_display()})"`

---

### UploadSession (TimeStampedModel)
One upload session per file. Holds the chunking contract and tracks upload progress. OneToOne relationship with `UploadFile`. `db_table = "upload_session"`.

**Fields:**
- `id` -- UUIDField (primary_key, default=uuid7)
- `file` -- OneToOneField to `UploadFile` (CASCADE, `related_name="session"`)
- `status` -- CharField (max_length=20, choices=Status.choices, default=INIT)
- `chunk_size_bytes` -- PositiveIntegerField (default=5,242,880 = 5 MB). Target chunk size.
- `total_size_bytes` -- PositiveBigIntegerField. Total expected file size.
- `total_parts` -- PositiveIntegerField. Total expected number of parts.
- `bytes_received` -- PositiveBigIntegerField (default=0). Progress counter.
- `completed_parts` -- PositiveIntegerField (default=0). Progress counter.
- `idempotency_key` -- CharField (max_length=255, blank, db_index). Client-side deduplication.
- `upload_token` -- CharField (max_length=255, blank, db_index). Lightweight auth token.
- `created_at`, `updated_at` -- inherited from TimeStampedModel

**Status Choices (UploadSession.Status):**
- `INIT` ("init") -- Session created, no parts received yet.
- `IN_PROGRESS` ("in_progress") -- Parts are being received.
- `COMPLETE` ("complete") -- All parts received successfully.
- `FAILED` ("failed") -- Session failed.
- `ABORTED` ("aborted") -- Session aborted by client.

**Status lifecycle:** `init → in_progress → complete / failed / aborted`

**Ordering:** `["-created_at"]`

**`__str__`:** `f"Session {self.pk} ({self.get_status_display()})"`

---

### UploadPart (TimeStampedModel)
Tracks individual chunks within an upload session. Unique per `(session, part_number)`. `db_table = "upload_part"`.

**Fields:**
- `id` -- UUIDField (primary_key, default=uuid7)
- `session` -- ForeignKey to `UploadSession` (CASCADE, `related_name="parts"`)
- `part_number` -- PositiveIntegerField. 1-indexed chunk ordinal.
- `offset_bytes` -- PositiveBigIntegerField. Byte offset of this part in the file.
- `size_bytes` -- PositiveBigIntegerField. Size of this part in bytes.
- `sha256` -- CharField (max_length=64, blank). Optional chunk-level integrity hash.
- `status` -- CharField (max_length=20, choices=Status.choices, default=PENDING)
- `temp_storage_key` -- CharField (max_length=500, blank). Temporary storage location for chunk before assembly.
- `created_at`, `updated_at` -- inherited from TimeStampedModel

**Status Choices (UploadPart.Status):**
- `PENDING` ("pending") -- Part expected but not yet received.
- `RECEIVED` ("received") -- Part received and stored.
- `FAILED` ("failed") -- Part upload failed.

**Status lifecycle:** `pending → received / failed`

**Constraints:**
- `UniqueConstraint(fields=["session", "part_number"], name="unique_session_part_number")`

**Ordering:** `["part_number"]`

**`__str__`:** `f"Part {self.part_number} of session {self.session_id}"`

---

## FK Cascade Rules

| FK | On Delete | Rationale |
|----|-----------|-----------|
| `UploadBatch.created_by` → User | SET_NULL | Batches survive user deletion |
| `UploadFile.batch` → UploadBatch | SET_NULL | Files survive batch deletion |
| `UploadFile.uploaded_by` → User | SET_NULL | Files survive user deletion |
| `UploadSession.file` → UploadFile | CASCADE | Session meaningless without file |
| `UploadPart.session` → UploadSession | CASCADE | Parts meaningless without session |

---

## Entity Relationship Summary

```
User (accounts.User, extends AbstractUser)
  ├── UploadBatch (via created_by FK, SET_NULL)
  │     └── UploadFile (via batch FK, SET_NULL)
  │           └── UploadSession (1:1, CASCADE)
  │                 └── UploadPart (via session FK, CASCADE)
  └── UploadFile (via uploaded_by FK, SET_NULL)
```

All models inherit from `TimeStampedModel`. All upload models use UUID v7 primary keys via `common.utils.uuid7`. Use `MoneyField` for monetary amounts.
