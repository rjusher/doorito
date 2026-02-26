# PEP 0003: Extend Data Models — Discussions

| Field | Value |
|-------|-------|
| **PEP** | 0003 |
| **Summary** | [summary.md](summary.md) |
| **Research** | [research.md](research.md) |

---

## Design Review (2026-02-25)

This section is a comprehensive review of the 5 proposed models. It covers architectural concerns, model-by-model suggestions, alternative approaches, and cross-cutting design questions. The goal is to ensure the implementation is the best possible before committing to code.

### Architectural Concern: Scope and Phasing

The PEP proposes 5 models at once: `UploadBatch`, `IngestFile` (redesigned), `UploadSession`, `UploadPart`, and `PortalEventOutbox`. This is ambitious for a single PEP, especially since:

- **Services and business logic are now in scope** — this PEP will deliver both models and their core service layer, ensuring each model has operational code. *(Decision: see Q4 below.)*
- **Outbox delivery worker is deferred** — `PortalEventOutbox` defines a transactional outbox schema. The delivery worker (polling task) will be implemented in a follow-up PEP, but the outbox model and event-creation services are in scope for this PEP.
- **Tests will cover services** — with services included, tests can verify status transitions, counter updates, and business logic beyond CRUD. *(Decision: see Q4 below.)*

**Alternative: Phase the models across multiple PEPs.**

| Phase | Models | Rationale |
|-------|--------|-----------|
| PEP 0003 | `IngestFile` (redesigned) | Core entity. Everything depends on it. Can be shipped with basic services. |
| PEP 0004 | `UploadBatch` | Grouping layer. Only needed when multi-file upload UX is built. |
| PEP 0005 | `UploadSession` + `UploadPart` | Chunking infrastructure. Only needed when resumable uploads are required. |
| PEP 0006 | `PortalEventOutbox` (or equivalent) | Event infrastructure. Only needed when downstream consumers exist. |

**Trade-off**: Phasing means more migrations and more PEPs, but each PEP is smaller, testable end-to-end, and ships with services. Doing all 5 at once means a large schema with no operational code — essentially scaffolding.

**Decision**: All 5 models and their services will be delivered under this PEP. The PEP scope has been expanded to include the service layer alongside models, ensuring each model ships with operational code. The phased approach was considered but rejected — a single PEP avoids migration churn and keeps related models cohesive. *(See Q4 in Previously Resolved Questions.)*

---

### Model-by-Model Review

#### 1. IngestFile — Storage Abstraction: FileField vs Abstract Pointers

The most consequential design decision in this PEP is replacing Django's `FileField` with three `CharField` pointers (`storage_backend`, `storage_bucket`, `storage_key`).

**What you lose by dropping FileField:**
- `instance.file.url` — automatic URL generation (including S3 pre-signed URLs via django-storages)
- `instance.file.delete()` — automatic file deletion from any backend
- `instance.file.open()` — automatic streaming from any backend
- Django admin file upload/download widgets
- Zero-code backend switching (local → S3) via a settings change

**What you gain with abstract pointers:**
- Per-instance backend routing (e.g., `storage_backend="s3"` for one file, `"local"` for another)
- Queryable storage metadata (`filter(storage_backend="s3")`)
- No dependency on Django's `FileField` abstraction

**However**: Django's `FileField` + custom storage backends (like `S3Boto3Storage` from django-storages) already supports S3, GCS, Azure, etc. Switching from local to S3 is a settings change — no schema migration needed. The `FileField` stores a varchar path in the database; the attached storage backend handles all I/O.

The abstract pointer pattern is justified only when you need **multiple active backends per row simultaneously** (e.g., "this file is replicated to both S3 us-east-1 AND GCS eu-west-1"). For Doorito's case — one file, one backend at a time — `FileField` with a custom storage backend gives you everything the pointers give you, plus `.url`, `.delete()`, `.open()`, and admin integration for free.

**Recommendation**: Keep `FileField` with a configurable storage backend. Add `sha256` and `metadata` as separate fields alongside it. If per-instance backend routing is needed later, a custom storage class can inspect a model field to route. This preserves Django's file handling ecosystem while still supporting the new fields (sha256, metadata, content_type, etc.).

**Decision**: Keep Django's `FileField`. The abstract storage pointer design (`storage_backend`/`storage_bucket`/`storage_key`) is rejected. `FileField` retains `.url`, `.delete()`, `.open()`, admin upload widgets, and django-storages compatibility for free. New fields (`sha256`, `metadata`, `content_type`) are added alongside it. *(See Q5 in Previously Resolved Questions.)*

