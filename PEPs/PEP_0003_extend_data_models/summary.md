# PEP 0003: Extend Data Models

| Field | Value |
|-------|-------|
| **PEP** | 0003 |
| **Title** | Extend Data Models |
| **Author** | Doorito Team |
| **Status** | Implementing |
| **Risk** | Medium |
| **Created** | 2026-02-25 |
| **Updated** | 2026-02-25 |
| **Related PEPs** | PEP 0002 (Rename FileUpload to IngestFile — superseded by UploadFile rename in this PEP) |
| **Depends On** | PEP 0002 |

---

## Problem Statement

Doorito's data layer currently has only `User`, `FileUpload` (pending rename via PEP 0002), and the abstract `TimeStampedModel`. A richer set of foundational domain models is needed to move beyond the skeleton and support basic application functionality.

## Proposed Solution

This PEP introduces 3 new models and redesigns the existing file model (renamed from `IngestFile` to `UploadFile` — see discussions.md Q6) to support batched, chunked file uploads. All models use UUID v7 primary keys (via `uuid_utils` — see discussions.md Q10) and live in the `uploads` app. Core services and business logic are included alongside models to ensure each model ships with operational code.

### Overview of Changes to UploadFile (formerly IngestFile)

The current `IngestFile` (from PEP 0001/0002) is renamed to `UploadFile` for naming consistency with the `Upload*` prefix used by all models in the `uploads` app (see discussions.md Q6). This PEP redesigns the model:

| Aspect | Current (PEP 0002) | Proposed (PEP 0003) |
|--------|-------------------|---------------------|
| Model name | `IngestFile` | `UploadFile` |
| Primary key | Auto-increment integer | UUID v7 |
| Base class | `TimeStampedModel` | `TimeStampedModel` (consistent with project convention) |
| File storage | Django `FileField` | Django `FileField` (retained — see discussions.md Q5) |
| User FK | `CASCADE` | `SET_NULL` (nullable) |
| Status choices | pending/ready/consumed/failed | uploading/stored/processed/failed/deleted |
| Batch support | None | Optional FK to `UploadBatch` |
| Integrity | None | `sha256` hash |
| Metadata | None | `JSONField` for non-sensitive metadata |

### Model 1: UploadBatch

Groups multiple uploaded files into a single logical batch for UX progress tracking.

**Key fields:**
- `id` — UUID v7 primary key
- `created_by` — FK to User (nullable, `SET_NULL`)
- `status` — `init` → `in_progress` → `complete` / `partial` / `failed`
- `idempotency_key` — Prevents duplicate batch creation from clients

Note: Denormalized counters were considered but rejected (see discussions.md Q8). Use `batch.files.filter(status=...).count()` for aggregate queries.

**Associated services:**
- `create_batch(user, idempotency_key=None) → UploadBatch` — Creates a new batch
- `finalize_batch(batch) → UploadBatch` — Transitions batch to `complete`/`partial`/`failed` based on file statuses

### Model 2: UploadFile (redesigned, renamed from IngestFile)

Canonical file record. Source of truth once the file reaches `stored` status.

**Key fields:**
- `id` — UUID v7 primary key
- `batch` — Optional FK to `UploadBatch` (`SET_NULL`)
- `uploaded_by` — FK to User (nullable, `SET_NULL`)
- `file` — Django `FileField` (retained for `.url`, `.delete()`, `.open()`, admin widgets, django-storages compatibility)
- `original_filename`, `content_type`, `size_bytes` — File metadata
- `sha256` — Content hash for integrity verification (indexed)
- `metadata` — JSONField for flexible non-sensitive metadata (e.g., xml_root, sniffed_type)
- `status` — `uploading` → `stored` → `processed` / `deleted` or `uploading` → `failed`

**Associated services:**
- `create_upload_file(user, file, batch=None) → UploadFile` — Validates file, creates record with `FileField`, computes `sha256`, sets status to `stored`
- `mark_file_failed(upload_file, error) → UploadFile` — Transitions to `FAILED` status
- `mark_file_deleted(upload_file) → UploadFile` — Transitions to `DELETED` status, deletes physical file
- `mark_file_processed(upload_file) → UploadFile` — Transitions from `STORED` to `PROCESSED` status

