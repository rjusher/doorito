# PEP 0002: Rename FileUpload to IngestFile — Discussions

| Field | Value |
|-------|-------|
| **PEP** | 0002 |
| **Summary** | [summary.md](summary.md) |

---

## Resolved Questions

### Q: How many files and references are actually affected?
- **Resolved**: 2026-02-25
- **Answer**: 13 code files need modification with ~91 total occurrences (not ~50 as stated in summary.md).
- **Rationale**: A codebase-wide grep for `FileUpload|file_upload|create_upload|consume_upload|cleanup_expired_uploads` found 128 occurrences across 18 files. Excluding PEP directory files (5 files), the code/doc files requiring changes are:
  - `uploads/models.py` (3 occurrences)
  - `uploads/services/uploads.py` (19 occurrences)
  - `uploads/admin.py` (3 occurrences)
  - `uploads/tasks.py` (5 occurrences)
  - `uploads/tests/test_services.py` (22 occurrences)
  - `uploads/tests/test_tasks.py` (16 occurrences)
  - `aikb/models.md` (5), `aikb/services.md` (4), `aikb/tasks.md` (2), `aikb/admin.md` (2), `aikb/architecture.md` (5)
  - `CLAUDE.md` (1)
  - `uploads/migrations/0001_initial.py` — **not modified** (existing migrations are never edited)
  The ~13 file count in the summary is accurate; the ~50 reference count should be corrected to ~91.

### Q: What migration strategy should be used?
- **Resolved**: 2026-02-25
- **Answer**: Use Django's `migrations.RenameModel(old_name="FileUpload", new_name="IngestFile")` as the primary operation, plus separate `AlterModelOptions` and `RenameIndex` operations.
- **Rationale**: `RenameModel` is Django's built-in operation for this exact scenario. It:
  1. Renames the database table (`file_upload` → `ingest_file`, respecting `db_table`)
  2. Updates Django's internal state tracking (content types, migration history)
  3. Is fully reversible via `migrate <app> <previous_migration>`

  However, `RenameModel` alone does **not** rename indexes. The existing auto-generated indexes (`file_upload_user_id_c50e60_idx`, `file_upload_status_20c17f_idx`) contain the old table name prefix. The migration should include `RenameIndex` operations to rename them with the new `ingest_file_*` prefix, and `AlterModelOptions` to update `verbose_name`/`verbose_name_plural`. Running `makemigrations` after the model rename should auto-detect most of this, but the index renames may need manual verification.

### Q: Does the Celery task `name` string need explicit updating?
- **Resolved**: 2026-02-25
- **Answer**: Yes. The `@shared_task` decorator in `uploads/tasks.py` has an explicit `name="uploads.tasks.cleanup_expired_uploads_task"` parameter that must be changed to `name="uploads.tasks.cleanup_expired_ingest_files_task"`.
- **Rationale**: This is easy to miss because it's a string literal rather than a Python identifier. Since there's no production deployment and Celery runs eagerly in dev, there's no backward-compatibility concern — just a correctness issue. The plan should call this out explicitly.

### Q: What values should `verbose_name` and `verbose_name_plural` take?
- **Resolved**: 2026-02-25
- **Answer**: `verbose_name = "ingest file"`, `verbose_name_plural = "ingest files"`.
- **Rationale**: Follows Django's convention of lowercase verbose names. These appear in the admin interface and error messages. The current values `"file upload"` / `"file uploads"` must be updated.

### Q: Does the `__str__` method need changes?
- **Resolved**: 2026-02-25
- **Answer**: No. The current implementation `f"{self.original_filename} ({self.get_status_display()})"` doesn't reference the model name, so it remains correct after the rename.

### Q: Are there `__init__.py` exports or conftest fixtures that reference FileUpload?
- **Resolved**: 2026-02-25
- **Answer**: No. `uploads/__init__.py` and `uploads/services/__init__.py` are both empty. The root `conftest.py` only defines a `user` fixture with no FileUpload references. No changes needed in these files.

### Q: Is the plan.md populated with implementation steps?
- **Resolved**: 2026-02-25
- **Answer**: No — plan.md is still the template with placeholder content. It has no context files, no implementation steps, no testing section, no rollback plan, and no aikb impact map filled in.
- **Rationale**: The plan needs to be fully populated before the PEP can move to Accepted. This should be done via `make claude-pep-plan PEP=0002` or manually. The resolved questions in this discussions file provide the technical grounding for the plan.

## Design Decisions

### 2026-02-25: Proposed IngestFile Model Enhancements — Deferred

**Context:** A review note on `summary.md` proposed adopting a significantly enhanced model definition during the rename, including:

- UUID primary key (`UUIDField`) instead of auto-incrementing integer
- `uploaded_by` with `SET_NULL` instead of `user` with `CASCADE`
- New status choices: `UPLOADING`, `STORED`, `FAILED`, `DELETED` (replacing `PENDING`, `READY`, `CONSUMED`, `FAILED`)
- `sha256` hash field (content integrity / deduplication)
- Abstract storage pointer fields: `storage_backend`, `storage_bucket`, `storage_key` (instead of Django `FileField`)
- `metadata` JSONField for flexible non-sensitive metadata
- `last_error` field (renamed from `error_message`)
- `content_type` (renamed from `mime_type`)
- `size_bytes` as `BigIntegerField` (replacing `file_size` as `PositiveBigIntegerField`)
- New indexes on `uploaded_at`, `(status, uploaded_at)`, `content_type`
- No `TimeStampedModel` inheritance — standalone `models.Model` with explicit `uploaded_at`