**Alternative if you truly want the abstract pointers**: Acknowledge the cost explicitly. The service layer PEP will need to implement URL generation, file deletion, file streaming, and admin integration from scratch. This is significant work.

---

#### 2. IngestFile — Naming Consistency

The proposed models use inconsistent naming prefixes:
- `IngestFile` (from PEP 0002's rename)
- `UploadBatch`, `UploadSession`, `UploadPart` (all use `Upload*` prefix)

If these are all in the `uploads` app and form a cohesive upload system, the naming should be consistent. Options:

1. **Rename to `UploadFile`** — consistent with `Upload*` prefix, matches the app name
2. **Rename others to `Ingest*`** — `IngestBatch`, `IngestSession`, `IngestPart` — consistent with `Ingest*` prefix
3. **Keep mixed naming** — `IngestFile` is the domain concept (ingestion), while `Upload*` describes the mechanism (uploading)

Option 3 is arguably defensible (ingestion vs mechanism), but it will confuse new contributors. Option 1 is simplest but undoes PEP 0002's work. Option 2 is consistent but `IngestPart` and `IngestSession` sound odd.

**Question for author**: Is the mixed naming intentional, or should we unify?

**Decision**: Rename `IngestFile` to `UploadFile`. All upload models use the `Upload*` prefix (`UploadBatch`, `UploadFile`, `UploadSession`, `UploadPart`), matching the `uploads` app name. This supersedes PEP 0002's `FileUpload → IngestFile` rename — the model is being completely redesigned in this PEP. *(See Q6 in Previously Resolved Questions.)*

---

#### 3. IngestFile — Status Choices

Proposed: `uploading → stored / failed / deleted`

**Concern**: The current model has `pending → ready → consumed / failed`, which represents a clear consumption lifecycle. The proposed statuses drop the `consumed` concept entirely. If downstream processing is still part of the design (and `PortalEventOutbox` suggests it is), there's no way to distinguish "stored and waiting for processing" from "stored and already processed."

**Suggestion**: Consider adding `PROCESSED` or keeping `CONSUMED`:
- `uploading → stored → processed / deleted`
- `uploading → failed`

**Decision**: Add `PROCESSED` status. The full status flow becomes: `uploading → stored → processed / deleted` and `uploading → failed`. This preserves the downstream processing lifecycle. *(See Q7 in Previously Resolved Questions.)*

Or use a separate field like `processed_at` (nullable DateTimeField) to track consumption without adding another status value.

---

#### 4. UploadBatch — Denormalized Counters

The `total_files`, `stored_files`, `failed_files` counters are denormalized. This is a well-known consistency risk:
- Concurrent uploads completing simultaneously can cause counter drift without `F()` expressions or `SELECT ... FOR UPDATE`
- Any bug in the service layer that updates `IngestFile.status` without updating `UploadBatch` counters silently corrupts the data
- The counters cannot be trusted without periodic reconciliation

**Alternatives**:
1. **Drop the counters entirely** — use `batch.files.filter(status="stored").count()` in queries. PostgreSQL is fast enough for this unless batches have thousands of files.
2. **Use annotated querysets** — `UploadBatch.objects.annotate(stored_count=Count("files", filter=Q(files__status="stored")))`. This is always-correct and costs one JOIN.
3. **Keep counters but add a `reconcile_counters()` method** — periodic correction via a management command or task.

**Recommendation**: Option 1 or 2 for now. Denormalized counters are a premature optimization. Add them later if `COUNT()` proves to be a bottleneck (it won't at this scale).

**Decision**: Option 1 — drop the denormalized counters (`total_files`, `stored_files`, `failed_files`) entirely. Use `batch.files.filter(status=...).count()` in service-layer queries. Counters can be added later as a performance optimization if needed. *(See Q8 in Previously Resolved Questions.)*

---

#### 5. UploadBatch — Is It Needed Now?

`UploadBatch` is useful for multi-file upload UX (drag-and-drop multiple files, show aggregate progress). But:
- No upload UI exists yet
- No API endpoints exist yet
- The batch concept only matters at the presentation layer

If `IngestFile` is the core entity and batching is a UX concern, `UploadBatch` can be deferred until the upload UI/API PEP. Adding a nullable `batch` FK to `IngestFile` later is a non-breaking migration.

---

**Decision**: Keep `UploadBatch` in this PEP. Batching is part of the upload data model. Defining it now ensures the schema is ready when the API PEP is built.

#### 6. UploadSession + UploadPart — Premature Abstraction?

These two models implement tus.io / S3 multipart upload semantics. This is sophisticated infrastructure, but:

- **No chunked upload endpoint exists** — the models define a contract with no consumer
- **Small files don't need sessions** — a single-request upload (POST with file body) doesn't need `UploadSession` or `UploadPart` at all
- **The OneToOne constraint is too rigid** — if `UploadSession` is OneToOne to `IngestFile`, every file implicitly has a session slot. But most files (especially small ones) should bypass chunking entirely.

**Alternative approaches**:

**A) Embedded session fields on IngestFile** — Add `upload_id` (CharField, nullable) and `upload_finished_at` (DateTimeField, nullable) to `IngestFile`. Small files set `upload_finished_at` immediately. Large files get an `upload_id` and null `upload_finished_at` until assembly completes. This is the HackSoft/direct-to-S3 pattern and works well for single-backend setups.

**B) Defer to the upload API PEP** — Define `UploadSession` and `UploadPart` when the chunked upload API is being built. The models should be co-designed with the service layer that manages chunk receipt, assembly, and retry.