### Model 3: UploadSession

One upload session per file. Holds the chunking contract and tracks upload progress.

**Key fields:**
- `id` — UUID v7 primary key
- `file` — OneToOne FK to `UploadFile` (`CASCADE`)
- `status` — `init` → `in_progress` → `complete` / `failed` / `aborted`
- `chunk_size_bytes` — Target chunk size (default 5 MB)
- `total_size_bytes`, `total_parts` — Contract for the upload
- `bytes_received`, `completed_parts` — Progress counters
- `idempotency_key`, `upload_token` — Client-side deduplication and lightweight auth

**Associated services:**
- `create_upload_session(upload_file, total_size_bytes, chunk_size_bytes=None) → UploadSession` — Creates session linked to file
- `complete_upload_session(session) → UploadSession` — Validates all parts received, transitions to `COMPLETE`

### Model 4: UploadPart

Tracks individual chunks within an upload session. Unique per `(session, part_number)`.

**Key fields:**
- `id` — UUID v7 primary key
- `session` — FK to `UploadSession` (`CASCADE`)
- `part_number` — 1-indexed chunk ordinal
- `offset_bytes`, `size_bytes` — Byte range of this part
- `sha256` — Optional chunk-level integrity hash
- `status` — `pending` → `received` / `failed`
- `temp_storage_key` — Temporary storage location for the chunk before assembly

**Constraints:** `UniqueConstraint(fields=["session", "part_number"])`

**Associated services:**
- `record_upload_part(session, part_number, offset_bytes, size_bytes, sha256=None) → UploadPart` — Records a received chunk

### Event Outbox (Deferred)

The transactional event outbox (`PortalEventOutbox`) has been deferred to a dedicated event infrastructure PEP (see discussions.md Q9). That PEP will design the outbox as a generic `OutboxEvent` model in `common/` using the aggregate/payload pattern, with a delivery worker included.

### Entity Relationship Summary

```
User
  ├── UploadBatch (via created_by FK, SET_NULL)
  │     └── UploadFile (via batch FK, SET_NULL)
  │           └── UploadSession (1:1, CASCADE)
  │                 └── UploadPart (via session FK, CASCADE)
  └── UploadFile (via uploaded_by FK, SET_NULL)
```

### Reference Implementation

The full model code for all 4 models is provided in the plan as the implementation specification. Key design decisions:
- **UUID v7 PKs everywhere** — Time-ordered, better B-tree performance than UUID v4, safe for external exposure. Uses `uuid_utils` package (Python 3.12 lacks native `uuid7()`).
- **`SET_NULL` for user FKs** — Files survive user deletion.
- **Django `FileField` retained** — Preserves `.url`, `.delete()`, `.open()`, admin widgets, and django-storages compatibility. New fields (`sha256`, `metadata`) added alongside it.
- **No denormalized counters** — Use `COUNT()` queries at service layer; counters can be added later if needed (see discussions.md Q8).
- **Services alongside models** — Core business logic (upload creation, status transitions, batch management, session lifecycle) included to ensure operational code for every model.

## Out of Scope

- **API endpoints** — REST/GraphQL endpoints for upload flows will be a separate PEP. This PEP delivers models and internal services, not HTTP-facing APIs.
- **Event outbox** — The transactional event outbox (`OutboxEvent`) is deferred to a dedicated event infrastructure PEP. That PEP will design it as a generic model in `common/` with a delivery worker (see discussions.md Q9).
- **Chunk assembly logic** — Services that assemble `UploadPart` records into the final file are not part of this PEP. Part tracking and session management services are in scope; physical chunk concatenation is deferred.
- **Renaming the `uploads/` app directory** — Deferred per PEP 0002 decision.
- **Migration of existing data** — There is no production data. The existing table will be dropped and recreated.

## Status History

| Date | From | To | Notes |
|------|------|----|-------|
| 2026-02-25 | — | Proposed | Initial creation |
