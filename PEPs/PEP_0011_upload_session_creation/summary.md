# PEP 0011: Upload Session Creation

| Field | Value |
|-------|-------|
| **PEP** | 0011 |
| **Title** | Upload Session Creation |
| **Author** | Doorito Team |
| **Status** | Proposed |
| **Risk** | Medium |
| **Created** | 2026-02-27 |
| **Updated** | 2026-02-27 |
| **Depends On** | PEP 0008, PEP 0009, PEP 0010 |
| **Enables** | PEP 0012, PEP 0013, PEP 0014 |

---

## Problem Statement

Chunked file uploads require a predefined contract for chunk size and part count before any data is transferred. Clients need an endpoint to initiate an upload session that calculates the chunking parameters and creates the necessary database records.

## Proposed Solution

Implement a session creation endpoint that establishes the chunk contract and creates the initial database records.

### Endpoint

`POST /uploads/sessions`

### Input

- `original_filename` — Name of the file being uploaded
- `content_type` — MIME type of the file
- `total_size_bytes` — Total file size in bytes
- `batch_id` (optional) — Associate with an existing batch
- `idempotency_key` (optional) — Client-provided key for safe retries

### Output

- `session_id` — UUID of the created session
- `chunk_size_bytes` — Size of each chunk (server-determined)
- `total_parts` — Number of parts to upload

### Behavior

1. Validate input (file size limits, content type allowlist if configured)
2. Create `IngestFile(status=UPLOADING)`
3. Create `UploadSession(status=INIT)`
4. Compute `total_parts = ceil(total_size_bytes / chunk_size)`
5. If `idempotency_key` matches an existing session, return the existing session
6. Return session details to client

## Rationale

Separating session creation from chunk upload allows the server to control chunking parameters (chunk size, total parts) based on file size and server configuration. This ensures consistent behavior across different clients and prevents oversized or undersized chunks.

The idempotency key enables safe retries — if a client's network drops after the server creates the session but before the response arrives, the client can retry with the same key and receive the original session.

## Alternatives Considered

### Alternative 1: Client-determined chunk size

- **Description**: Let the client decide chunk size and part count.
- **Pros**: More flexible for clients with specific requirements.
- **Cons**: Server cannot enforce chunk size limits. Inconsistent behavior. Server-side assembly becomes harder without known chunk size.
- **Why rejected**: Server-controlled chunking provides consistency and simplifies the assembly step.

## Impact Assessment

### Affected Components

- **Views/Endpoints**: New `POST /uploads/sessions` endpoint
- **Services**: New session creation service
- **Models**: Uses IngestFile, UploadSession from PEP 0008

### Migration Impact

- **Database migrations required?** No (models from PEP 0008)
- **Data migration needed?** No
- **Backward compatibility**: Non-breaking (new endpoint)

### Performance Impact

- Single transaction creating two rows — negligible

## Out of Scope

- Chunk upload logic (PEP 0012)
- Session status/resume endpoint (PEP 0013)
- Finalization logic (PEP 0014)
- Batch creation (PEP 0015)

## Acceptance Criteria

- [ ] `total_parts` is correctly computed as `ceil(total_size_bytes / chunk_size)`
- [ ] Oversized file (exceeding configured max) is rejected with 413
- [ ] Duplicate `idempotency_key` returns the same session (200, not 201)
- [ ] Response includes `session_id`, `chunk_size_bytes`, and `total_parts`
- [ ] `IngestFile` is created with status `UPLOADING`
- [ ] `UploadSession` is created with status `INIT`
- [ ] Authentication is required (401 for unauthenticated requests)

## Status History

| Date | From | To | Notes |
|------|------|----|-------|
| 2026-02-27 | — | Proposed | Initial creation |