**Decision**: Keep `UploadSession` and `UploadPart` in this PEP. The API PEP is next and needs these models ready. Co-designing models and services together (as decided in Q4) addresses the concern about models without consumers.

**C) Keep the separate models but make the OneToOne nullable** — `file = OneToOneField(IngestFile, null=True, on_delete=CASCADE)`. Sessions can exist before the file record is finalized. But this adds complexity.

**Recommendation**: Option B (defer). Chunking models without chunking services are dead schema. Design them together.

---

#### 7. PortalEventOutbox — Placement and Design

Several concerns:

**a) Why "Portal" prefix?** The name `PortalEventOutbox` implies a specific "portal" concept that doesn't exist in Doorito. If this is a generic event outbox, call it `EventOutbox` or `OutboxEvent`.

**b) Why in the `uploads` app?** A transactional outbox is a cross-cutting pattern. If other apps (e.g., `accounts`, future domain apps) need to emit events, they'd either import from `uploads` (wrong) or duplicate the model (worse). The outbox should live in `common/` if it's generic.

**c) Explicit FK vs payload-only pattern.** The proposed design uses `file = ForeignKey(IngestFile, CASCADE)`, which hard-couples the outbox to file uploads. The standard outbox pattern in the microservices literature (Debezium, Axon, django-outbox-pattern) uses **no FK at all**:

```python
class OutboxEvent(TimeStampedModel):
    aggregate_type = CharField(max_length=100)   # "IngestFile", "Order"
    aggregate_id = CharField(max_length=100)      # str(pk)
    event_type = CharField(max_length=100)        # "file.stored"
    payload = JSONField()                          # full serialized event data
    status = CharField(...)
    # retry fields...
```

This pattern makes the outbox record **self-contained** — consumers read the payload, they don't join back to the source table. It also means the outbox works for any model type without schema changes.

**d) No delivery worker** — without a polling task or CDC mechanism, outbox rows accumulate forever. Is it premature to define the schema without the drain?

**Recommendation**: Either (a) defer the outbox to a dedicated "event infrastructure" PEP where the model, delivery worker, and consumer pattern are designed together, or (b) use the aggregate/payload pattern in `common/` so it's reusable across apps.

**Decision**: Defer the event outbox to a dedicated event infrastructure PEP. Remove `PortalEventOutbox` from PEP 0003 scope entirely. The future PEP should:
- Name the model `OutboxEvent` (consistent noun-phrase naming)
- Place it in `common/` (cross-cutting, reusable across apps)
- Use the aggregate/payload pattern with no FK (self-contained events)
- Include the delivery worker (polling task or CDC)

This reduces PEP 0003 from 5 models to 4: `UploadBatch`, `UploadFile`, `UploadSession`, `UploadPart`. *(See Q9 in Previously Resolved Questions.)*

---

#### 8. UUID v4 vs UUID v7

The plan uses `default=uuid.uuid4` (random UUIDs). UUID v7 (time-ordered) offers measurably better PostgreSQL B-tree index performance:
- ~49% faster inserts (less page splitting)
- ~22% smaller indexes (better clustering)
- Natural time-ordering (no need for `-created_at` ordering in most cases)

Python 3.14 adds `uuid.uuid7()` natively. For earlier Python versions, the `uuid6` or `uuid_utils` packages provide RFC 9562-compliant UUID v7. Django's `UUIDField` is version-agnostic — it stores 16 bytes regardless.

**Recommendation**: Use UUID v7 if the project targets Python 3.14+ or is willing to add the `uuid6` dependency. Otherwise, UUID v4 is fine at Doorito's scale — the performance difference only matters above ~100K rows.

