# PEP 0012: Chunk Upload Endpoint

| Field | Value |
|-------|-------|
| **PEP** | 0012 |
| **Title** | Chunk Upload Endpoint |
| **Author** | Doorito Team |
| **Status** | Proposed |
| **Risk** | High |
| **Created** | 2026-02-27 |
| **Updated** | 2026-02-27 |
| **Depends On** | PEP 0008, PEP 0009, PEP 0010, PEP 0011 |
| **Enables** | PEP 0014 |

---

## Problem Statement

Network instability requires safe retry behavior for file chunk uploads. Clients must be able to upload individual chunks idempotently, with the server correctly handling duplicate uploads, out-of-order parts, and size validation.

## Proposed Solution

Implement a chunk upload endpoint that accepts individual file parts and stores them safely in temporary storage.

### Endpoint

`PUT /uploads/sessions/{session_id}/parts/{part_number}`

### Behavior

1. Validate session status (must be INIT or IN_PROGRESS)
2. Validate `part_number` is within range `[1, total_parts]`
3. Validate chunk size (within expected bounds)
4. Store chunk in temp storage via storage adapter (PEP 0009)
5. Upsert `UploadPart` record:
   - If same part uploaded twice with same content → success (idempotent)
   - If same part uploaded with different content → 409 Conflict
6. Update session counters safely (atomic F() updates)
7. Set session status to `IN_PROGRESS` (if currently `INIT`)

### Idempotency

Re-uploading the same part with identical content is a no-op success. This allows clients to safely retry after network failures without risk of data corruption or double-counting.

## Rationale

PUT is the correct HTTP method for idempotent chunk uploads — uploading the same part twice produces the same result. The part number in the URL path makes each chunk addressable. Storing parts in temp storage (rather than directly assembling) enables out-of-order uploads and safe retry behavior.

## Alternatives Considered

### Alternative 1: POST with multipart form data

- **Description**: Use POST with standard multipart form encoding for chunk uploads.
- **Pros**: Works with standard HTML forms.
- **Cons**: POST is not idempotent by convention. Multipart encoding adds overhead for binary data.
- **Why rejected**: PUT semantics better match idempotent chunk uploads. Binary body is more efficient.

### Alternative 2: Assemble on-the-fly (no temp storage)

- **Description**: Append each chunk directly to the final file as it arrives.
- **Pros**: No temp storage needed.
- **Cons**: Out-of-order uploads impossible. Retry of a middle chunk corrupts the file. No way to verify completeness before finalizing.
- **Why rejected**: Temporary storage is essential for reliable out-of-order chunk uploads.

## Impact Assessment

### Affected Components

- **Views/Endpoints**: New `PUT /uploads/sessions/{id}/parts/{n}` endpoint
- **Services**: New chunk upload service
- **Models**: Uses UploadSession, UploadPart from PEP 0008
- **Storage**: Uses temp part operations from PEP 0009

### Migration Impact

- **Database migrations required?** No
- **Data migration needed?** No
- **Backward compatibility**: Non-breaking (new endpoint)

### Performance Impact

- Each chunk upload is a single DB upsert + storage write
- Atomic counter updates prevent race conditions under concurrent uploads

## Out of Scope

- Session finalization (PEP 0014)
- Content-based deduplication across files
- Client-side chunking library

## Acceptance Criteria

- [ ] Duplicate upload of same part with same content does not double-count received parts
- [ ] Wrong-size chunk (too large or too small, except last part) is rejected with 400
- [ ] Out-of-order parts are accepted (e.g., part 5 before part 3)
- [ ] Re-upload of same part with different content returns 409 Conflict
- [ ] Session status transitions from INIT to IN_PROGRESS on first part upload
- [ ] Part number outside valid range `[1, total_parts]` is rejected with 400
- [ ] Upload to a non-INIT/IN_PROGRESS session is rejected
- [ ] Authentication is required (401 for unauthenticated requests)

## Status History

| Date | From | To | Notes |
|------|------|----|-------|
| 2026-02-27 | — | Proposed | Initial creation |
