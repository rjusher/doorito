# PEP 0003: Extend Data Models — Discussions

| Field | Value |
|-------|-------|
| **PEP** | 0003 |
| **Summary** | [summary.md](summary.md) |
| **Research** | [research.md](research.md) |

---

## Open Questions

### Q1: Should new models inherit from TimeStampedModel or use explicit timestamp fields?

**Context**: The summary specifies `models.Model` with explicit timestamp fields as the base class, departing from the project convention in `aikb/models.md` ("All future models should inherit from TimeStampedModel"). The `TimeStampedModel` provides `created_at` (auto_now_add) and `updated_at` (auto_now).

**Arguments for TimeStampedModel**:
- Consistency with project convention and existing models
- Less boilerplate (2 fields inherited automatically)
- All 5 models need `created_at`/`updated_at` anyway
- Extra fields like `delivered_at` can be added alongside inherited ones

**Arguments for explicit fields**:
- Full control over field definitions (e.g., `null=True` on timestamps if needed)
- `auto_now_add=True` prevents explicit setting — makes test fixtures harder
- The summary explicitly specifies this approach

**Status**: Unresolved — needs author decision before planning.

---

### Q2: What happens to existing services, tasks, and tests?

**Context**: PEP 0003 is scoped to "models only" (services/endpoints are out of scope). However, the existing `uploads/services/uploads.py`, `uploads/tasks.py`, and `uploads/tests/` all depend on the current model shape (`FileField`, old status choices, old FK behavior). After the model rewrite, this code will have broken imports and incorrect logic.

**Options**:
1. **Delete** existing services, task, and tests. Add a note or follow-up PEP for rebuilding.
2. **Stub** services with `raise NotImplementedError` to preserve the module structure.
3. **Rewrite** minimal versions that work with the new model shape (scope creep risk).

**Recommendation from research**: Option 1 (delete) is cleanest. The existing services are tightly coupled to `FileField` semantics and cannot be adapted incrementally. A follow-up PEP should define the new service layer for the redesigned models.

**Status**: Unresolved — needs author decision before planning.

---

### Q3: Should PEP 0002 be completed first, or does PEP 0003 subsume the model changes?

**Context**: PEP 0002 (Rename FileUpload → IngestFile) is mid-implementation. The model class has been renamed, but admin, services, tasks, and tests still reference `FileUpload`. PEP 0003 drops and recreates the `ingest_file` table, making PEP 0002's rename migration moot.

**Options**:
1. **Complete PEP 0002 fully first** — clean separation, but some work gets immediately overwritten by PEP 0003.
2. **Subsume PEP 0002 into PEP 0003** — PEP 0003's plan includes the remaining code renames from PEP 0002 as a first step. PEP 0002 is marked as Implemented (or Withdrawn with note).
3. **Complete PEP 0002 code renames only** — skip the migration (it's moot), finish the code-level renames, mark PEP 0002 done, then proceed with PEP 0003.

**Recommendation from research**: Option 3 is pragmatic. The code renames are needed regardless (admin/service/task names should use `IngestFile` terminology). The database migration from PEP 0002 is wasted effort since PEP 0003 drops the table.

**Status**: Unresolved — needs author decision before planning.
