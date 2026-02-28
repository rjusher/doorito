# PEP 0008: Canonical Domain Model for OSS Ingest Portal

| Field | Value |
|-------|-------|
| **PEP** | 0008 |
| **Title** | Canonical Domain Model for OSS Ingest Portal |
| **Author** | Doorito Team |
| **Status** | Implementing |
| **Risk** | High |
| **Created** | 2026-02-27 |
| **Updated** | 2026-02-27 |
| **Enables** | PEP 0009, PEP 0010, PEP 0011, PEP 0014, PEP 0015, PEP 0016, PEP 0017 |

---

## Problem Statement

A stable domain model is required before implementing chunking, batching, and reliable integration with the AI runner. Without a well-defined canonical model, upload lifecycle management, resumable chunked uploads, batch grouping, and durable event emission cannot be built on a solid foundation.

The existing upload models (UploadBatch, UploadFile, UploadSession, UploadPart) provide a starting point, but the OSS ingest portal requires a purpose-built model with strict invariants around file status transitions, deduplication, and outbox event creation.

## Proposed Solution

Implement the following Django models forming the canonical domain for the OSS ingest portal:

- **UploadFile** — Canonical file identity with simplified status lifecycle (UPLOADING, STORED, FAILED)
- **UploadSession** — Tracks a single chunked upload attempt (1:1 with UploadFile)
- **UploadPart** — Individual chunk within an upload session (1:N under UploadSession)
- **UploadBatch** — Optional grouping of multiple files for batch operations
- **PortalEventOutbox** — Durable event queue for reliable downstream integration (generic aggregate pattern, not FK-bound)

### Model Relationships

```
UploadBatch
└── UploadFile
    ├── UploadSession (1:1)
    │   └── UploadPart (1:N)

PortalEventOutbox (references any aggregate via aggregate_type/aggregate_id)
```

### Model Invariants

<!-- Amendment 2026-02-27: Clarified "storage pointer" — remains FileField until PEP 0009 per discussions.md -->
- `UploadFile.status = STORED` implies: `sha256` is populated, `size_bytes` is populated, file is stored (FileField non-blank; explicit storage fields deferred to PEP 0009)
- `UploadPart` must be unique per `(session, part_number)`
- `PortalEventOutbox` entries for file aggregates must only be created after the file is `STORED` (enforced in service layer)
- `PortalEventOutbox` uses `aggregate_type`/`aggregate_id` (not FK) to reference portal entities

## Rationale

Separating upload lifecycle (`UploadSession`) from file identity (`UploadFile`) ensures resumable uploads without corrupting the canonical file record. The session captures the transient state of a chunked upload, while the file record represents the permanent, verified artifact.

The `PortalEventOutbox` is kept as a separate model (rather than reusing `common.OutboxEvent`) to maintain domain isolation and allow portal-specific event schemas and delivery policies.

## Alternatives Considered

### Alternative 1: Reuse existing upload models directly

- **Description**: Use the existing `UploadBatch`, `UploadFile`, `UploadSession`, `UploadPart` models from the `uploads` app without modification.
- **Pros**: No new models, no migrations.
- **Cons**: Existing models may not enforce the strict invariants needed for the ingest portal. Missing portal-specific outbox integration.
- **Why rejected**: The ingest portal requires stricter status-transition invariants and a dedicated outbox model tied to file lifecycle events.

### Alternative 2: Single unified model

- **Description**: Combine file identity and upload lifecycle into a single model.
- **Pros**: Simpler schema, fewer joins.
- **Cons**: Mixes transient upload state with permanent file metadata. Makes resumable uploads harder to implement cleanly.
- **Why rejected**: Separation of concerns is critical for reliable chunked uploads.

## Impact Assessment

### Affected Components

- **Models**: Existing models evolved in portal app — UploadFile (status simplified), UploadSession, UploadPart, UploadBatch; new PortalEventOutbox model
- **Services**: New service layer for model operations (to be defined in subsequent PEPs)
- **Admin**: New admin registrations for all portal models
- **Tasks**: None initially (defined in subsequent PEPs)

### Migration Impact

- **Database migrations required?** Yes — new tables for all five models
- **Data migration needed?** No
- **Backward compatibility**: Non-breaking (additive)

### Performance Impact

- Unique constraint on `(session, part_number)` ensures efficient part lookups
- Indexes on status fields for query performance

## Out of Scope

- Upload endpoint implementation (PEP 0011, PEP 0012)
- Storage backend abstraction (PEP 0009)
- Event schema definition (PEP 0016)
- Outbox dispatcher logic (PEP 0017)
- New service layer features (chunked upload orchestration, storage abstraction)

<!-- Amendment 2026-02-28: Clarified per discussions.md — maintaining existing service functions and basic model-lifecycle validations ARE in scope; only new service features are out of scope -->

## Acceptance Criteria

- [ ] Unique constraint on `(session, part_number)` is enforced at the database level
<!-- Amendment 2026-02-27: Clarified storage pointer — remains FileField until PEP 0009 -->
- [ ] File cannot be marked `STORED` without required metadata (sha256, size_bytes, file stored) — enforced in service layer
- [ ] `PortalEventOutbox` entries for file aggregates cannot be created unless the referenced file is `STORED` (enforced in service layer)
- [ ] All models inherit from `TimeStampedModel` and use `uuid7` primary keys
- [ ] Database migrations are generated and apply cleanly
- [ ] `python manage.py check` passes

## Security Considerations

- No secrets stored in JSON fields
- Storage pointers must not expose filesystem paths directly

## Status History

| Date | From | To | Notes |
|------|------|----|-------|
| 2026-02-27 | — | Proposed | Initial creation |
| 2026-02-28 | — | — | Discussions pass: resolved migration handling, test updates, index naming, stale aggregate_type Q |
| 2026-02-28 | — | — | Review pass: resolved db_table naming — rename existing tables to portal_upload_* prefix |
