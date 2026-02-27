# PEP 0015: Batch Upload Support

| Field | Value |
|-------|-------|
| **PEP** | 0015 |
| **Title** | Batch Upload Support |
| **Author** | Doorito Team |
| **Status** | Proposed |
| **Risk** | Medium |
| **Created** | 2026-02-27 |
| **Updated** | 2026-02-27 |
| **Depends On** | PEP 0008, PEP 0010 |

---

## Problem Statement

Users uploading many files need a way to group them and track progress collectively. Without batch support, clients must track individual upload sessions independently, making it difficult to determine overall completion status for a multi-file upload operation.

## Proposed Solution

Provide grouping of multiple files under a batch with automatic counter tracking.

### Endpoints

- `POST /batches` — Create a new batch
- `GET /batches/{id}` — Get batch details and progress
- `GET /batches/{id}/files` — List files in the batch

### Behavior

- `IngestFile` may optionally reference a batch (nullable FK)
- Batch counters (`total_files`, `stored_count`, `failed_count`) are updated atomically when a file transitions to STORED or FAILED
- Counter updates use atomic `F()` expressions to avoid race conditions under concurrent uploads
- Batch status derived from counters (e.g., all files stored = batch complete)

## Rationale

Batch grouping is a natural user expectation when uploading multiple files. Atomic counter updates ensure accuracy even when multiple files in the same batch finalize concurrently. Keeping batch logic separate from the core upload flow (sessions, chunks, finalize) maintains clean separation of concerns.

## Alternatives Considered

### Alternative 1: Client-side batch tracking

- **Description**: Let clients track batch membership and progress themselves.
- **Pros**: No server-side batch logic needed.
- **Cons**: Duplicates logic across clients. No server-side visibility into batch progress. No admin UI for batch status.
- **Why rejected**: Server-side batching provides a single source of truth and enables admin visibility.

### Alternative 2: Batch as a required concept

- **Description**: Every upload must belong to a batch (even single files).
- **Pros**: Uniform model.
- **Cons**: Adds unnecessary overhead for single-file uploads.
- **Why rejected**: Batches should be optional to keep single-file uploads simple.

## Impact Assessment

### Affected Components

- **Views/Endpoints**: New batch creation, detail, and file listing endpoints
- **Services**: New batch service, integration with finalization service for counter updates
- **Models**: Uses UploadBatch, IngestFile from PEP 0008

### Migration Impact

- **Database migrations required?** No (models from PEP 0008)
- **Data migration needed?** No
- **Backward compatibility**: Non-breaking (new endpoints)

### Performance Impact

- Atomic F() counter updates add minimal overhead to finalization
- Batch listing queries are indexed on batch FK

## Out of Scope

- Batch-level operations (cancel all, retry all)
- Batch completion webhooks (events are per-file via PEP 0016/0017)
- Nested batches

## Acceptance Criteria

- [ ] Batch counters are accurate under concurrent file finalizations
- [ ] Batch listing returns correct files with their statuses
- [ ] Batch detail shows total_files, stored_count, failed_count
- [ ] Single-file uploads work without a batch (batch_id is optional)
- [ ] Authentication is required for all batch endpoints

## Status History

| Date | From | To | Notes |
|------|------|----|-------|
| 2026-02-27 | — | Proposed | Initial creation |
