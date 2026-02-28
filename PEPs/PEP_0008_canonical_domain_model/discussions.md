# PEP 0008: Canonical Domain Model for OSS Ingest Portal — Discussions

| Field | Value |
|-------|-------|
| **PEP** | 0008 |
| **Summary** | [summary.md](summary.md) |

---

## Resolved Questions

### Q: What should the Django app name be for the portal models?
- **Resolved**: 2026-02-27
- **Answer**: The app should be named `portal`. The rollback plan already references `python manage.py migrate portal zero`, and the impact section says "New models in a portal/ingest app." Use `portal` as the canonical app name.
- **Rationale**: `portal` is concise, matches the "OSS Ingest Portal" naming in the title, and avoids the verbose `ingest_portal`. The `db_table` prefix for all models should be `portal_` (e.g., `portal_ingest_file`, `portal_upload_session`).

### Q: Should IngestFile include an `error_message` field for failure context?
- **Resolved**: 2026-02-27
- **Answer**: Yes. The existing `UploadFile` model has `error_message = models.TextField(blank=True)` which is populated on validation failure. `IngestFile` should include the same field since the `FAILED` status needs context.
- **Rationale**: Without an error message field, diagnosing why a file entered `FAILED` status requires log trawling. The existing pattern in `uploads/models.py` confirms this is established convention.

### Q: Should IngestFile include a `metadata` JSONField?
- **Resolved**: 2026-02-27
- **Answer**: Yes. The existing `UploadFile` has `metadata = models.JSONField(default=dict, blank=True)` for flexible non-sensitive metadata (e.g., xml_root, sniffed_type). `IngestFile` should include this for parity and extensibility.
- **Rationale**: Without a metadata field, any future need for semi-structured per-file data would require a migration. The JSONField costs nothing when empty and the existing pattern supports it.

