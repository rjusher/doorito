# PEP 0001: AI Upload Portal

| Field | Value |
|-------|-------|
| **PEP** | 0001 |
| **Title** | AI Upload Portal |
| **Author** | Doorito Team |
| **Status** | Proposed |
| **Risk** | Medium |
| **Created** | 2026-02-25 |
| **Updated** | 2026-02-25 |

---

## Problem Statement

Doorito currently has only a placeholder dashboard with no functional features. The project's purpose is to serve as an upload portal where users can submit files and trigger AI-powered workflows on them. There is no file upload infrastructure, no workflow management system, and no mechanism to connect uploaded files to background processing pipelines.

Users need the ability to:
- Upload files through a web interface
- Select an AI workflow to run on their uploaded files
- Monitor the progress of running workflows
- View and download results when workflows complete

Without this core feature, the application is an empty shell that provides no value to end users.

<!--
Review:
Don't need to monitor the progress of running workflows
The file uploads are just temporary, until a workflow retrieves it.
Use local storage to store files, should be deleted after a time.
-->

## Proposed Solution

Introduce a new `uploads` Django app that provides a complete file upload portal with AI workflow integration. The solution has four key components:

### 1. File Upload System
A `FileUpload` model stores uploaded file metadata (name, size, MIME type, status) with `FileField` storage. An upload form with drag-and-drop support (Alpine.js) allows users to submit files. Files are validated for size and allowed types before storage.

### 2. Workflow Definition Registry
A `Workflow` model defines available AI workflows with a name, description, accepted file types, and an active/inactive flag. Workflows are registered by administrators through Django admin. Each workflow has a `task_name` field that maps to the Celery task to execute.

### 3. Workflow Execution Engine
A `WorkflowRun` model tracks each execution of a workflow against an uploaded file, storing status (pending → running → completed → failed), progress percentage, started/completed timestamps, and result output. A Celery task dispatches the actual AI processing, updating the `WorkflowRun` record as it progresses.

### 4. Status & Results UI
HTMX-powered polling on the workflow run detail page shows real-time status updates without full page reloads. Users see a list of their uploads, can trigger workflows, and view results — all within the existing authenticated frontend shell.

## Rationale

**New app vs. extending frontend**: A dedicated `uploads` app keeps models, services, and tasks cleanly separated from the authentication-focused `frontend` app. The frontend app handles templates and views, while `uploads` owns the domain logic. This follows the existing architecture pattern where `accounts` owns users and `frontend` owns the UI.

**Workflow as a model vs. hardcoded pipelines**: Storing workflow definitions in the database allows administrators to add, modify, or disable workflows without code changes. The `task_name` field provides a clean mapping to Celery tasks, making the system extensible.

**HTMX polling vs. WebSockets**: HTMX polling is simpler, requires no additional infrastructure (no Daphne/channels), and works within the existing technology stack. For the initial implementation, polling every few seconds is sufficient for workflow status updates. WebSocket support can be added later if needed.

**Local file storage vs. S3**: The skeleton already has `MEDIA_ROOT`/`MEDIA_URL` configured for local filesystem storage. Starting with local storage keeps the implementation simple and avoids new dependencies. S3 support can be added in a future PEP.

## Alternatives Considered

### Alternative 1: API-first approach with a separate SPA frontend
- Description: Build a REST/GraphQL API for uploads and workflows, with a React or Vue.js frontend consuming it.
- Pros: Clean API separation, reusable endpoints, modern SPA experience.
- Cons: Massive scope increase, requires Node.js toolchain, breaks the HTMX/Alpine.js convention, adds API auth complexity (JWT/tokens).
- Why rejected: Contradicts the project's server-rendered architecture. The existing HTMX + Alpine.js stack is well-suited for this use case.

