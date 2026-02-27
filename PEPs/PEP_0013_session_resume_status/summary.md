# PEP 0013: Session Resume and Status Endpoint

| Field | Value |
|-------|-------|
| **PEP** | 0013 |
| **Title** | Session Resume and Status Endpoint |
| **Author** | Doorito Team |
| **Status** | Proposed |
| **Risk** | Low |
| **Created** | 2026-02-27 |
| **Updated** | 2026-02-27 |
| **Depends On** | PEP 0008, PEP 0010, PEP 0011 |

---

## Problem Statement

Clients must be able to resume uploads after interruption. Without a status endpoint, a client that loses connectivity has no way to determine which chunks have been received and which still need to be uploaded, forcing a full re-upload.

## Proposed Solution

Expose an endpoint that returns the current upload session status and which chunks have been received.

### Endpoint

`GET /uploads/sessions/{session_id}`

### Response

- `session_id` — Session identifier
- `status` — Current session status (INIT, IN_PROGRESS, COMPLETE, FAILED, ABORTED)
- `total_parts` — Total number of expected parts
- `completed_parts` — Number of parts received
- `received_parts` — List or compact range representation of received part numbers

### Compact Range Representation

For large sessions with many parts, received parts are returned as ranges for efficiency:
- Example: `[1-50, 52, 55-100]` instead of listing all 96 individual part numbers

## Rationale

A status endpoint is essential for resumable uploads. Clients can query the session state, determine which parts are missing, and upload only those parts. The compact range representation keeps response sizes manageable even for sessions with thousands of parts.

## Alternatives Considered

### Alternative 1: Include status in chunk upload response

- **Description**: Return session progress in each chunk upload response.
- **Pros**: No separate endpoint needed.
- **Cons**: Doesn't help after a full disconnect — client needs to query without uploading.
- **Why rejected**: A dedicated status endpoint is needed for the resume use case.

## Impact Assessment

### Affected Components

- **Views/Endpoints**: New `GET /uploads/sessions/{id}` endpoint
- **Services**: New session status service
- **Models**: Reads UploadSession, UploadPart from PEP 0008

### Migration Impact

- **Database migrations required?** No
- **Data migration needed?** No
- **Backward compatibility**: Non-breaking (new endpoint)

### Performance Impact

- Single session query + part list query — lightweight

## Out of Scope

- Session modification or cancellation via this endpoint
- Webhook notifications for session progress
- Batch-level status (covered in PEP 0015)

## Acceptance Criteria

- [ ] Received parts accurately reflect the database state
- [ ] Large sessions (1000+ parts) return compact range representation
- [ ] Response includes session status, total_parts, and completed_parts
- [ ] Non-existent session returns 404
- [ ] Authentication is required (401 for unauthenticated requests)

## Status History

| Date | From | To | Notes |
|------|------|----|-------|
| 2026-02-27 | — | Proposed | Initial creation |
