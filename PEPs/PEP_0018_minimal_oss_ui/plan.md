# PEP 0018: Minimal OSS User Interface — Implementation Plan

| Field | Value |
|-------|-------|
| **PEP** | 0018 |
| **Summary** | [summary.md](summary.md) |
| **Estimated Effort** | L |

---

## Context Files

- `aikb/architecture.md` — Frontend app structure, template hierarchy, sidebar
- `frontend/templates/frontend/` — Existing template patterns (base, components, pages)
- `frontend/views.py` — Existing view patterns (dashboard, auth)
- `frontend/decorators.py` — `@frontend_login_required` decorator
- `static/css/input.css` — Tailwind design tokens
- `templates/base.html` — Base template with HTMX, Alpine.js, Tailwind CSS

## Prerequisites

- PEP 0008 (Canonical Domain Model) implemented
- PEP 0010 (Authentication) implemented
- PEP 0014 (Finalize Upload) implemented
- PEP 0015 (Batch Upload) implemented
- PEP 0017 (Outbox Dispatcher) implemented

## Implementation Steps

- [ ] **Step 1**: Create upload page template and view
  - Files: `frontend/templates/frontend/pages/upload.html`, `frontend/views.py`
  - Details: Upload form with Alpine.js for client-side chunking, HTMX for progress updates
  - Verify: Page renders at `/app/upload/`

- [ ] **Step 2**: Create file list page
  - Files: `frontend/templates/frontend/pages/files.html`, `frontend/views.py`
  - Details: Paginated file list with status filters, search by filename
  - Verify: Page renders at `/app/files/`

- [ ] **Step 3**: Create file detail page
  - Files: `frontend/templates/frontend/pages/file_detail.html`, `frontend/views.py`
  - Details: File metadata, associated outbox events with status
  - Verify: Page renders at `/app/files/<id>/`

- [ ] **Step 4**: Create batch detail page
  - Files: `frontend/templates/frontend/pages/batch_detail.html`, `frontend/views.py`
  - Details: Batch metadata, file list within batch, progress counters
  - Verify: Page renders at `/app/batches/<id>/`

- [ ] **Step 5**: Implement retry outbox button
  - Files: `frontend/views.py`, file detail template
  - Details: HTMX button that POSTs to retry endpoint, resets outbox event to PENDING
  - Verify: Click retry → event status changes to PENDING

- [ ] **Step 6**: Add navigation links to sidebar
  - Files: `frontend/templates/frontend/components/sidebar.html`
  - Details: Add Upload, Files links to sidebar navigation
  - Verify: Links visible and functional

- [ ] **Step 7**: Implement client-side chunk upload with Alpine.js
  - Files: JS in upload template or separate static file
  - Details: Split file into chunks, upload via PUT, show progress bar
  - Verify: Large file uploads successfully with visible progress

## Testing

- [ ] Manual testing of upload → file list → file detail flow
- [ ] Manual testing of batch upload → batch detail flow
- [ ] Manual testing of retry button
- [ ] Verify auth required on all pages

## Rollback Plan

- Remove new templates and view functions
- Revert sidebar changes
- Revert URL configuration

## aikb Impact Map

- [ ] `aikb/models.md` — N/A
- [ ] `aikb/services.md` — N/A
- [ ] `aikb/tasks.md` — N/A
- [ ] `aikb/signals.md` — N/A
- [ ] `aikb/admin.md` — N/A
- [ ] `aikb/cli.md` — N/A
- [ ] `aikb/architecture.md` — Add portal UI pages to frontend description
- [ ] `aikb/conventions.md` — N/A
- [ ] `aikb/dependencies.md` — N/A
- [ ] `aikb/specs-roadmap.md` — Update
- [ ] `CLAUDE.md` — Update URL structure with portal pages

## Final Verification

### Acceptance Criteria

- [ ] **Upload → visible**: Upload file, see it in file list
  - Verify: Manual browser test
- [ ] **Event status visible**: File detail shows outbox event status
  - Verify: Manual browser test
- [ ] **Retry works**: Click retry, event status resets to PENDING
  - Verify: Manual browser test

### Regression Checks

- [ ] `python manage.py check` passes
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check`
- [ ] `ruff check .` passes
  - Verify: `ruff check .`

## Completion

- [ ] **Update `PEPs/IMPLEMENTED/LATEST.md`**
- [ ] **Update `PEPs/INDEX.md`** — Remove the PEP row
- [ ] **Remove PEP directory** — Delete `PEPs/PEP_0018_minimal_oss_ui/`
