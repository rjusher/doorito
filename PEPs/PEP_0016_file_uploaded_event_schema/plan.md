# PEP 0016: Canonical file.uploaded Event Schema — Implementation Plan

| Field | Value |
|-------|-------|
| **PEP** | 0016 |
| **Summary** | [summary.md](summary.md) |
| **Estimated Effort** | S |

---

## Context Files

- `aikb/models.md` — PortalEventOutbox, IngestFile (from PEP 0008)
- `aikb/services.md` — Service conventions, outbox patterns
- Portal app `services/finalize.py` — Where the event is created (from PEP 0014)
- `common/services/outbox.py` — Existing outbox emit_event pattern

## Prerequisites

- PEP 0008 (Canonical Domain Model) implemented
- PEP 0014 (Finalize Upload) implemented

## Implementation Steps

- [ ] **Step 1**: Define event payload builder
  - Files: Portal app `services/events.py`
  - Details: `build_file_uploaded_payload(ingest_file)` function that constructs the canonical payload dict
  - Verify: Unit tests pass

- [ ] **Step 2**: Define JSON schema for validation
  - Files: Portal app `schemas/file_uploaded.json` or inline in tests
  - Details: JSON Schema document matching the canonical payload structure
  - Verify: `jsonschema` validation test passes

- [ ] **Step 3**: Integrate payload builder into finalization service
  - Files: Portal app `services/finalize.py`
  - Details: Use `build_file_uploaded_payload()` when creating PortalEventOutbox entry
  - Verify: Integration test verifying outbox payload matches schema

- [ ] **Step 4**: Document schema
  - Files: Portal app documentation or `aikb/` files
  - Details: Document the event schema, rules, and evolution policy
  - Verify: Documentation review

## Testing

- [ ] Unit tests for payload builder (all fields populated correctly)
- [ ] Unit test for null-safe actor handling
- [ ] Schema validation test (payload validates against JSON schema)

## Rollback Plan

- Revert payload builder integration in finalization service
- Remove schema files

## aikb Impact Map

- [ ] `aikb/models.md` — N/A
- [ ] `aikb/services.md` — Add event payload builder documentation
- [ ] `aikb/tasks.md` — N/A
- [ ] `aikb/signals.md` — N/A
- [ ] `aikb/admin.md` — N/A
- [ ] `aikb/cli.md` — N/A
- [ ] `aikb/architecture.md` — Document event schema contract
- [ ] `aikb/conventions.md` — Add event schema evolution rules
- [ ] `aikb/dependencies.md` — Add jsonschema if used for validation
- [ ] `aikb/specs-roadmap.md` — Update
- [ ] `CLAUDE.md` — N/A

## Final Verification

### Acceptance Criteria

- [ ] **Schema validation**: Generated payload passes JSON schema validation
  - Verify: Unit test with jsonschema
- [ ] **Deduplication**: event_id is unique per event
  - Verify: Unit test creating multiple events
- [ ] **No secrets**: Payload inspection test
  - Verify: Unit test asserting no sensitive fields

### Regression Checks

- [ ] `python manage.py check` passes
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check`
- [ ] `ruff check .` passes
  - Verify: `ruff check .`

## Completion

- [ ] **Update `PEPs/IMPLEMENTED/LATEST.md`**
- [ ] **Update `PEPs/INDEX.md`** — Remove the PEP row
- [ ] **Remove PEP directory** — Delete `PEPs/PEP_0016_file_uploaded_event_schema/`