### Alternative 2: Extend the `frontend` app with upload models and logic
- Description: Add FileUpload and WorkflowRun models directly to the `frontend` app alongside auth views.
- Pros: Fewer files to create, simpler initial structure.
- Cons: Violates separation of concerns — `frontend` is a UI app with no models. Mixes domain logic with presentation. Makes future refactoring harder.
- Why rejected: The existing convention clearly separates apps by domain responsibility. An upload portal is a distinct domain that warrants its own app.

### Alternative 3: Use Django Channels for real-time workflow updates
- Description: Add WebSocket support via Django Channels for instant status streaming.
- Pros: Truly real-time updates, no polling overhead.
- Cons: Requires adding Daphne, channels, and channel layers (Redis or in-memory). Significant infrastructure change. The project explicitly has "No Daphne" as a design decision.
- Why rejected: Over-engineering for the initial implementation. HTMX polling provides an adequate user experience with zero new dependencies.

## Impact Assessment

### Affected Components
- Models: New `FileUpload`, `Workflow`, `WorkflowRun` models (in new `uploads` app)
- Services: New `uploads/services/` module for upload handling and workflow dispatch
- Admin: New `WorkflowAdmin`, `FileUploadAdmin`, `WorkflowRunAdmin`
- Tasks: New `uploads/tasks.py` with workflow execution task
- Views: New upload, workflow selection, and status views in `frontend`
- Templates: New templates for upload form, file list, workflow selection, run status

### Migration Impact
- Database migrations required: Yes — three new tables (`file_upload`, `workflow`, `workflow_run`)
- Data migration needed: No — new tables only, no existing data affected
- Backward compatibility: Non-breaking — purely additive

### Performance Impact
- Query performance: Minimal — new tables with proper indexing on user FK and status fields
- Cache implications: None initially
- Task queue implications: Workflow execution tasks will use the Celery queue. File processing tasks should route to the `default` queue. Long-running AI tasks may need their own time limits.

## Out of Scope

- **AI model integration**: This PEP creates the infrastructure for triggering workflows, but does not implement specific AI models or processing logic. Actual AI task implementations (OCR, classification, summarization, etc.) will be added in separate PEPs per workflow type.
- **S3 or cloud storage**: Files are stored locally via Django's `FileField`. Cloud storage migration is a separate PEP.
- **Batch uploads or folder uploads**: This PEP handles single-file uploads. Multi-file batch processing can be added later.
- **File sharing between users**: Uploaded files are private to the uploading user. Sharing/collaboration features are out of scope.
- **Workflow chaining**: Running multiple workflows sequentially on the same file. Each workflow run is independent.
- **API endpoints**: No REST API for programmatic uploads. API access is a separate PEP.
- **File preview/thumbnail generation**: Files are downloadable but not previewed inline.

## Acceptance Criteria

- [ ] Authenticated users can upload a file through a web form at `/app/uploads/new/`
- [ ] Uploaded files are stored on disk and recorded in the database with metadata (name, size, MIME type, uploader)
- [ ] File uploads are validated for maximum size (configurable, default 50MB) and allowed MIME types
- [ ] Users can view a list of their uploaded files at `/app/uploads/`
- [ ] Administrators can define AI workflows in Django admin with name, description, accepted file types, and task name
- [ ] Users can select and start an available workflow on an uploaded file
- [ ] A Celery task is dispatched when a workflow is started, creating a WorkflowRun record
- [ ] The workflow run status page at `/app/uploads/<id>/runs/<run_id>/` shows live progress via HTMX polling
- [ ] WorkflowRun records track status transitions: pending → running → completed/failed
- [ ] Users can view workflow results (output text) when a run completes
- [ ] The sidebar navigation includes an "Uploads" link
- [ ] All new models inherit from `TimeStampedModel`
- [ ] `python manage.py check` passes with no errors
- [ ] `ruff check .` passes with no errors

## Status History

| Date | From | To | Notes |
|------|------|----|-------|
| 2026-02-25 | — | Proposed | Initial creation |