**Decision:** Defer model enhancements. Keep PEP 0002 as a pure rename/refactor.

**Rationale:**
1. PEP 0002 is explicitly scoped as "pure rename/refactor" with "no functional changes" (see Out of Scope). Folding in a model redesign would fundamentally change the PEP's risk profile and scope.
2. Several of the proposed changes are individually significant design decisions (UUID PKs, dropping `FileField` for abstract storage pointers, changing the status lifecycle) that deserve their own analysis and acceptance criteria.
3. A clean rename first (PEP 0002) followed by model enhancements (new PEP) gives a clearer git history and easier rollback boundaries.
4. The proposed model is a strong direction for IngestFile's evolution. It should be captured as a new PEP (e.g., PEP 0004: "Enhance IngestFile Model") or folded into PEP 0003's scope if the data model extension effort is broadened beyond just the `workflows` app.

**Follow-up:** Create a PEP for IngestFile model enhancements covering the proposed fields. The full proposed model definition is preserved in git history (this file, and the original review note in `summary.md` prior to this commit).

### Proposed Model (reference)

```python
class IngestFile(models.Model):
    """
    Canonical file record. This is the source of truth once STORED.
    """
    class Status(models.TextChoices):
        UPLOADING = "uploading"
        STORED = "stored"
        FAILED = "failed"
        DELETED = "deleted"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    uploaded_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    original_filename = models.CharField(max_length=512)
    content_type = models.CharField(max_length=255, blank=True)
    size_bytes = models.BigIntegerField(default=0)

    sha256 = models.CharField(max_length=64, blank=True, db_index=True)

    # Storage pointer (abstract; supports local FS or S3-like)
    storage_backend = models.CharField(max_length=64, default="local")  # "local", "s3"
    storage_bucket = models.CharField(max_length=255, blank=True)
    storage_key = models.CharField(max_length=1024, blank=True)

    # Flexible non-sensitive metadata (e.g., xml_root, sniffed_type, etc.)
    metadata = models.JSONField(default=dict, blank=True)

    status = models.CharField(max_length=32, choices=Status.choices, default=Status.UPLOADING)
    last_error = models.TextField(blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["uploaded_at"]),
            models.Index(fields=["status", "uploaded_at"]),
            models.Index(fields=["content_type"]),
        ]
```

Note: The original review note had a typo (`ditable=False` instead of `editable=False`), corrected above.

### 2026-02-25: Update log messages and docstrings during rename

**Context:** The service functions in `uploads/services/uploads.py` contain log messages referencing "Upload" (e.g., `"Upload created: pk=%s"`, `"Upload consumed: pk=%s"`, `"Upload failed validation"`) and docstrings that use "upload" terminology (e.g., "Validate and store a file upload", "Mark an upload as consumed"). Similarly, test class names (`TestCreateUpload`, `TestConsumeUpload`) and test docstrings reference "upload" and "FileUpload". The question is whether these should be updated as part of the rename.

**Decision:** Update all log messages, docstrings, test class names, and test docstrings to use the new naming consistently.

**Alternatives rejected:**
- *Leave log/docstring language as-is:* This would create a confusing split where the code uses `IngestFile` / `create_ingest_file` but logs say "Upload created" and docstrings reference "uploads". Since this is a pure rename PEP with no functional changes, updating the surrounding prose is low-risk and prevents naming inconsistency from day one.

### 2026-02-25: Module docstrings update

**Context:** `uploads/services/uploads.py` has module docstring `"Upload handling services for file validation, creation, and consumption."` and `uploads/tasks.py` has `"Celery tasks for the uploads app."` The question is whether these module-level docstrings should be updated.

**Decision:** Update to reference "ingest file" where the docstring describes the domain concept (e.g., `uploads/services/uploads.py` → `"Ingest file services for file validation, creation, and consumption."`). Leave module docstrings that reference the app name unchanged (e.g., `"Celery tasks for the uploads app."` stays as-is since the app is still called `uploads`).

**Alternatives rejected:**
- *Update all docstrings including app-level ones:* The app is still named `uploads/`, so saying "Celery tasks for the uploads app" is still accurate. Changing it to "ingest files app" would be misleading.

## Open Threads

### Thread: Should `related_name="uploads"` on the User FK be renamed?
- **Raised**: 2026-02-25
- **Context**: The `FileUpload.user` ForeignKey has `related_name="uploads"`, which means the reverse accessor from User is `user.uploads.all()`. After the model rename to `IngestFile`, the accessor `user.uploads.all()` would still work but would be semantically misaligned — the User doesn't have "uploads", they have "ingest files". However, renaming the `related_name` to `ingest_files` would:
  1. Require a migration (Django tracks `related_name` changes)
  2. Break any code using `user.uploads.all()` (currently none exist outside the model definition and migration)
  3. Change the documented API surface in `aikb/models.md`
- **Options**:
  1. **Rename to `ingest_files`** — Full naming consistency. Since there are currently zero consumers of `user.uploads`, the cost is minimal. The migration is trivial (just a field alteration). Recommended while the blast radius is still zero.
  2. **Keep as `uploads`** — The `related_name` describes how files got there (via upload), which is still accurate. The `uploads` app name isn't changing either, so `user.uploads` is consistent with the app namespace. Less churn.
  3. **Rename to `uploaded_files`** — A middle ground: avoids the `uploads` ambiguity but doesn't fully align with `IngestFile`.
- **Status**: Awaiting input — this is a naming/API question that affects downstream code patterns. Recommend option 1 (rename to `ingest_files`) given zero current consumers.
