# PEP 0003: Extend Data Models

| Field | Value |
|-------|-------|
| **PEP** | 0003 |
| **Title** | Extend Data Models |
| **Author** | Doorito Team |
| **Status** | Proposed |
| **Risk** | Medium |
| **Created** | 2026-02-25 |
| **Updated** | 2026-02-25 |
| **Related PEPs** | PEP 0002 (Rename FileUpload to IngestFile) |
| **Depends On** | PEP 0002 |

---

## Problem Statement

Doorito's data layer currently has only `User`, `FileUpload` (pending rename to `IngestFile` via PEP 0002), and the abstract `TimeStampedModel`. A richer set of foundational domain models is needed to move beyond the skeleton and support basic application functionality.

## Proposed Solution

This PEP introduces 4 new models and redesigns the existing `IngestFile` model to support batched, chunked file uploads with an event outbox for downstream processing. All new models use UUID primary keys and live in the `uploads` app.

### Overview of Changes to IngestFile

The current `IngestFile` (from PEP 0001/0002) is a simple model backed by Django's `FileField`. This PEP replaces it with a storage-abstracted design:

| Aspect | Current (PEP 0002) | Proposed (PEP 0003) |
|--------|-------------------|---------------------|
| Primary key | Auto-increment integer | UUID |
| Base class | `TimeStampedModel` | `models.Model` (explicit timestamp fields) |
| File storage | Django `FileField` | Abstract pointers (`storage_backend`, `storage_bucket`, `storage_key`) |
| User FK | `CASCADE` | `SET_NULL` (nullable) |
| Status choices | pending/ready/consumed/failed | uploading/stored/failed/deleted |
| Batch support | None | Optional FK to `UploadBatch` |
| Integrity | None | `sha256` hash |
| Metadata | None | `JSONField` for non-sensitive metadata |

### Model 1: UploadBatch

Groups multiple uploaded files into a single logical batch for UX progress tracking.

**Key fields:**
- `id` — UUID primary key
- `created_by` — FK to User (nullable, `SET_NULL`)
- `status` — `init` → `in_progress` → `complete` / `partial` / `failed`
- `total_files`, `stored_files`, `failed_files` — Denormalized counters for quick UI rendering
- `idempotency_key` — Prevents duplicate batch creation from clients

### Model 2: IngestFile (redesigned)

Canonical file record. Source of truth once the file reaches `stored` status.

**Key fields:**
- `id` — UUID primary key
- `batch` — Optional FK to `UploadBatch` (`SET_NULL`)
- `uploaded_by` — FK to User (nullable, `SET_NULL`)
- `original_filename`, `content_type`, `size_bytes` — File metadata
- `sha256` — Content hash for integrity verification (indexed)
- `storage_backend` — `"local"` or `"s3"` (abstract storage pointer)
- `storage_bucket`, `storage_key` — Storage location coordinates
- `metadata` — JSONField for flexible non-sensitive metadata (e.g., xml_root, sniffed_type)
- `status` — `uploading` → `stored` / `failed` / `deleted`

### Model 3: UploadSession

One upload session per file. Holds the chunking contract and tracks upload progress.

**Key fields:**
- `id` — UUID primary key
- `file` — OneToOne FK to `IngestFile` (`CASCADE`)
- `status` — `init` → `in_progress` → `complete` / `failed` / `aborted`
- `chunk_size_bytes` — Target chunk size (default 5 MB)
- `total_size_bytes`, `total_parts` — Contract for the upload
- `bytes_received`, `completed_parts` — Progress counters
- `idempotency_key`, `upload_token` — Client-side deduplication and lightweight auth

### Model 4: UploadPart

Tracks individual chunks within an upload session. Unique per `(session, part_number)`.

**Key fields:**
- `id` — UUID primary key
- `session` — FK to `UploadSession` (`CASCADE`)
- `part_number` — 1-indexed chunk ordinal
- `offset_bytes`, `size_bytes` — Byte range of this part
- `sha256` — Optional chunk-level integrity hash
- `status` — `pending` → `received` / `failed`
- `temp_storage_key` — Temporary storage location for the chunk before assembly

**Constraints:** `UniqueConstraint(fields=["session", "part_number"])`

### Model 5: PortalEventOutbox

Durable outbox entry for delivering events (e.g., `file.uploaded`) to downstream consumers. Created only after a file reaches `stored` status. Implements the transactional outbox pattern.

**Key fields:**
- `id` — UUID primary key
- `event_type` — Event name (e.g., `"file.uploaded"`)
- `idempotency_key` — Deduplication key
- `file` — FK to `IngestFile` (`CASCADE`)
- `payload` — JSONField with event data
- `status` — `pending` → `sending` → `delivered` / `failed`
- `attempts`, `next_attempt_at` — Retry tracking
- `delivered_at` — Timestamp of successful delivery

**Constraints:** `UniqueConstraint(fields=["event_type", "idempotency_key"])`

### Entity Relationship Summary

```
User
  ├── UploadBatch (via created_by FK, SET_NULL)
  │     └── IngestFile (via batch FK, SET_NULL)
  │           ├── UploadSession (1:1, CASCADE)
  │           │     └── UploadPart (via session FK, CASCADE)
  │           └── PortalEventOutbox (via file FK, CASCADE)
  └── IngestFile (via uploaded_by FK, SET_NULL)
```

### Reference Implementation

The full model code for all 5 models is provided in the plan as the implementation specification. Key design decisions:
- **UUID PKs everywhere** — Avoids sequential ID enumeration; safe for external exposure.
- **`SET_NULL` for user FKs** — Files survive user deletion.
- **Abstract storage pointers** instead of Django `FileField` — Supports local FS and S3-like backends without coupling to Django's file handling.
- **Denormalized counters on UploadBatch** — Avoids `COUNT(*)` queries for UI rendering.
- **Transactional outbox** — Guarantees event delivery after file storage without distributed transactions.

## Out of Scope

- **API endpoints** — This PEP defines models only. REST/GraphQL endpoints for upload flows will be a separate PEP.
- **Storage backend implementation** — The `storage_backend`/`storage_bucket`/`storage_key` fields are pointers. Actual S3 integration is out of scope; only local storage is supported initially.
- **Chunk assembly logic** — Services that assemble `UploadPart` records into the final file are not part of this PEP.
- **Outbox delivery worker** — The `PortalEventOutbox` model defines the schema; the Celery task that polls and delivers events is a separate concern.
- **Renaming the `uploads/` app directory** — Deferred per PEP 0002 decision.
- **Migration of existing `IngestFile` data** — There is no production data. The existing table will be dropped and recreated.

## Status History

| Date | From | To | Notes |
|------|------|----|-------|
| 2026-02-25 | — | Proposed | Initial creation |
