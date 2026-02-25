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

- **No services are included** — the models are defined without business logic to operate on them. This means models like `UploadSession` and `UploadPart` define a chunked upload contract but no code to fulfill it.
<!-- Review: Add services and business logic -->
- **No consumers exist** — `PortalEventOutbox` defines a transactional outbox schema but no delivery worker. It will accumulate rows with no way to drain them.
<!-- Review: Will be implemented later -->
- **Testing is limited to CRUD** — without services, tests can only verify field defaults, FK cascades, and constraints. The interesting behavior (status transitions, counter updates, chunk assembly) is untestable.
<!-- Review: services will be implemented add test accordingly -->

**Alternative: Phase the models across multiple PEPs.**

| Phase | Models | Rationale |
|-------|--------|-----------|
| PEP 0003 | `IngestFile` (redesigned) | Core entity. Everything depends on it. Can be shipped with basic services. |
| PEP 0004 | `UploadBatch` | Grouping layer. Only needed when multi-file upload UX is built. |
| PEP 0005 | `UploadSession` + `UploadPart` | Chunking infrastructure. Only needed when resumable uploads are required. |
| PEP 0006 | `PortalEventOutbox` (or equivalent) | Event infrastructure. Only needed when downstream consumers exist. |

**Trade-off**: Phasing means more migrations and more PEPs, but each PEP is smaller, testable end-to-end, and ships with services. Doing all 5 at once means a large schema with no operational code — essentially scaffolding.

**Question for author**: Do you want all 5 models now (schema-first, services later), or would you prefer to phase them so each PEP delivers a working vertical slice?
<!-- Review: Work them under this PEP update PEP scope and the PEP files to solve this issue -->

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
<!-- Review: Keep the current FileField -->

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

---

#### 3. IngestFile — Status Choices

Proposed: `uploading → stored / failed / deleted`

**Concern**: The current model has `pending → ready → consumed / failed`, which represents a clear consumption lifecycle. The proposed statuses drop the `consumed` concept entirely. If downstream processing is still part of the design (and `PortalEventOutbox` suggests it is), there's no way to distinguish "stored and waiting for processing" from "stored and already processed."

**Suggestion**: Consider adding `PROCESSED` or keeping `CONSUMED`:
- `uploading → stored → processed / deleted`
- `uploading → failed`

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

---

#### 5. UploadBatch — Is It Needed Now?

`UploadBatch` is useful for multi-file upload UX (drag-and-drop multiple files, show aggregate progress). But:
- No upload UI exists yet
- No API endpoints exist yet
- The batch concept only matters at the presentation layer

If `IngestFile` is the core entity and batching is a UX concern, `UploadBatch` can be deferred until the upload UI/API PEP. Adding a nullable `batch` FK to `IngestFile` later is a non-breaking migration.

---

#### 6. UploadSession + UploadPart — Premature Abstraction?

These two models implement tus.io / S3 multipart upload semantics. This is sophisticated infrastructure, but:

- **No chunked upload endpoint exists** — the models define a contract with no consumer
- **Small files don't need sessions** — a single-request upload (POST with file body) doesn't need `UploadSession` or `UploadPart` at all
- **The OneToOne constraint is too rigid** — if `UploadSession` is OneToOne to `IngestFile`, every file implicitly has a session slot. But most files (especially small ones) should bypass chunking entirely.

**Alternative approaches**:

**A) Embedded session fields on IngestFile** — Add `upload_id` (CharField, nullable) and `upload_finished_at` (DateTimeField, nullable) to `IngestFile`. Small files set `upload_finished_at` immediately. Large files get an `upload_id` and null `upload_finished_at` until assembly completes. This is the HackSoft/direct-to-S3 pattern and works well for single-backend setups.

**B) Defer to the upload API PEP** — Define `UploadSession` and `UploadPart` when the chunked upload API is being built. The models should be co-designed with the service layer that manages chunk receipt, assembly, and retry.

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

---

#### 8. UUID v4 vs UUID v7

The plan uses `default=uuid.uuid4` (random UUIDs). UUID v7 (time-ordered) offers measurably better PostgreSQL B-tree index performance:
- ~49% faster inserts (less page splitting)
- ~22% smaller indexes (better clustering)
- Natural time-ordering (no need for `-created_at` ordering in most cases)

Python 3.14 adds `uuid.uuid7()` natively. For earlier Python versions, the `uuid6` or `uuid_utils` packages provide RFC 9562-compliant UUID v7. Django's `UUIDField` is version-agnostic — it stores 16 bytes regardless.

**Recommendation**: Use UUID v7 if the project targets Python 3.14+ or is willing to add the `uuid6` dependency. Otherwise, UUID v4 is fine at Doorito's scale — the performance difference only matters above ~100K rows.

**Question for author**: What Python version does Doorito target? Is adding a small dependency (`uuid6`) acceptable for UUID v7 support?

---

### Cross-Cutting Questions

#### C1: Should models and services be co-designed?

The PEP explicitly defers services ("models only"). But models without services are like database schemas without stored procedures — they define structure but not behavior. The risk is that the model design doesn't quite fit the service needs discovered later, requiring migrations.

**Counter-argument**: The model shapes are stable enough (UUID PKs, status fields, FKs) that services can adapt. Defining models first is a legitimate architectural approach — it establishes the data contracts.

**Question for author**: Are you comfortable with the risk that some fields may need adjustment when services are built? Or would you prefer to sketch service signatures alongside model definitions?

#### C2: How many models does Doorito actually need right now?

If the goal is to "move beyond the skeleton," the minimum viable extension might be:

1. **Redesigned `IngestFile`** — UUID PK, `sha256`, `metadata`, new status set, nullable user FK. Keep `FileField` for now.
2. That's it.

Everything else (`UploadBatch`, `UploadSession`, `UploadPart`, `PortalEventOutbox`) is infrastructure for features that don't exist yet. YAGNI applies.

**Question for author**: What's the near-term roadmap? Which features will be built next? That should drive which models are needed now.

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
