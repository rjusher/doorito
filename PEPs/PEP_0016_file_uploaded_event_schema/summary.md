# PEP 0016: Canonical file.uploaded Event Schema

| Field | Value |
|-------|-------|
| **PEP** | 0016 |
| **Title** | Canonical file.uploaded Event Schema |
| **Author** | Doorito Team |
| **Status** | Proposed |
| **Risk** | Medium |
| **Created** | 2026-02-27 |
| **Updated** | 2026-02-27 |
| **Depends On** | PEP 0008, PEP 0014 |
| **Enables** | PEP 0017 |

---

## Problem Statement

The AI runner depends on a stable integration contract for file upload events. Without a well-defined event schema, the runner cannot reliably parse events, and schema changes risk breaking the integration. A canonical schema ensures both the portal and runner agree on the event structure.

## Proposed Solution

Define a stable event payload schema for the `file.uploaded` event emitted to the AI runner when a file reaches STORED status.

### Event Payload

```json
{
  "event_type": "file.uploaded",
  "event_id": "<uuid7>",
  "occurred_at": "<ISO 8601 timestamp>",
  "file": {
    "id": "<uuid7>",
    "filename": "<original filename>",
    "content_type": "<MIME type>",
    "size_bytes": <integer>,
    "sha256": "<hex digest>",
    "storage": {
      "backend": "<storage backend identifier>",
      "bucket": "<bucket name>",
      "key": "<object key>"
    }
  },
  "actor": {
    "user_id": "<uuid7 or null>",
    "username": "<string or null>"
  }
}
```

### Schema Rules

- **Additive-only changes**: New fields may be added but existing fields must not be removed or renamed
- **No secrets**: No API keys, tokens, or credentials in the payload
- **Runner deduplication**: Runner can deduplicate by `event_id`
- **Null-safe actor**: `actor` fields are null when the upload was performed without authentication context (e.g., system-initiated)

## Rationale

A canonical event schema serves as the integration contract between the ingest portal and the AI runner. By defining the schema explicitly and committing to additive-only evolution, both sides can evolve independently without breaking changes. Including the full storage pointer (backend/bucket/key) allows the runner to access the file directly from storage without going through the portal.

## Alternatives Considered

### Alternative 1: Include file content in the event

- **Description**: Embed the file data (base64) directly in the event payload.
- **Pros**: Runner doesn't need storage access.
- **Cons**: Massive payloads. Defeats the purpose of chunked uploads. Queue/outbox size explosion.
- **Why rejected**: Events should be lightweight pointers, not data carriers.

### Alternative 2: Use a generic event envelope without schema

- **Description**: Emit events with unstructured JSON payloads.
- **Pros**: Maximum flexibility.
- **Cons**: No contract. Runner parsing is fragile. Schema drift is invisible.
- **Why rejected**: A defined schema is essential for reliable integration.

## Impact Assessment

### Affected Components

- **Services**: Finalization service (PEP 0014) produces the event payload
- **Models**: PortalEventOutbox stores the payload as JSON
- **Documentation**: Schema documented for runner integration

### Migration Impact

- **Database migrations required?** No
- **Data migration needed?** No
- **Backward compatibility**: Non-breaking (defines new schema)

### Performance Impact

- None — schema definition, not runtime change

## Out of Scope

- Event versioning strategy (v1/v2 envelopes)
- Runner-side event parsing implementation
- Non-file event types (batch.completed, etc.)

## Acceptance Criteria

- [ ] Event payload validates against a defined JSON schema
- [ ] Runner can deduplicate events by `event_id`
- [ ] No secrets present in the payload
- [ ] Storage pointer includes backend, bucket, and key
- [ ] Actor is populated when available, null-safe when not
- [ ] Schema is documented in the codebase

## Status History

| Date | From | To | Notes |
|------|------|----|-------|
| 2026-02-27 | — | Proposed | Initial creation |