**Question for author**: What Python version does Doorito target? Is adding a small dependency (`uuid6`) acceptable for UUID v7 support?

**Decision**: Use UUID v7. Doorito runs on Python 3.12.3 which lacks native `uuid.uuid7()` (added in Python 3.14). Add the `uuid_utils` package as a dependency — it provides `uuid_utils.uuid7()` following RFC 9562 with a fast Rust-based implementation. All model UUID PKs use `default=uuid_utils.uuid7`. *(See Q10 in Previously Resolved Questions.)*

---

### Cross-Cutting Questions

#### C1: Should models and services be co-designed?

The PEP explicitly defers services ("models only"). But models without services are like database schemas without stored procedures — they define structure but not behavior. The risk is that the model design doesn't quite fit the service needs discovered later, requiring migrations.

**Counter-argument**: The model shapes are stable enough (UUID PKs, status fields, FKs) that services can adapt. Defining models first is a legitimate architectural approach — it establishes the data contracts.

**Question for author**: Are you comfortable with the risk that some fields may need adjustment when services are built? Or would you prefer to sketch service signatures alongside model definitions?

**Decision**: Include service signatures alongside model definitions in the plan. Each model section should list the core service functions that operate on it, with their signatures and brief descriptions. This ensures the data model and service layer are co-designed. *(See Q11 in Previously Resolved Questions.)*

#### C2: How many models does Doorito actually need right now?

If the goal is to "move beyond the skeleton," the minimum viable extension might be:

1. **Redesigned `IngestFile`** — UUID PK, `sha256`, `metadata`, new status set, nullable user FK. Keep `FileField` for now.
2. That's it.

Everything else (`UploadBatch`, `UploadSession`, `UploadPart`, `PortalEventOutbox`) is infrastructure for features that don't exist yet. YAGNI applies.

**Question for author**: What's the near-term roadmap? Which features will be built next? That should drive which models are needed now.

**Decision**: All upload models are needed now — we are modelling a broader system. With the outbox deferred to a separate PEP (see section 7 decision), the scope is 4 models: `UploadBatch`, `UploadFile`, `UploadSession`, `UploadPart`. The API PEP is next and depends on these models being ready.

---

## Previously Resolved Questions

### Q1: Should new models inherit from TimeStampedModel or use explicit timestamp fields?

**Resolution (plan.md)**: Use `TimeStampedModel` for all models. Consistent with project convention. Models needing extra timestamps (like `delivered_at`) add them alongside inherited fields.

---

### Q2: What happens to existing services, tasks, and tests?

**Resolution (plan.md)**: Delete them. The existing code is tightly coupled to `FileField` and the old status lifecycle. New services and tasks will be rebuilt in a future PEP.

---

### Q3: Should PEP 0002 be completed first?

**Resolution (plan.md)**: Require PEP 0002 completion first. Code-level renames must be done before PEP 0003 starts. The PEP 0002 database migration is moot (table is being dropped).

---

### Q4: Should all 5 models and services be in this PEP, or phased across multiple PEPs?

**Date**: 2026-02-25

**Context**: The Design Review raised concerns about delivering 5 models without services — dead schema with no operational code. The alternative was phasing across PEP 0003–0006, each delivering one model with its services.

**Resolution**: All 5 models and their core services will be delivered in this PEP. The phased approach adds migration churn and PEP overhead. A single PEP keeps the related upload infrastructure cohesive. Services will be written alongside models so each model ships with operational code and testable behavior.

**Impact**: summary.md "Out of Scope" section updated — services are no longer out of scope. plan.md must add service implementation steps and service tests.

---

### Q5: Should IngestFile keep Django's FileField or switch to abstract storage pointers?

**Date**: 2026-02-25

**Context**: The original design replaced `FileField` with three `CharField` pointers (`storage_backend`, `storage_bucket`, `storage_key`) for storage-agnostic file references. The Design Review argued this loses `.url`, `.delete()`, `.open()`, admin widgets, and django-storages compatibility — all of which `FileField` provides for free.

**Resolution**: Keep Django's `FileField`. The abstract storage pointer design is rejected. `FileField` with a configurable storage backend already supports local FS and S3 via django-storages. Per-instance backend routing (if ever needed) can be handled by a custom storage class. New fields (`sha256`, `metadata`, `content_type`, `size_bytes`) are added alongside `FileField`.

**Impact**: summary.md IngestFile comparison table and model description updated. plan.md IngestFile model definition, admin fields, and acceptance criteria updated. The `storage_backend`/`storage_bucket`/`storage_key` fields are removed. The existing `file = FileField(upload_to="uploads/%Y/%m/")` is retained.