### Q: What indexes should IngestFile have beyond the status field?
- **Resolved**: 2026-02-27
- **Answer**: Replicate the existing `UploadFile` index strategy: composite index on `["uploaded_by", "-created_at"]` (user's file list), single index on `["status"]` (cleanup/status queries), and `db_index=True` on `sha256` (dedup lookups).
- **Rationale**: These indexes are proven in the existing upload models and match the expected query patterns for the ingest portal. The plan's Step 2 mentions `sha256` but doesn't specify the index strategy explicitly.

### Q: Should PortalEventOutbox use `attempts` or `attempt_count` for the retry counter?
- **Resolved**: 2026-02-27
- **Answer**: Use `attempts` to match `common.OutboxEvent` (`common/models.py:41`).
- **Rationale**: The two outbox models serve analogous roles. Using different field names for the same concept creates cognitive overhead when developers work across both models. Consistency with the established pattern wins over marginal descriptiveness.

### Q: Should PortalEventOutbox include a SENDING status?
- **Resolved**: 2026-02-27
- **Answer**: No. Use the same three statuses as `common.OutboxEvent`: PENDING, DELIVERED, FAILED. The plan's Step 6 listed (PENDING, SENDING, DELIVERED, FAILED) but `OutboxEvent` (`common/models.py:27-30`) has no SENDING status. Adding a fourth status without justification diverges from the proven pattern.
- **Rationale**: The SENDING status would represent an in-flight delivery attempt, but `OutboxEvent` handles this implicitly through `next_attempt_at` and `attempts`. Adding SENDING creates a state that must be recovered from (e.g., process crash during delivery) without adding value. If SENDING is needed for observability, it can be added later in PEP 0017 when the delivery dispatcher is implemented.

### Q: Should PEP 0008 remove FileField or keep it alongside new storage fields?
- **Resolved**: 2026-02-27
- **Answer**: Defer storage field changes entirely to PEP 0009 (Option 3 from the open thread). PEP 0008 keeps the existing `FileField` on IngestFile unchanged. The explicit storage fields (`storage_backend`, `storage_bucket`, `storage_key`) are added by PEP 0009 when the storage abstraction service is ready to populate them.
- **Rationale**: Removing `FileField` breaks 5 code paths immediately: `create_upload_file()` saves via `file=file`, `mark_file_deleted()` calls `upload_file.file.delete()`, `cleanup_expired_upload_files_task()` calls `upload.file.delete()`, and both `create_upload_file()` and `notify_expiring_files()` reference `upload.file.url` in event payloads. Adding blank storage fields alongside FileField (Option 2) adds fields that nothing populates or reads, creating dead schema. Option 3 is cleanest — PEP 0008 focuses on app rename, status simplification, and PortalEventOutbox. Storage migration is PEP 0009's responsibility.

### Q: What `db_table` should PortalEventOutbox use?
- **Resolved**: 2026-02-27
- **Note (2026-02-28)**: The example names in the original answer (`portal_ingest_file`) are stale — the IngestFile rename was cancelled. The answer (`portal_event_outbox`) remains correct. The `db_table` naming for existing models (currently `upload_batch`, `upload_file`, etc.) is addressed in a separate open thread.
- **Answer**: `portal_event_outbox`. This follows the `portal_` prefix convention for new tables in the portal app.
- **Rationale**: Consistent with the `portal_` prefix for new portal models, and parallel to `common.OutboxEvent`'s `outbox_event` table name pattern.

### Q: Should PortalEventOutbox include a `delivered_at` field?
- **Resolved**: 2026-02-27
- **Answer**: Yes. `common.OutboxEvent` has `delivered_at = models.DateTimeField(null=True, blank=True)` at `common/models.py:44`. The plan's Step 6 omits this field. Include it for consistency.
- **Rationale**: The `delivered_at` timestamp is essential for delivery auditing, SLA tracking, and the cleanup task (which uses it to determine retention eligibility). Omitting it would force PEP 0017 to add a migration for a field that should have been there from the start.

### Q: What happens to `finalize_batch()` when PROCESSED status is removed?
- **Resolved**: 2026-02-27
- **Answer**: Update `finalize_batch()` at `uploads/services/uploads.py:258` to use `success_statuses = {IngestFile.Status.STORED}` (removing the `PROCESSED` member from the set). Also remove the `mark_file_processed()` function entirely (lines 149-177) and the `mark_file_deleted()` function (lines 197-212), since their target statuses no longer exist.
- **Rationale**: These are direct consequences of simplifying from 5 statuses to 3. The plan mentions status simplification in Step 2 but doesn't explicitly address the dependent service functions. The plan should include a step for updating service functions.

### Q: What `aggregate_type` should be used in outbox events after the UploadFile→IngestFile rename?
- **Resolved**: 2026-02-27
- **Superseded**: 2026-02-28 — The 2026-02-28 naming decision ("Keep all models as Upload*") eliminates the model rename. `aggregate_type` remains `"UploadFile"` with no change needed. See Design Decision "Keep all models as Upload*".
- **Answer** (original, now superseded): Change from `"UploadFile"` to `"IngestFile"` in `create_upload_file()` and `notify_expiring_files()` service functions.
- **Rationale** (original): The `aggregate_type` should match the model class name for consistency. Any existing `OutboxEvent` rows with `aggregate_type="UploadFile"` are historical artifacts in the common outbox and won't affect the new `PortalEventOutbox`.

### Q: What names should the PortalEventOutbox index and constraint use?
- **Resolved**: 2026-02-28
- **Answer**: Use `idx_portal_outbox_pending_next` for the partial index on `next_attempt_at WHERE status="pending"`, and `unique_portal_event_type_idempotency_key` for the unique constraint on `(event_type, idempotency_key)`.
- **Rationale**: Database index and constraint names must be globally unique. `common.OutboxEvent` uses `idx_outbox_pending_next` and `unique_event_type_idempotency_key`. Prefixing with `portal_` avoids name collisions while maintaining a clear naming convention.

### Q: What existing tests must be updated for the status simplification and app rename?
- **Resolved**: 2026-02-28
- **Answer**: The plan must include a test update step covering these changes:
  - **Remove test classes**: `TestMarkFileProcessed` and `TestMarkFileDeleted` in `test_services.py` (test removed functions)
  - **Update assertions**: `test_status_choices` in `test_models.py` — change expected `UploadFile.Status.values` from `{"uploading", "stored", "processed", "failed", "deleted"}` to `{"uploading", "stored", "failed"}`
  - **Fix test logic**: `test_skips_non_stored_files` in `test_services.py` — change `UploadFile.Status.PROCESSED` to `UploadFile.Status.FAILED` (or remove if redundant with existing FAILED test)
  - **Update all imports**: Every `from uploads.*` import across 6 test files → `from portal.*`
  - **Update module refs**: `from uploads import tasks` in `test_tasks.py:86` → `from portal import tasks`
- **Rationale**: The plan's testing section lists new tests but doesn't account for existing tests that reference removed statuses, removed functions, or old import paths. Without this step, `pytest` will fail with ImportError and AttributeError before any new tests can run.

### Q: How should the migration files be handled during the app rename?
- **Resolved**: 2026-02-28
- **Answer**: The physical directory rename (`uploads/` → `portal/`) includes the migrations directory. Existing `uploads/migrations/0001_initial.py` becomes `portal/migrations/0001_initial.py`. A new manual migration `portal/migrations/0002_rename_app.py` is then created to update Django's internal tables (`django_content_type`, `django_migrations`). The migration's `dependencies` reference `("portal", "0001_initial")`.
- **Rationale**: Django resolves app labels from the `migrations/` directory within the app module. If the old migrations aren't moved, Django treats `portal` as a new app with no history and tries to recreate all tables. The rename migration must be manually written (not auto-generated) because it operates on Django system tables, not model schema.

### Q: Should the `upload_to` path on FileField change after the app rename?
- **Resolved**: 2026-02-28
- **Answer**: No. Keep `upload_to="uploads/%Y/%m/"` unchanged. It's a storage path convention, not a code reference. Changing it would split the file namespace between old and new uploads. PEP 0009 redesigns storage paths.
- **Rationale**: Existing files in Dev (`MEDIA_ROOT/uploads/...`) and Production (S3 prefix `uploads/...`) would become orphaned if the path changes. The `upload_to` string is independent of the app name.

## Design Decisions

### Decision: Separate PortalEventOutbox vs. reusing common.OutboxEvent
- **Date**: 2026-02-27
- **Context**: The `common.OutboxEvent` model already provides a complete transactional outbox with delivery services (`emit_event`, `process_pending_events`, `cleanup`), webhook integration, and Celery tasks. PEP 0008 proposes a separate `PortalEventOutbox` model for "domain isolation and portal-specific event schemas and delivery policies."
- **Decision**: This is accepted as proposed, but the trade-offs should be explicitly acknowledged.
- **Alternatives rejected**:
  - **Reuse `common.OutboxEvent` directly**: Simpler, zero duplication, proven delivery infrastructure. Rejected because portal events may need different delivery semantics (not just webhooks), different retry policies, or different payload schemas. The `aggregate_type`/`aggregate_id` pattern in `OutboxEvent` could work, but coupling to the common delivery pipeline limits future flexibility.
  - **Subclass `OutboxEvent`**: Multi-table inheritance adds join overhead and complicates queries. Rejected for performance.
- **Note**: PEP 0017 (Durable Outbox Dispatcher) will need to implement delivery infrastructure for `PortalEventOutbox` from scratch. This is a deliberate duplication cost accepted for domain isolation.

### Decision: Explicit storage fields vs. Django FileField
- **Date**: 2026-02-27
- **Context**: The plan's Step 2 specifies `storage_backend`, `storage_bucket`, `storage_key` as explicit CharField/TextField fields on `IngestFile`. The existing `UploadFile` uses Django's `FileField(upload_to="uploads/%Y/%m/")` which abstracts storage behind Django's storage backend API.
- **Decision**: The explicit storage fields approach is accepted. This aligns with the portal's need for fine-grained storage control (PEP 0009: Storage Backend Abstraction) and decouples the model from Django's storage API.
- **Alternatives rejected**:
  - **Django `FileField`**: Simpler Django integration, auto cleanup via `FieldFile.delete()`, works with `default_storage`. Rejected because the portal needs to support multiple storage backends per deployment, explicit bucket routing, and the abstraction layer in PEP 0009 will manage storage operations outside of Django's `FileField` lifecycle.

### Decision: Evolve uploads app into portal (not coexist or replace)
- **Date**: 2026-02-27
- **Context**: The codebase has a fully implemented `uploads` app with `UploadBatch`, `UploadFile`, `UploadSession`, and `UploadPart` models that are structurally ~80% aligned with the proposed portal models. Three options were considered: coexist (parallel model hierarchies), replace (deprecate + migrate), or evolve (rename/refactor incrementally).
- **Decision**: Evolve the `uploads` app into `portal`. Rename the app directory and module, refactor existing models to add portal-specific fields and invariants (e.g., explicit storage fields on IngestFile, PortalEventOutbox), and preserve the existing migration history via a rename migration.
- **Alternatives rejected**:
  - **Coexist**: Two parallel upload model hierarchies (uploads + portal) creates confusion and duplication. Both serve file uploads with chunking, leading to ongoing maintenance burden and unclear ownership.
  - **Replace**: A clean break (new app + deprecate old) requires data migration from the existing tables and temporarily breaks the frontend upload page at `/app/upload/`. More disruptive than necessary given the structural overlap.
- **Rationale**: The existing models already provide the core structure (batch → file → session → parts, status lifecycles, idempotency keys, SHA256 hashing, TimeStampedModel + uuid7). Evolving avoids duplication, preserves working functionality, and allows incremental addition of portal-specific invariants. The rename from `uploads` to `portal` signals the expanded scope from "file uploads" to "OSS ingest portal."
- **Impact on plan**: Step 1 changes from "Create new portal app" to "Rename and evolve the existing uploads app." Subsequent steps become model modifications rather than greenfield creation for overlapping models.

### Decision: UploadSession as 1:1 with IngestFile (no retry sessions)
- **Date**: 2026-02-27
- **Context**: The summary states "UploadSession (1:1 with IngestFile)" using a OneToOneField, matching the existing `uploads.UploadSession` pattern. This means a failed upload cannot create a new session for the same file — the file must be re-created.
- **Decision**: Accepted as proposed. The 1:1 constraint keeps the model simple. If an upload fails, the client creates a new `IngestFile` + `UploadSession` pair rather than attaching a retry session to an existing file.
- **Alternatives rejected**:
  - **1:N (ForeignKey)**: Allows multiple upload attempts per file. More flexible but adds complexity — need to determine "active" session, handle concurrent sessions, etc. Rejected for initial implementation; can be relaxed later if needed (OneToOne → ForeignKey is a backward-compatible migration).

### Decision: PortalEventOutbox uses generic aggregate_type/aggregate_id pattern
- **Date**: 2026-02-27
- **Context**: The plan's Step 6 specified a FK to IngestFile on `PortalEventOutbox`. The existing `common.OutboxEvent` uses `aggregate_type` (CharField) + `aggregate_id` (CharField) without a FK, allowing it to reference any model. PEP 0016 (Event Schema) hasn't been drafted yet and may define batch-level or session-level events, not just file-scoped events.
- **Decision**: Use the generic `aggregate_type`/`aggregate_id` pattern (Option 2), matching the `common.OutboxEvent` convention.
- **Alternatives rejected**:
  - **FK to IngestFile**: Enforces referential integrity but limits events to file-scoped only. Rejected because portal events may also relate to batches (`batch.completed`), sessions (`session.failed`), or other portal entities as PEP 0016 evolves.
  - **Nullable FK to IngestFile + nullable FK to UploadBatch**: Covers two entity types with integrity but becomes awkward if more event sources are added. Not extensible.
- **Rationale**: The generic pattern is proven in `common.OutboxEvent`, keeps the model flexible for future event schemas defined in PEP 0016, and avoids painting the outbox into a file-only corner. The trade-off (no FK integrity) is acceptable because outbox events are created in the service layer within the same transaction as the aggregate mutation, and the service layer enforces the STORED invariant for file events.

### Decision: STORED-only outbox invariant is kept (enforced in service layer)
- **Date**: 2026-02-27
- **Context**: The acceptance criterion states "PortalEventOutbox entries cannot be created unless the associated file is STORED." This would prevent emitting events for `file.uploading`, `file.failed`, `batch.created`, etc. The question was whether this constraint is too restrictive.
- **Decision**: Keep the invariant (Option 1). Only emit `PortalEventOutbox` events for files in STORED status. Other lifecycle events (`file.failed`, `batch.created`) can use `common.OutboxEvent` if needed, or the invariant can be relaxed in PEP 0016 when event schemas are formally defined.
- **Alternatives rejected**:
  - **Relax the invariant**: Allowing outbox entries for any status risks cluttering the portal outbox with events for files that never reach STORED. Premature flexibility.
  - **Defer to service layer only (no model-level convention)**: Leaves the constraint implicit. Rejected because the PEP should document the design intent even if enforcement is in the service layer, not at the DB level.
- **Rationale**: The portal outbox's primary purpose is notifying downstream systems (AI runner) that a file is ready for processing. Non-STORED events are informational, not actionable, and are better served by the existing `common.OutboxEvent` infrastructure. This keeps the portal outbox focused and its consumers simple.

### Decision: UploadBatch counters computed via annotation (not denormalized)
- **Date**: 2026-02-27
- **Context**: The plan's Step 5 raised the question of adding denormalized counter fields (`total_files`, `stored_count`, `failed_count`) to `UploadBatch`. The existing `uploads.UploadBatch` has no counter fields.
- **Decision**: Compute batch counters via queryset annotation (Option 2). No counter fields are added to the model.
- **Alternatives rejected**:
  - **Denormalized counter fields**: Fast reads but require careful maintenance with F-expressions or `select_for_update` on every file status change. Introduces data drift risk and consistency bugs.
  - **Hybrid (store total_files, compute rest)**: Marginal benefit over full annotation, still requires maintenance for the stored field.
- **Rationale**: Batch sizes in the portal are expected to be modest (tens to low hundreds of files). Annotation queries (`Count`, `Case`/`When`) are efficient at this scale and eliminate consistency concerns. If performance becomes an issue at scale, denormalized counters can be added as a targeted optimization in a future PEP.

### Decision: Defer storage field changes to PEP 0009
- **Date**: 2026-02-27
- **Context**: The plan's Step 2 originally specified replacing `FileField` with explicit `storage_backend`, `storage_bucket`, `storage_key` fields. Research identified that 5 code paths depend on `FileField` and would break before PEP 0009 provides a replacement storage abstraction.
- **Decision**: PEP 0008 keeps the existing `FileField` on UploadFile unchanged. Storage fields are added by PEP 0009.
- **Alternatives rejected**:
  - **Remove FileField immediately (original plan)**: Breaks `create_upload_file()`, `mark_file_deleted()`, `cleanup_expired_upload_files_task()`, `notify_expiring_files()`, and event payloads. Creates a gap between PEP 0008 and PEP 0009 where upload functionality is non-operational.
  - **Keep FileField alongside new storage fields**: Adds three blank fields that nothing reads or writes. Dead schema with no benefit until PEP 0009.
- **Rationale**: PEP 0008's scope is narrowed to: app rename, status simplification (5→3), PortalEventOutbox addition, and necessary service function updates. This keeps PEP 0008 focused and avoids coupling it to PEP 0009's storage abstraction timeline.
- **Impact on plan**: Step 2 is simplified — no storage field changes. The `file = models.FileField(upload_to="uploads/%Y/%m/")` remains on UploadFile.
- **Impact on summary**: The "storage pointer" in the model invariant ("STORED implies sha256 + size_bytes + storage pointer") remains the existing `FileField` for now. PEP 0009 redefines it as the explicit storage fields.
- **Impact on acceptance criteria**: Criterion "File cannot be marked STORED without required metadata (sha256, size_bytes, storage pointer)" — the "storage pointer" is the existing `FileField` (non-blank) until PEP 0009.

### Decision: PEP 0008 must include service function updates (not just models)
- **Date**: 2026-02-27
- **Context**: The summary's "Out of Scope" says "Service layer implementation beyond model-level validation" is excluded. However, the app rename and status simplification break existing service functions at `uploads/services/uploads.py` and `uploads/services/sessions.py`. These functions must be updated for the rename to work.
- **Decision**: PEP 0008 includes updating existing service functions to reflect the app rename and status simplification. This is maintenance of existing code, not new service layer implementation.
- **Scope of service changes**:
  - Update all imports from `uploads.*` to `portal.*`
  - Remove `mark_file_processed()` and `mark_file_deleted()` functions (target statuses removed)
  - Update `finalize_batch()` to use `{UploadFile.Status.STORED}` only (remove PROCESSED from success set)
  - Update `cleanup_expired_upload_files_task()` imports
- **NOT in scope**: New service layer features (chunked upload orchestration, storage abstraction, etc.)

### Decision: Include minimal service enforcement in PEP 0008
- **Date**: 2026-02-28
- **Context**: The summary's "Out of Scope" excluded "Service layer implementation beyond model-level validation." However, acceptance criteria #2 and #3 explicitly require service layer enforcement of the STORED invariant and outbox guard. The existing service functions at `uploads/services/uploads.py` and `uploads/services/sessions.py` must be updated anyway for the app rename and status simplification.
- **Decision**: Include minimal service enforcement in PEP 0008. The out-of-scope section is clarified to distinguish between maintaining existing service functions (in scope) and building new service layer features (out of scope).
- **Alternatives rejected**:
  - **Defer acceptance criteria to later PEP**: Would leave documented invariants unenforced. The existing `create_upload_file()` function is already being modified; adding the STORED check is trivial.
  - **Model-level validation (clean/pre_save)**: Mixes validation concerns into the model layer. The existing pattern uses service-layer enforcement, which is consistent with `aikb/conventions.md`.
- **Rationale**: The existing services already exist and require modification. Adding the STORED invariant check is a minimal addition to an already-required edit, not a new service layer feature.
- **Impact on summary**: Out-of-scope section updated to read "New service layer features (chunked upload orchestration, storage abstraction)" instead of the blanket "Service layer implementation beyond model-level validation."

### Decision: Keep all models as Upload* (no UploadFile→IngestFile rename)
- **Date**: 2026-02-28
- **Context**: PEP 0008 originally proposed renaming `UploadFile` to `IngestFile` while keeping `UploadSession`, `UploadPart`, `UploadBatch` with their Upload* prefix. This created a mixed-prefix naming scheme within the same domain.
- **Decision**: Keep all four models with their Upload* prefix: `UploadFile`, `UploadSession`, `UploadPart`, `UploadBatch`. The app rename from `uploads` to `portal` already signals the expanded scope from "file uploads" to "OSS ingest portal."
- **Alternatives rejected**:
  - **Mixed naming (IngestFile + Upload*)**: Semantically defensible (ingest = outcome, upload = process) but creates cognitive overhead for developers navigating the portal app. Inconsistent prefixes within the same domain.
  - **Rename all to Ingest***: `IngestSession` and `IngestPart` are less intuitive than `UploadSession` and `UploadPart` — these models specifically track the chunked transfer process.
- **Rationale**: Consistent naming within the domain wins over semantic nuance. The `portal` app name provides the "ingest portal" context; the model names describe what they are (upload artifacts). No model-rename migration needed, reducing migration complexity.
- **Impact on plan**: Step 2 simplified to status changes only (no RenameModel). Steps 3, 5, 8, 9 simplified (no IngestFile references). No related_name changes needed since existing names (`"upload_files"`, `"upload_batches"`) already match model names.
- **Impact on summary**: All IngestFile references become UploadFile. Model described as "simplified" rather than "new."
- **Impact on research**: Historical analysis preserved as-is; the IngestFile references in research.md document the evolution of thinking.

### Decision: Rename existing tables to portal_ prefix
- **Date**: 2026-02-28
- **Context**: After renaming the `uploads` app to `portal`, the existing `db_table` values (`upload_batch`, `upload_file`, `upload_session`, `upload_part`) become inconsistent with the new `portal_event_outbox` table. Three options were considered: keep existing `upload_*` names, rename to `portal_upload_*`, or use short `portal_*` names.
- **Decision**: Rename existing tables to follow Django's `{app}_{model}` convention: `portal_upload_batch`, `portal_upload_file`, `portal_upload_session`, `portal_upload_part`.
- **Alternatives rejected**:
  - **Keep existing `upload_*` table names**: Simplest migration but creates naming inconsistency within the portal app — new tables use `portal_*` prefix while legacy tables keep `upload_*`.
  - **Short `portal_*` names (`portal_batch`, `portal_file`, etc.)**: Loses the `upload` context from the model names, making table names ambiguous.
- **Rationale**: Consistency across all tables in the portal app. The `portal_upload_*` pattern follows Django's `{app}_{model}` convention, makes it clear these tables belong to the portal app, and aligns with the new `portal_event_outbox` table.
- **Impact on plan**: Step 1's rename migration includes `ALTER TABLE upload_* RENAME TO portal_upload_*` for all four existing tables. All `db_table` values in `portal/models.py` are updated accordingly.

## Open Threads

### Thread: What happens to the existing `uploads` app?
- **Raised**: 2026-02-27
- **Resolved**: 2026-02-27
- **Resolution**: Evolve (Option 3). See Design Decision "Evolve uploads app into portal" above.
- **Context**: The codebase already has a fully implemented `uploads` app with `UploadBatch`, `UploadFile`, `UploadSession`, and `UploadPart` models that are structurally very similar to the proposed portal models.
- **Status**: Resolved — the `uploads` app will be renamed/refactored into `portal`, evolving existing models incrementally rather than creating parallel models or doing a clean replacement.

### Thread: Should PortalEventOutbox have a FK to IngestFile, or use aggregate_type/aggregate_id like OutboxEvent?
- **Raised**: 2026-02-27
- **Resolved**: 2026-02-27
- **Resolution**: Generic aggregate_type/aggregate_id pattern (Option 2). See Design Decision "PortalEventOutbox uses generic aggregate_type/aggregate_id pattern" above.
- **Context**: The plan's Step 6 specifies "FK to IngestFile" on `PortalEventOutbox`. The existing `common.OutboxEvent` uses `aggregate_type` (CharField) + `aggregate_id` (CharField) without a FK, allowing it to reference any model. The summary's model relationships diagram shows `IngestFile → PortalEventOutbox (1:N)`. However, if portal events could also relate to batches, sessions, or other portal entities, a FK to IngestFile alone is too narrow.
- **Status**: Resolved — using generic aggregate_type/aggregate_id pattern for flexibility with future event schemas.

### Thread: Is the "STORED implies outbox-only" invariant too restrictive?
- **Raised**: 2026-02-27
- **Resolved**: 2026-02-27
- **Resolution**: Keep the invariant (Option 1). See Design Decision "STORED-only outbox invariant is kept" above.
- **Context**: The acceptance criterion states "PortalEventOutbox entries cannot be created unless the associated file is STORED." This means no events can be emitted for `file.uploading`, `file.failed`, `batch.created`, or other non-STORED lifecycle events. The out-of-scope section defers event schema to PEP 0016, but PEP 0008's model invariant already constrains which events are possible.
- **Status**: Resolved — STORED-only invariant kept; non-STORED lifecycle events can use `common.OutboxEvent` if needed.

### Thread: UploadBatch counter fields — stored at model or computed?
- **Raised**: 2026-02-27
- **Resolved**: 2026-02-27
- **Resolution**: Computed via annotation (Option 2). See Design Decision "UploadBatch counters computed via annotation" above.
- **Context**: The plan's Step 5 mentions `total_files`, `stored_count`, `failed_count` as fields on `UploadBatch`. The existing `uploads.UploadBatch` has no counter fields — counts are presumably computed via queryset aggregation. Denormalized counters are faster to read but require careful maintenance (increment on file status change, handle race conditions with F-expressions or select_for_update).
- **Status**: Resolved — batch counters will be computed via queryset annotation, no denormalized fields added.

### Thread: Should PEP 0008 remove FileField immediately or keep it alongside new storage fields?
- **Raised**: 2026-02-27 (via research.md findings)
- **Status**: Open
- **Context**: The plan's Step 2 says to "replace Django FileField with explicit storage fields: `storage_backend`, `storage_bucket`, `storage_key`." However, removing `FileField` before PEP 0009 (Storage Backend Abstraction) is implemented creates a gap where the existing upload functionality is broken. Five code paths depend on `FileField`: `create_upload_file()` (saves file via `file=file`), `mark_file_deleted()` (calls `upload_file.file.delete()`), `cleanup_expired_upload_files_task()` (calls `upload.file.delete()`), `notify_expiring_files()` (uses `upload.file.url`), and `create_upload_file()` event payload (uses `upload.file.url`).
- **Options**:
  - **Option 1: Remove FileField immediately (as planned)** — Add storage fields, remove FileField, update all services to work without FileField. Services that reference `file.url` or `file.delete()` would need stub implementations or be temporarily broken until PEP 0009.
  - **Option 2: Keep FileField alongside new storage fields** — Add `storage_backend`, `storage_bucket`, `storage_key` as new blank=True fields. Keep the existing `FileField`. All existing code continues to work. PEP 0009 migrates to the new fields and then removes `FileField`.
  - **Option 3: Defer storage field addition to PEP 0009 entirely** — PEP 0008 only does the app rename, model rename (UploadFile→IngestFile), status simplification, and PortalEventOutbox. Storage fields are added in PEP 0009.
- **Recommendation (from research)**: Option 2 or Option 3. Both avoid breaking existing upload functionality. Option 2 is forward-looking (storage fields exist early), Option 3 is simpler (fewer changes in PEP 0008).

### Thread: Should PortalEventOutbox use `attempts` or `attempt_count` for the retry counter field?
- **Raised**: 2026-02-27 (via research.md findings)
- **Resolved**: 2026-02-27
- **Resolution**: Use `attempts` (Option 1). See Resolved Question below.
- **Context**: The plan's Step 6 specifies `attempt_count` (PositiveIntegerField, default=0) for the retry counter on `PortalEventOutbox`. The existing `common.OutboxEvent` uses `attempts` (PositiveIntegerField, default=0) for the same purpose. Using different names for equivalent fields creates cognitive overhead and potential bugs when developers switch between the two outbox models.
- **Options**:
  - **Option 1: Use `attempts`** — Match `common.OutboxEvent` naming for consistency.
  - **Option 2: Use `attempt_count`** — More descriptive name, signals it's a counter not a list.
- **Recommendation (from research)**: Option 1 (`attempts`) for consistency with the established pattern in `common.OutboxEvent`.
- **Status**: Resolved — use `attempts` to match `common.OutboxEvent`.

### Thread: Should PEP 0008 remove FileField immediately or keep it alongside new storage fields?
- **Raised**: 2026-02-27 (via research.md findings)
- **Resolved**: 2026-02-27
- **Resolution**: Defer storage fields entirely to PEP 0009 (Option 3). See Resolved Question below.
- **Status**: Resolved — PEP 0008 keeps FileField; storage fields are PEP 0009's scope.

### Thread: PortalEventOutbox status choices include SENDING but OutboxEvent does not
- **Raised**: 2026-02-27 (via discuss pass)
- **Resolved**: 2026-02-27
- **Resolution**: Remove SENDING; match OutboxEvent's (PENDING, DELIVERED, FAILED). See Resolved Question below.
- **Context**: Plan Step 6 lists PortalEventOutbox status choices as (PENDING, SENDING, DELIVERED, FAILED). But `common.OutboxEvent` (`common/models.py:27-30`) only has (PENDING, DELIVERED, FAILED) — there is no SENDING status. The plan introduces an extra status not present in the template model.
- **Status**: Resolved — match OutboxEvent exactly.

### Thread: `finalize_batch()` depends on PROCESSED status being removed
- **Raised**: 2026-02-27 (via discuss pass)
- **Resolved**: 2026-02-27
- **Resolution**: Update `finalize_batch()` to use only STORED as the success status. See Resolved Question below.
- **Context**: `uploads/services/uploads.py:258` uses `success_statuses = {UploadFile.Status.STORED, UploadFile.Status.PROCESSED}`. When PROCESSED is removed from IngestFile's status choices, `finalize_batch()` will raise an AttributeError. The plan's Step 2 mentions simplifying statuses but doesn't address the dependent service functions.
- **Status**: Resolved — plan must include service function updates.

### Thread: Service layer out-of-scope contradiction with acceptance criteria
- **Raised**: 2026-02-27 (via discuss pass)
- **Resolved**: 2026-02-28
- **Resolution**: Option 1 — include minimal service enforcement in PEP 0008. See Design Decision "Include minimal service enforcement in PEP 0008" below.
- **Context**: The summary's "Out of Scope" section says "Service layer implementation beyond model-level validation" is out of scope. However, acceptance criteria #2 ("File cannot be marked STORED without required metadata — enforced in service layer") and #3 ("PortalEventOutbox entries cannot be created unless the file is STORED — enforced in service layer") explicitly require service layer enforcement. This is a contradiction — the acceptance criteria demand service layer code that the out-of-scope section excludes.
- **Status**: Resolved — out-of-scope section clarified; existing service function maintenance and basic model-lifecycle validations are in scope.

### Thread: Naming inconsistency — IngestFile with UploadSession/UploadPart/UploadBatch
- **Raised**: 2026-02-27 (via discuss pass)
- **Resolved**: 2026-02-28
- **Resolution**: Option 3 — keep all models as Upload*. See Design Decision "Keep all models as Upload* (no UploadFile→IngestFile rename)" below.
- **Context**: The file model was proposed to be renamed from `UploadFile` to `IngestFile`, but the other three models keep their `Upload*` prefix: `UploadSession`, `UploadPart`, `UploadBatch`. This creates a mixed-prefix naming scheme within the same domain.
- **Status**: Resolved — all models retain their Upload* prefix for consistency. The app rename (`uploads` → `portal`) already signals the expanded scope.

### Thread: `related_name` updates for Upload model FKs
- **Raised**: 2026-02-27 (via discuss pass)
- **Resolved**: 2026-02-28
- **Resolution**: Option 1 — update to match model name. With the naming decision to keep all Upload* models, the existing related_names already match: `"upload_files"` matches `UploadFile`, `"upload_batches"` matches `UploadBatch`. No related_name changes are needed.
- **Context**: The plan's Step 5 originally proposed updating `UploadBatch.created_by` related_name from `"upload_batches"` to `"portal_batches"`, and Step 2 proposed changing `UploadFile.uploaded_by` related_name from `"upload_files"` to `"ingest_files"`.
- **Status**: Resolved — no related_name changes needed since models keep Upload* names and related_names already match.

### Thread: Stale aggregate_type resolved question — superseded by naming decision
- **Raised**: 2026-02-28 (via discuss pass)
- **Resolved**: 2026-02-28
- **Resolution**: The resolved Q "What `aggregate_type` should be used after the UploadFile→IngestFile rename?" (2026-02-27) is superseded by the 2026-02-28 naming decision to keep all models as Upload*. The `aggregate_type` remains `"UploadFile"` — no change needed.
- **Context**: The original Q answered "change to IngestFile" but a later design decision eliminated the model rename entirely. The plan was correctly amended (`<!-- Amendment 2026-02-28: No model rename — UploadFile kept; removed aggregate_type change -->`), but the resolved Q in this file was not annotated as superseded.
- **Status**: Resolved — aggregate_type stays `"UploadFile"`. The earlier resolved Q is superseded.

### Thread: PortalEventOutbox index and constraint naming
- **Raised**: 2026-02-28 (via discuss pass)
- **Resolved**: 2026-02-28
- **Resolution**: Use `idx_portal_outbox_pending_next` for the partial index and `unique_portal_event_type_idempotency_key` for the unique constraint. See Resolved Question below.
- **Context**: Plan Step 6 specifies the partial index on `next_attempt_at WHERE status="pending"` and the unique constraint on `(event_type, idempotency_key)` but does not specify their names. Database constraint and index names must be unique across the database. `common.OutboxEvent` uses `idx_outbox_pending_next` and `unique_event_type_idempotency_key` — the portal equivalents need distinct names.
- **Status**: Resolved — names prefixed with `portal_` to avoid collisions with common outbox.

### Thread: Existing tests must be updated for status simplification
- **Raised**: 2026-02-28 (via discuss pass)
- **Resolved**: 2026-02-28
- **Resolution**: See Resolved Question below.
- **Context**: The plan's testing section lists new tests to write but does not account for existing tests that will break after the status simplification (removing PROCESSED and DELETED) and service function removal. Specifically:
  - `uploads/tests/test_models.py:219-225` — `test_status_choices` asserts `UploadFile.Status.values` includes `"processed"` and `"deleted"` — these must be updated to the new 3-status set
  - `uploads/tests/test_services.py:129-152` — `TestMarkFileProcessed` class tests `mark_file_processed()` which is being removed — entire class must be removed
  - `uploads/tests/test_services.py:170-183` — `TestMarkFileDeleted` class tests `mark_file_deleted()` which is being removed — entire class must be removed
  - `uploads/tests/test_services.py:14-24` — imports `mark_file_deleted`, `mark_file_processed` — must be removed from import list
  - `uploads/tests/test_services.py:322-327` — `test_skips_non_stored_files` sets `upload.status = UploadFile.Status.PROCESSED` — must use `UploadFile.Status.FAILED` instead (or remove the test if FAILED is already covered)
  - `uploads/tests/test_tasks.py:86` — `from uploads import tasks` — module path changes to `from portal import tasks`
  - All test files (`test_models.py`, `test_services.py`, `test_tasks.py`, `test_sessions.py`) import from `uploads.*` — all must be updated to `portal.*`
  - `frontend/tests/test_views_upload.py:6` — imports from `uploads.models` — must update to `portal.models`
- **Status**: Resolved — plan should include a step for updating existing tests (not just writing new ones).

### Thread: Migration file handling during app rename
- **Raised**: 2026-02-28 (via discuss pass)
- **Resolved**: 2026-02-28
- **Resolution**: See Resolved Question below.
- **Context**: Plan Step 1 says to "Create a migration to rename the `db_table` entries" but does not specify the physical file handling. After renaming the `uploads/` directory to `portal/`, the existing `uploads/migrations/0001_initial.py` must be moved to `portal/migrations/0001_initial.py`. The rename migration should then be `portal/migrations/0002_rename_app.py`. If the migrations directory is not moved, Django will see `portal` as a brand new app with no migration history and attempt to create all tables from scratch.
- **Ordering**:
  1. Physically rename `uploads/` → `portal/` (including `uploads/migrations/` → `portal/migrations/`)
  2. Update `portal/apps.py` — `name="portal"`, class name to `PortalConfig`
  3. Update `INSTALLED_APPS` from `"uploads"` to `"portal"`
  4. Create `portal/migrations/0002_rename_app.py` — a manual migration (not auto-generated) that uses `RunSQL` / `RunPython` to:
     - Update `django_content_type` rows: `UPDATE django_content_type SET app_label='portal' WHERE app_label='uploads'`
     - Update `django_migrations` rows: `UPDATE django_migrations SET app='portal' WHERE app='uploads'`
     - Optionally rename tables from `upload_*` to `portal_*` (depends on db_table naming decision)
  5. The migration's `dependencies` should be `[("portal", "0001_initial")]` (referencing the moved initial migration)
- **Status**: Resolved — the plan should spell out the physical file move and manual migration creation.

### Thread: `db_table` naming for existing models after app rename
- **Raised**: 2026-02-28 (via discuss pass)
- **Context**: Current `db_table` values are `upload_batch`, `upload_file`, `upload_session`, `upload_part`. The app is being renamed from `uploads` to `portal`. The resolved Q about PortalEventOutbox's `db_table` uses `portal_event_outbox` (following `portal_` prefix). But the existing models' `db_table` values are not addressed.
- **Options**:
  - **Option 1: Keep existing table names (`upload_*`)** — Simplest migration (only `django_content_type` and `django_migrations` need updating, no `ALTER TABLE RENAME`). Downside: a `portal` app has `upload_*` tables, which is inconsistent with the new `portal_event_outbox` table.
  - **Option 2: Rename to `portal_*` prefix** — `portal_upload_batch`, `portal_upload_file`, `portal_upload_session`, `portal_upload_part`. Follows Django's `{app}_{model}` convention. Consistent with `portal_event_outbox`. Requires `ALTER TABLE ... RENAME TO ...` in the migration, plus updating all explicit `db_table` values in `portal/models.py`.
  - **Option 3: Rename to short `portal_*` names** — `portal_batch`, `portal_file`, `portal_session`, `portal_part`. Shorter but loses the `upload` context from model names.
- **Recommendation**: Option 1 (keep `upload_*`) is simplest and avoids table rename risk. The existing names are explicit and won't confuse Django. The inconsistency with `portal_event_outbox` is minor — new models get `portal_*` tables, legacy models keep their names. PEP 0009+ can rename tables if desired.
- **Resolved**: 2026-02-28
- **Resolution**: Option 2 — rename to `portal_upload_*` prefix. See Design Decision "Rename existing tables to portal_ prefix" below.
- **Status**: Resolved — existing tables renamed to follow `{app}_{model}` convention.

### Thread: `upload_to` path on FileField after app rename
- **Raised**: 2026-02-28 (via discuss pass)
- **Resolved**: 2026-02-28
- **Resolution**: Keep the existing `upload_to="uploads/%Y/%m/"` path unchanged. See Resolved Question below.
- **Context**: `UploadFile.file = models.FileField(upload_to="uploads/%Y/%m/")` references the old app name "uploads" in the upload path. After renaming the app to `portal`, new files would still be stored under `uploads/2026/02/...` (Dev: in `MEDIA_ROOT/uploads/`, Production: S3 key prefix `uploads/`). Changing this path would mean new files go to a different directory/prefix than old files, creating a split.
- **Status**: Resolved — keep existing path. It's a storage path convention, not a code reference. Changing it splits the file namespace. PEP 0009 will redesign storage paths when it implements the storage abstraction.