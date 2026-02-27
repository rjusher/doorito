# PEP 0014: Finalize Upload

| Field | Value |
|-------|-------|
| **PEP** | 0014 |
| **Title** | Finalize Upload |
| **Author** | Doorito Team |
| **Status** | Proposed |
| **Risk** | High |
| **Created** | 2026-02-27 |
| **Updated** | 2026-02-27 |
| **Depends On** | PEP 0008, PEP 0009, PEP 0010, PEP 0011, PEP 0012 |
| **Enables** | PEP 0016, PEP 0017 |

---

## Problem Statement

After all chunks are uploaded, the file must be assembled, verified, and stored as a canonical file before the AI runner can process it. Without a finalization step, uploaded chunks remain as disconnected temporary parts with no verified final file.

## Proposed Solution

Implement a finalization endpoint that assembles chunks into the final file, computes a SHA256 hash, updates the file record, and emits a durable outbox event.

### Endpoint

`POST /uploads/sessions/{session_id}/finalize`

### Algorithm

1. **Lock session row** (SELECT FOR UPDATE) to prevent concurrent finalization
2. **Idempotency check**: If session is already COMPLETE and file is STORED → return success
3. **Verify all parts received** — all parts in RECEIVED status
4. **Stream-assemble parts** — read parts in order from temp storage, write to final storage
5. **Compute SHA256 streaming** — hash computed during assembly, not as a separate pass
6. **Update IngestFile**:
   - `status = STORED`
   - `sha256` = computed hash
   - `size_bytes` = total assembled size
   - `storage_backend`, `storage_bucket`, `storage_key` = final storage pointer
7. **Mark session COMPLETE**
8. **Create PortalEventOutbox** entry with `event_type = "file.uploaded"`
9. **Use `transaction.on_commit`** to enqueue the outbox dispatcher task

## Rationale

The finalization step is the critical transition point where temporary chunks become a verified canonical file. Locking prevents duplicate assembly. Streaming assembly with inline SHA256 computation avoids reading the file twice and keeps memory usage constant. The outbox pattern ensures the event is only created when the file is truly stored, and `transaction.on_commit` ensures the dispatcher is only triggered after the database transaction succeeds.

## Alternatives Considered

### Alternative 1: Auto-finalize when last chunk arrives

- **Description**: Automatically finalize when `received_parts_count == total_parts`.
- **Pros**: No explicit finalize call needed.
- **Cons**: Race condition if multiple chunks arrive simultaneously. Client loses control over when finalization happens. No explicit confirmation step.
- **Why rejected**: Explicit finalization gives clients control and avoids race conditions.

### Alternative 2: Separate hash verification step

- **Description**: Assemble first, then compute SHA256 in a separate read pass.
- **Pros**: Simpler implementation.
- **Cons**: Reads the entire file twice — doubles I/O and time for large files.
- **Why rejected**: Streaming hash computation during assembly is more efficient.

## Impact Assessment

### Affected Components

- **Views/Endpoints**: New `POST /uploads/sessions/{id}/finalize` endpoint
- **Services**: New finalization service (most complex service in the portal)
- **Models**: Updates IngestFile, UploadSession, creates PortalEventOutbox
- **Storage**: Uses both temp (read/delete) and final (write) storage operations
- **Tasks**: Enqueues outbox dispatcher via `transaction.on_commit`

### Migration Impact

- **Database migrations required?** No
- **Data migration needed?** No
- **Backward compatibility**: Non-breaking (new endpoint)

### Performance Impact

- Assembly streams through storage adapter — memory usage is constant regardless of file size
- SHA256 computed inline — single pass over data
- SELECT FOR UPDATE lock held only during assembly

## Out of Scope

- Outbox dispatcher implementation (PEP 0017)
- Event schema definition (PEP 0016)
- Automatic cleanup of temp parts after finalization (PEP 0019)
- Parallel assembly of parts

## Acceptance Criteria

- [ ] Missing part → finalize fails with 400 and descriptive error
- [ ] Duplicate finalize does not duplicate the outbox event (idempotent)
- [ ] SHA256 in the IngestFile record matches the assembled file content
- [ ] File status transitions to STORED only after successful assembly
- [ ] Session status transitions to COMPLETE only after file is STORED
- [ ] PortalEventOutbox entry created with `event_type = "file.uploaded"`
- [ ] Dispatcher enqueued via `transaction.on_commit` (not before commit)
- [ ] Authentication is required (401 for unauthenticated requests)

## Status History

| Date | From | To | Notes |
|------|------|----|-------|
| 2026-02-27 | — | Proposed | Initial creation |
