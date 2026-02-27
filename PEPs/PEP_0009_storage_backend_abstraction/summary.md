# PEP 0009: Storage Backend Abstraction

| Field | Value |
|-------|-------|
| **PEP** | 0009 |
| **Title** | Storage Backend Abstraction |
| **Author** | Doorito Team |
| **Status** | Proposed |
| **Risk** | Medium |
| **Created** | 2026-02-27 |
| **Updated** | 2026-02-27 |
| **Depends On** | PEP 0008 |
| **Enables** | PEP 0012, PEP 0014 |

---

## Problem Statement

OSS users may run the ingest portal locally or in S3/MinIO environments. The portal needs a storage layer that supports streaming reads and writes for both temporary chunk parts and finalized files, without coupling portal logic to a specific storage infrastructure.

Currently, there is no abstraction for temp part storage (used during chunked uploads) or final object storage that works consistently across local filesystem and S3-compatible backends.

## Proposed Solution

Create a pluggable storage adapter interface with streaming support, covering both temporary part operations and final object operations.

### Temp Part Operations

- `put_temp_part(session_id, part_number, stream) -> temp_key`
- `get_temp_part_stream(temp_key) -> stream`
- `delete_temp_part(temp_key)`

### Final Object Operations

- `put_final(file_id, stream) -> (bucket, key)`
- `get_final_stream(bucket, key) -> stream`
- `delete_final(bucket, key)`

### Requirements

- No full-file memory loads — all operations must be streaming-safe
- Temp and final storage prefixes are isolated
- Clear error propagation with well-defined exceptions

### Implementations

- **LocalStorageAdapter** — Uses local filesystem (development default)
- **S3StorageAdapter** — Uses boto3 with S3-compatible APIs (production)

## Rationale

Storage abstraction prevents tight coupling between portal logic and infrastructure. By defining a clear interface, the upload session creation, chunk upload, and finalize endpoints can operate identically regardless of whether files are stored locally or in S3. This also enables testing with the local adapter while deploying with S3.

## Alternatives Considered

### Alternative 1: Use Django's built-in storage API directly

- **Description**: Use `default_storage` from Django for all operations.
- **Pros**: No custom abstraction needed.
- **Cons**: Django's storage API doesn't natively handle temp-part namespacing or streaming assembly of chunked uploads. Would require workarounds.
- **Why rejected**: The temp part lifecycle (write, read-back for assembly, delete) doesn't map cleanly to Django's FileField-oriented storage API.

### Alternative 2: Always use local temp storage, S3 only for final

- **Description**: Store temp parts on local disk even in S3 deployments; only push final assembled file to S3.
- **Pros**: Simpler temp storage logic.
- **Cons**: Requires local disk on every worker node. Doesn't scale in serverless/container environments. Part data lost if container restarts mid-upload.
- **Why rejected**: Inconsistent storage strategy creates operational complexity and fragility.

## Impact Assessment

### Affected Components

- **Services**: New storage adapter module in portal app
- **Settings**: Storage backend configuration (adapter selection, S3 credentials)
- **Dependencies**: `boto3` for S3 adapter (may already be present from PEP 0006)

### Migration Impact

- **Database migrations required?** No
- **Data migration needed?** No
- **Backward compatibility**: Non-breaking (additive)

### Performance Impact

- Streaming operations ensure memory usage stays constant regardless of file size
- S3 multipart upload API used for large final objects

## Out of Scope

- CDN or pre-signed URL generation
- Object lifecycle policies
- Cross-region replication
- Encryption at rest configuration (handled by S3 bucket settings)

## Acceptance Criteria

- [ ] Large file upload does not exceed memory limits (streaming verified)
- [ ] Temp parts can be written, read back, and deleted via the adapter interface
- [ ] Final object can be streamed, stored, and hashed without full-file memory load
- [ ] Local adapter works without any external dependencies
- [ ] S3 adapter works with MinIO or S3-compatible endpoint
- [ ] Adapter selection is configurable via settings

## Status History

| Date | From | To | Notes |
|------|------|----|-------|
| 2026-02-27 | — | Proposed | Initial creation |
