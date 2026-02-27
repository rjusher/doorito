# PEP 0018: Minimal OSS User Interface

| Field | Value |
|-------|-------|
| **PEP** | 0018 |
| **Title** | Minimal OSS User Interface |
| **Author** | Doorito Team |
| **Status** | Proposed |
| **Risk** | Medium |
| **Created** | 2026-02-27 |
| **Updated** | 2026-02-27 |
| **Depends On** | PEP 0008, PEP 0010, PEP 0014, PEP 0015, PEP 0017 |

---

## Problem Statement

Users need a minimal web interface to upload files, monitor ingest progress, and view event delivery status. Without a UI, all operations require API calls or direct database access, which limits accessibility for non-technical users and makes debugging delivery issues difficult.

## Proposed Solution

Provide a minimal web UI for uploading files and monitoring the ingest pipeline, integrated into the existing `frontend` app's dashboard.

### Pages

1. **Upload page** — Single file and batch upload with progress indicator
2. **File list** — Filterable list of ingested files with status, filename, size, upload date
3. **File detail** — File metadata (filename, content type, size, sha256, storage pointer) and associated outbox event status (PENDING, SENDING, DELIVERED, FAILED)
4. **Batch detail** — Batch metadata with file list and progress counters
5. **Retry outbox button** — Manual retry trigger for FAILED outbox events

### Technology

- Server-rendered Django views with HTMX for dynamic updates (consistent with existing frontend)
- Alpine.js for client-side upload progress and chunk management
- Tailwind CSS for styling (existing design tokens)

## Rationale

A minimal UI lowers the barrier to using the ingest portal. HTMX-driven server rendering keeps the architecture consistent with the existing frontend app. The retry button provides essential operational capability without requiring admin access or API tools.

## Alternatives Considered

### Alternative 1: Admin-only interface

- **Description**: Rely on Django admin for all monitoring and management.
- **Pros**: No custom UI development.
- **Cons**: Django admin is not suitable for file uploads with chunking. Poor UX for non-admin users. No upload progress.
- **Why rejected**: Admin works for data inspection but not for the upload workflow itself.

### Alternative 2: SPA frontend (React/Vue)

- **Description**: Build a standalone SPA for the ingest portal.
- **Pros**: Richer client-side interactions.
- **Cons**: Adds significant complexity (build tooling, API serialization, CORS). Inconsistent with the HTMX/Alpine.js approach used in the rest of the project.
- **Why rejected**: Over-engineered for a minimal UI. HTMX + Alpine.js provides sufficient interactivity.

## Impact Assessment

### Affected Components

- **Views**: New views in `frontend` app or dedicated portal views
- **Templates**: New page templates for upload, file list, file detail, batch detail
- **URLs**: New URL patterns under `/app/` namespace
- **Static**: Potential JS for chunk upload client logic

### Migration Impact

- **Database migrations required?** No
- **Data migration needed?** No
- **Backward compatibility**: Non-breaking (new pages)

### Performance Impact

- File list page should use pagination to handle large datasets
- HTMX polling for upload progress keeps server load minimal

## Out of Scope

- Admin bulk operations (mass retry, mass delete)
- Real-time WebSocket updates
- Mobile-optimized responsive layout (basic responsiveness only)
- File preview/thumbnail generation
- Download functionality

## Acceptance Criteria

- [ ] Upload a file → file visible in file list with correct metadata
- [ ] Event delivery status visible on file detail page (PENDING → DELIVERED)
- [ ] Manual retry button updates outbox event status and triggers re-delivery
- [ ] Batch detail shows correct file counts and progress
- [ ] Upload progress indicator shows chunk upload status
- [ ] All pages require authentication

## Status History

| Date | From | To | Notes |
|------|------|----|-------|
| 2026-02-27 | — | Proposed | Initial creation |