---

### Q6: Should IngestFile be renamed to UploadFile for naming consistency?

**Date**: 2026-02-25

**Context**: The Design Review identified inconsistent naming between `IngestFile` (from PEP 0002) and the other `Upload*` models (`UploadBatch`, `UploadSession`, `UploadPart`). Three options were considered: rename to `UploadFile`, rename others to `Ingest*`, or keep mixed naming.

**Resolution**: Rename `IngestFile` to `UploadFile`. The `Upload*` prefix is consistent with the `uploads` app name and the other models. PEP 0002's `FileUpload → IngestFile` rename is superseded — the model is being completely redesigned in PEP 0003 anyway.

**Impact**: All PEP 0003 documents updated to use `UploadFile`. Model class name, `db_table`, `related_name`, admin class, service functions, task name, and test references all change from `IngestFile`/`ingest_file` to `UploadFile`/`upload_file`.

---

### Q7: Should UploadFile add a PROCESSED status?

**Date**: 2026-02-25

**Context**: The proposed status choices (`uploading/stored/failed/deleted`) dropped the `consumed` concept from the original model. Without a post-storage status, there's no way to distinguish files waiting for processing from files already processed.

**Resolution**: Add `PROCESSED` status. The full status flow is: `uploading → stored → processed / deleted` and `uploading → failed`. This preserves the downstream processing lifecycle needed by future event consumers.

**Impact**: summary.md and plan.md updated with 5 status values (`UPLOADING`, `STORED`, `PROCESSED`, `FAILED`, `DELETED`).

---

### Q8: Should UploadBatch keep denormalized counters?

**Date**: 2026-02-25

**Context**: The Design Review raised concerns about `total_files`, `stored_files`, `failed_files` counters: consistency risk with concurrent updates, silent corruption if service layer bugs skip counter updates, and inability to trust without reconciliation.

**Resolution**: Drop the denormalized counters entirely (Option 1). Use `batch.files.filter(status=...).count()` in service-layer queries. PostgreSQL handles this efficiently at Doorito's scale. Counters can be added later as a performance optimization if `COUNT()` proves to be a bottleneck.

**Impact**: summary.md and plan.md updated — `total_files`, `stored_files`, `failed_files` removed from `UploadBatch`. The `update_batch_counters` service function is removed.

---

### Q9: Should PortalEventOutbox be in PEP 0003 or deferred to a separate PEP?

**Date**: 2026-02-25

**Context**: The Design Review raised multiple concerns about the outbox: (a) "Portal" prefix is meaningless, (b) placing it in `uploads/` limits reuse, (c) the FK to IngestFile hard-couples it to uploads, (d) no delivery worker means rows accumulate forever. These concerns span naming, placement, schema design, and operational completeness.

**Resolution**: Defer the event outbox to a dedicated event infrastructure PEP. Remove it from PEP 0003 scope entirely. The future PEP should name the model `OutboxEvent`, place it in `common/`, use the aggregate/payload pattern (no FK to specific models), and include the delivery worker.

**Impact**: PEP 0003 reduces from 5 models to 4. The `emit_event` service function, outbox admin class, outbox tests, and all outbox references are removed from the plan. The `PortalEventOutbox` model section is removed from the summary.

---

### Q10: Should models use UUID v7 instead of UUID v4?

**Date**: 2026-02-25

**Context**: UUID v7 (time-ordered, RFC 9562) offers better B-tree index performance (~49% faster inserts, ~22% smaller indexes) and natural time-ordering. Python 3.12.3 (Doorito's runtime) lacks native `uuid.uuid7()` — that's added in Python 3.14.

**Resolution**: Use UUID v7 via the `uuid_utils` package. This adds a small dependency but provides RFC 9562-compliant UUID v7 generation with a fast Rust-based implementation. All model UUID PKs use `default=uuid_utils.uuid7`.

**Impact**: Add `uuid_utils` to `requirements.in` and recompile lockfiles. All UUID PK defaults change from `uuid.uuid4` to `uuid_utils.uuid7`. A new prerequisite step is added to the plan for dependency installation.

---

### Q11: Should service signatures be included alongside model definitions?

**Date**: 2026-02-25

**Context**: The Design Review asked whether models and services should be co-designed. The risk of defining models first is that the schema doesn't quite fit service needs, requiring later migrations.

**Resolution**: Include service signatures alongside model definitions. Each model section in the plan lists the core service functions that operate on it. This ensures the data model and service layer are designed together.

**Impact**: plan.md model definitions updated with associated service signatures.
