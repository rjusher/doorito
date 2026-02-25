# PEP 0001: AI Upload Portal — Implementation Plan

| Field | Value |
|-------|-------|
| **PEP** | 0001 |
| **Summary** | [summary.md](summary.md) |
| **Estimated Effort** | L |

---

## Context Files

- `aikb/architecture.md` §Django App Structure — understand the 3-app layout and where the new app fits
- `aikb/models.md` §TimeStampedModel — base model for all new models
- `aikb/services.md` §Convention — service layer pattern for business logic
- `aikb/tasks.md` §Task Conventions — Celery task patterns for workflow execution
- `aikb/conventions.md` §Model Patterns, §Frontend Patterns — coding and template conventions
- `aikb/dependencies.md` — current dependency list to check for conflicts
- `boot/settings.py` — INSTALLED_APPS, MEDIA settings, Celery configuration
- `boot/urls.py` — root URL routing to add uploads namespace
- `frontend/views/auth.py` — view pattern reference (function-based, decorator usage)
- `frontend/views/dashboard.py` — dashboard view pattern
- `frontend/forms/auth.py` — form pattern reference (INPUT_CLASS, widget styling)
- `frontend/urls.py` — URL pattern reference
- `frontend/decorators.py` — `@frontend_login_required` decorator
- `frontend/templates/frontend/base.html` — app shell template to extend
- `frontend/templates/frontend/components/sidebar.html` — sidebar navigation to update

## Prerequisites

- PostgreSQL database running and accessible (existing requirement)
- Virtual environment activated with current dependencies installed
- Tailwind CSS standalone CLI installed (`make tailwind-install`)

## Implementation Steps

- [ ] **Step 1**: Create the `uploads` Django app skeleton

  - Files:
    - `uploads/__init__.py` — empty init
    - `uploads/apps.py` — UploadsConfig with `default_auto_field` and `name`
    - `uploads/models.py` — will hold models (initially empty with docstring)
    - `uploads/admin.py` — will hold admin registrations (initially empty with docstring)
    - `uploads/services/__init__.py` — service package init
    - `uploads/tasks.py` — will hold Celery tasks (initially empty with docstring)

  - Details:
    Create the app directory manually (not `startapp`) to match project conventions. The `apps.py` should follow the same pattern as `accounts/apps.py` and `frontend/apps.py`. Set `default_auto_field = "django.db.models.BigAutoField"`.

  - Verify: `ls uploads/__init__.py uploads/apps.py uploads/models.py uploads/admin.py uploads/services/__init__.py uploads/tasks.py`

- [ ] **Step 2**: Register the `uploads` app in settings and configure media

  - Files:
    - `boot/settings.py` — add `"uploads"` to `INSTALLED_APPS`, verify `MEDIA_ROOT`/`MEDIA_URL` settings, add upload size limit setting

  - Details:
    Add `"uploads"` to `INSTALLED_APPS` in the `Base` class after `"frontend"`. Add a `FILE_UPLOAD_MAX_SIZE` setting (default `52428800` — 50MB). Verify that `MEDIA_ROOT` and `MEDIA_URL` are already configured (they are: `MEDIA_URL = "media/"`, `MEDIA_ROOT = BASE_DIR / "media"`). Ensure `media/` is in `.gitignore`.

  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "import django; django.setup(); from django.conf import settings; print('uploads' in settings.INSTALLED_APPS, settings.MEDIA_ROOT)"`

- [ ] **Step 3**: Define the `FileUpload` model

  - Files:
    - `uploads/models.py` — add `FileUpload` model

  - Details:
    ```python
    class FileUpload(TimeStampedModel):
        class Status(models.TextChoices):
            PENDING = "pending", "Pending"
            READY = "ready", "Ready"
            FAILED = "failed", "Failed"

        user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="uploads")
        file = models.FileField(upload_to="uploads/%Y/%m/")
        original_filename = models.CharField(max_length=255)
        file_size = models.PositiveBigIntegerField(help_text="File size in bytes")
        mime_type = models.CharField(max_length=100)
        status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
        error_message = models.TextField(blank=True)

        class Meta:
            db_table = "file_upload"
            ordering = ["-created_at"]
            indexes = [
                models.Index(fields=["user", "-created_at"]),
                models.Index(fields=["status"]),
            ]
    ```
    Inherit from `TimeStampedModel`. Use `TextChoices` for status per conventions. The `upload_to` uses date-based subdirectories to avoid flat directory buildup. Store `original_filename` separately because Django may rename files on collision.

  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py makemigrations uploads --check --dry-run`

- [ ] **Step 4**: Define the `Workflow` model

  - Files:
    - `uploads/models.py` — add `Workflow` model

  - Details:
    ```python
    class Workflow(TimeStampedModel):
        name = models.CharField(max_length=200, unique=True)
        slug = models.SlugField(max_length=200, unique=True)
        description = models.TextField(blank=True)
        task_name = models.CharField(
            max_length=255,
            help_text="Dotted path to the Celery task (e.g., uploads.tasks.ocr_task)"
        )
        accepted_mime_types = models.JSONField(
            default=list,
            help_text='List of accepted MIME types, e.g. ["application/pdf", "image/*"]'
        )
        max_file_size = models.PositiveBigIntegerField(
            default=52428800,
            help_text="Maximum file size in bytes (default 50MB)"
        )
        is_active = models.BooleanField(default=True)

        class Meta:
            db_table = "workflow"
            ordering = ["name"]
    ```
    The `task_name` field maps to a Celery task that will be looked up dynamically at dispatch time. `accepted_mime_types` uses JSONField to store a list of MIME type patterns (supports wildcards like `image/*`). `slug` is used for URL-friendly references.

  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "import django; django.setup(); from uploads.models import Workflow; print(Workflow._meta.db_table)"`

- [ ] **Step 5**: Define the `WorkflowRun` model

  - Files:
    - `uploads/models.py` — add `WorkflowRun` model

  - Details:
    ```python
    class WorkflowRun(TimeStampedModel):
        class Status(models.TextChoices):
            PENDING = "pending", "Pending"
            RUNNING = "running", "Running"
            COMPLETED = "completed", "Completed"
            FAILED = "failed", "Failed"

        file_upload = models.ForeignKey(FileUpload, on_delete=models.CASCADE, related_name="workflow_runs")
        workflow = models.ForeignKey(Workflow, on_delete=models.PROTECT, related_name="runs")
        user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="workflow_runs")
        status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
        progress = models.PositiveSmallIntegerField(default=0, help_text="Progress percentage 0-100")
        started_at = models.DateTimeField(null=True, blank=True)
        completed_at = models.DateTimeField(null=True, blank=True)
        result_output = models.TextField(blank=True, help_text="Workflow result or output text")
        error_message = models.TextField(blank=True)
        celery_task_id = models.CharField(max_length=255, blank=True)

        class Meta:
            db_table = "workflow_run"
            ordering = ["-created_at"]
            indexes = [
                models.Index(fields=["user", "-created_at"]),
                models.Index(fields=["status"]),
                models.Index(fields=["file_upload", "-created_at"]),
            ]
    ```
    `on_delete=PROTECT` on workflow FK prevents deleting workflows that have runs. `celery_task_id` stores the Celery task ID for potential cancellation or status lookup. Denormalized `user` FK avoids joins through `file_upload` for the common "my workflow runs" query.

  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py makemigrations uploads --check --dry-run`

- [ ] **Step 6**: Create and apply database migrations

  - Files:
    - `uploads/migrations/0001_initial.py` — auto-generated migration

  - Details:
    Run `makemigrations` to generate the initial migration for all three models, then apply it.

  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py makemigrations uploads && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py migrate uploads`

- [ ] **Step 7**: Register models in Django admin

  - Files:
    - `uploads/admin.py` — add `FileUploadAdmin`, `WorkflowAdmin`, `WorkflowRunAdmin`

  - Details:
    Register all three models with appropriate `list_display`, `list_filter`, `search_fields`, and `readonly_fields`. `WorkflowAdmin` should use `prepopulated_fields = {"slug": ("name",)}`. `WorkflowRunAdmin` should make status-related fields and timestamps read-only. `FileUploadAdmin` should show file details and link to the user.

  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check`

- [ ] **Step 8**: Create upload services

  - Files:
    - `uploads/services/__init__.py` — package init
    - `uploads/services/uploads.py` — file upload handling service
    - `uploads/services/workflows.py` — workflow dispatch service

  - Details:
    `uploads/services/uploads.py`:
    - `create_upload(user, file)` — validate file size and type, save FileUpload record, return the instance
    - `validate_file(file, max_size=None)` — check size limit and basic MIME type detection

    `uploads/services/workflows.py`:
    - `get_available_workflows(file_upload)` — return active workflows that accept the file's MIME type
    - `start_workflow(file_upload, workflow, user)` — create WorkflowRun record, dispatch Celery task, return the run instance
    - `check_mime_match(mime_type, accepted_patterns)` — check if a MIME type matches a list of patterns (supports `*` wildcards)

  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "import django; django.setup(); from uploads.services.uploads import create_upload; from uploads.services.workflows import start_workflow; print('Services importable')"`

- [ ] **Step 9**: Create the Celery task for workflow execution

  - Files:
    - `uploads/tasks.py` — `execute_workflow_task`

  - Details:
    ```python
    @shared_task(
        name="uploads.tasks.execute_workflow_task",
        bind=True,
        max_retries=1,
        default_retry_delay=120,
    )
    def execute_workflow_task(self, workflow_run_id):
        """Execute an AI workflow on an uploaded file."""
        from uploads.models import WorkflowRun

        run = WorkflowRun.objects.select_related("workflow", "file_upload").get(id=workflow_run_id)
        run.status = WorkflowRun.Status.RUNNING
        run.started_at = timezone.now()
        run.celery_task_id = self.request.id
        run.save(update_fields=["status", "started_at", "celery_task_id", "updated_at"])

        try:
            # Look up and call the actual workflow task by name
            from celery import current_app
            task = current_app.tasks[run.workflow.task_name]
            result = task.apply(args=[run.id])
            # The actual workflow task is responsible for updating progress and result
        except Exception as exc:
            run.status = WorkflowRun.Status.FAILED
            run.error_message = str(exc)
            run.completed_at = timezone.now()
            run.save(update_fields=["status", "error_message", "completed_at", "updated_at"])
            raise
    ```
    This is the dispatcher task. It updates the run status to RUNNING, then calls the workflow-specific task by looking it up in the Celery task registry. Individual AI workflow tasks (OCR, classification, etc.) are implemented separately in future PEPs and are responsible for updating the WorkflowRun's `progress`, `result_output`, and final `status`.

  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "import django; django.setup(); from uploads.tasks import execute_workflow_task; print('Task registered:', execute_workflow_task.name)"`

- [ ] **Step 10**: Create a placeholder/echo workflow task for testing

  - Files:
    - `uploads/tasks.py` — add `echo_workflow_task`

  - Details:
    A simple task that reads the uploaded file, sleeps briefly to simulate processing, and stores a summary as the result. This allows end-to-end testing of the upload-to-workflow-to-result pipeline without any real AI integration.
    ```python
    @shared_task(
        name="uploads.tasks.echo_workflow_task",
        bind=True,
    )
    def echo_workflow_task(self, workflow_run_id):
        """Placeholder workflow: echoes file metadata as the result."""
        from uploads.models import WorkflowRun
        import time

        run = WorkflowRun.objects.select_related("file_upload").get(id=workflow_run_id)

        # Simulate processing with progress updates
        for pct in (25, 50, 75, 100):
            time.sleep(1)  # Simulate work
            run.progress = pct
            run.save(update_fields=["progress", "updated_at"])

        run.status = WorkflowRun.Status.COMPLETED
        run.result_output = f"Processed: {run.file_upload.original_filename} ({run.file_upload.file_size} bytes, {run.file_upload.mime_type})"
        run.completed_at = timezone.now()
        run.save(update_fields=["status", "result_output", "completed_at", "updated_at"])

        return {"status": "ok", "workflow_run_id": run.id}
    ```

  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "import django; django.setup(); from uploads.tasks import echo_workflow_task; print('Echo task registered:', echo_workflow_task.name)"`

- [ ] **Step 11**: Create upload forms

  - Files:
    - `frontend/forms/uploads.py` — `FileUploadForm`

  - Details:
    Create a form with a `FileField` for the upload. Style the file input widget using the same `INPUT_CLASS` pattern from `frontend/forms/auth.py`. Add `clean_file()` method that validates file size against the configured limit and checks MIME type against a configurable allowlist.

  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "import django; django.setup(); from frontend.forms.uploads import FileUploadForm; print('Form importable')"`

- [ ] **Step 12**: Create frontend views for the upload portal

  - Files:
    - `frontend/views/uploads.py` — upload list, upload create, file detail, workflow start, workflow run status views

  - Details:
    Five views, all decorated with `@frontend_login_required`:

    1. `upload_list(request)` — list user's uploads with pagination, template: `frontend/uploads/list.html`
    2. `upload_create(request)` — GET shows form, POST processes upload via `create_upload` service, redirects to file detail. Template: `frontend/uploads/create.html`
    3. `upload_detail(request, pk)` — show file info and available workflows, list workflow runs. Template: `frontend/uploads/detail.html`
    4. `workflow_start(request, pk, workflow_slug)` — POST-only, calls `start_workflow` service, redirects to run status
    5. `workflow_run_status(request, pk, run_pk)` — show run status with HTMX polling partial. Template: `frontend/uploads/run_status.html`. If `request.htmx`, return partial `frontend/uploads/partials/run_progress.html`.

    All views filter by `request.user` to ensure users can only see their own uploads.

  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "import django; django.setup(); from frontend.views.uploads import upload_list, upload_create, upload_detail; print('Views importable')"`

- [ ] **Step 13**: Add URL routes

  - Files:
    - `frontend/urls.py` — add upload portal URL patterns

  - Details:
    Add URL patterns under the existing `frontend` app namespace:
    ```python
    path("uploads/", upload_list, name="upload_list"),
    path("uploads/new/", upload_create, name="upload_create"),
    path("uploads/<int:pk>/", upload_detail, name="upload_detail"),
    path("uploads/<int:pk>/run/<slug:workflow_slug>/", workflow_start, name="workflow_start"),
    path("uploads/<int:pk>/runs/<int:run_pk>/", workflow_run_status, name="workflow_run_status"),
    ```
    These are added to the existing `frontend/urls.py` alongside the auth and dashboard routes, keeping all `/app/` paths in one URL configuration.

  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "import django; django.setup(); from django.urls import reverse; print(reverse('frontend:upload_list')); print(reverse('frontend:upload_create'))"`

- [ ] **Step 14**: Create upload portal templates

  - Files:
    - `frontend/templates/frontend/uploads/list.html` — file upload list page
    - `frontend/templates/frontend/uploads/create.html` — upload form page
    - `frontend/templates/frontend/uploads/detail.html` — file detail with workflow actions
    - `frontend/templates/frontend/uploads/run_status.html` — workflow run status page
    - `frontend/templates/frontend/uploads/partials/run_progress.html` — HTMX polling partial for live status

  - Details:
    All full-page templates extend `frontend/base.html` and use the `page_title`, `sidebar_active`, `page_header`, `page_header_actions`, and `page_content` blocks.

    **list.html**: Table of uploads showing filename, size, date, status. "Upload File" button in `page_header_actions`. Empty state message when no uploads.

    **create.html**: Upload form with drag-and-drop zone (Alpine.js `x-data` for drag state, file preview). Form submits via standard POST with `enctype="multipart/form-data"`.

    **detail.html**: File metadata card (name, size, type, uploaded date). Section listing available workflows with "Start" buttons (POST forms). Section listing past workflow runs with status badges and links.

    **run_status.html**: Status card showing workflow name, progress bar, timestamps. Uses `hx-get` on the progress partial with `hx-trigger="every 3s"` while status is pending/running. Shows result output when completed, error message when failed.

    **partials/run_progress.html**: Just the progress section — status badge, progress bar, timestamps. Returns itself with continued polling trigger if still running, or final state without trigger if completed/failed.

    Use Tailwind CSS utility classes consistent with existing templates (primary colors, rounded-lg, shadow, etc.).

  - Verify: `ls frontend/templates/frontend/uploads/list.html frontend/templates/frontend/uploads/create.html frontend/templates/frontend/uploads/detail.html frontend/templates/frontend/uploads/run_status.html frontend/templates/frontend/uploads/partials/run_progress.html`

- [ ] **Step 15**: Update sidebar navigation

  - Files:
    - `frontend/templates/frontend/components/sidebar.html` — add "Uploads" nav link

  - Details:
    Add an "Uploads" navigation link to the sidebar, using the same pattern as the existing "Dashboard" link. The link should point to `{% url 'frontend:upload_list' %}` and highlight when `sidebar_active == "uploads"`. Use an upload/file icon (SVG or Tailwind icon class).

  - Verify: `grep -q "upload_list" frontend/templates/frontend/components/sidebar.html && echo "Sidebar updated"`

- [ ] **Step 16**: Rebuild Tailwind CSS

  - Files:
    - `static/css/main.css` — regenerated output

  - Details:
    Run `make css` to rebuild the CSS file after adding new templates with Tailwind classes.

  - Verify: `make css`

- [ ] **Step 17**: Add `media/` to `.gitignore` and create seed data fixture

  - Files:
    - `.gitignore` — ensure `media/` directory is ignored
    - `uploads/fixtures/seed_workflows.json` — fixture with the echo workflow for development

  - Details:
    Add `media/` to `.gitignore` if not already present. Create a fixture that pre-loads the echo workflow:
    ```json
    [
      {
        "model": "uploads.workflow",
        "fields": {
          "name": "Echo (Test)",
          "slug": "echo-test",
          "description": "Test workflow that echoes file metadata. Use this to verify the upload pipeline works.",
          "task_name": "uploads.tasks.echo_workflow_task",
          "accepted_mime_types": ["*/*"],
          "max_file_size": 52428800,
          "is_active": true
        }
      }
    ]
    ```

  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py loaddata uploads/fixtures/seed_workflows.json`

## Testing

- [ ] Unit tests for upload service (`validate_file`, `create_upload`) — Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev pytest uploads/tests/ -v`
- [ ] Unit tests for workflow service (`check_mime_match`, `get_available_workflows`, `start_workflow`)
- [ ] Unit tests for form validation (`FileUploadForm`)
- [ ] Integration test: upload a file via the create view, verify FileUpload record created
- [ ] Integration test: start echo workflow on uploaded file, verify WorkflowRun created and task dispatched
- [ ] Manual testing: full workflow through the browser (upload → select workflow → view progress → see result)

## Rollback Plan

- All changes are additive (new app, new models, new views, new templates)
- Migrations can be reversed: `python manage.py migrate uploads zero`
- Remove `"uploads"` from `INSTALLED_APPS` in `boot/settings.py`
- Delete the `uploads/` app directory
- Remove upload-related URL patterns from `frontend/urls.py`
- Remove upload-related views, forms, and templates from `frontend/`
- Revert sidebar changes in `frontend/templates/frontend/components/sidebar.html`
- No existing data or functionality is affected

## aikb Impact Map

- [ ] `aikb/models.md` — Add FileUpload, Workflow, WorkflowRun model documentation with fields, relationships, and status choices. Update Entity Relationship Summary diagram.
- [ ] `aikb/services.md` — Document `uploads/services/uploads.py` and `uploads/services/workflows.py` functions. Update "Current State" to note services now exist.
- [ ] `aikb/tasks.md` — Document `execute_workflow_task` and `echo_workflow_task`. Update "Current State" to note tasks now exist.
- [ ] `aikb/signals.md` — N/A (no signals in this PEP)
- [ ] `aikb/admin.md` — Document FileUploadAdmin, WorkflowAdmin, WorkflowRunAdmin registrations
- [ ] `aikb/cli.md` — N/A (no CLI changes)
- [ ] `aikb/architecture.md` — Add `uploads` app to the Django App Structure table and directory tree. Update URL Routing section with `/app/uploads/` routes.
- [ ] `aikb/conventions.md` — N/A (no new conventions, follows existing patterns)
- [ ] `aikb/dependencies.md` — N/A (no new Python dependencies)
- [ ] `aikb/specs-roadmap.md` — Update to reflect upload portal as implemented; note next steps (specific AI workflow implementations)
- [ ] `CLAUDE.md` — Add `uploads` app to the Django App Structure table. Add upload URLs to URL Structure section.

## Final Verification

### Acceptance Criteria

- [ ] **Upload via web form**: Navigate to `/app/uploads/new/`, upload a file, verify redirect to detail page
  - Verify: Manual browser test after `python manage.py runserver`

- [ ] **File stored and recorded**: After upload, check that file exists in `media/uploads/` and `FileUpload` record exists in DB
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "import django; django.setup(); from uploads.models import FileUpload; print(f'{FileUpload.objects.count()} uploads in DB')"`

- [ ] **File validation**: Attempt to upload a file exceeding 50MB, verify form error displayed
  - Verify: Manual browser test

- [ ] **Upload list visible**: Navigate to `/app/uploads/`, verify list of user's uploads shown
  - Verify: Manual browser test

- [ ] **Workflow admin**: Create a workflow in Django admin, verify it appears in workflow list
  - Verify: Manual browser test via `/admin/`

- [ ] **Workflow start**: Click "Start" on a workflow for an uploaded file, verify WorkflowRun created
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "import django; django.setup(); from uploads.models import WorkflowRun; print(f'{WorkflowRun.objects.count()} runs in DB')"`

- [ ] **Status polling**: On run status page, verify HTMX polls and updates progress
  - Verify: Manual browser test (watch network tab for polling requests)

- [ ] **Result display**: After echo workflow completes, verify result text shown on status page
  - Verify: Manual browser test

- [ ] **Sidebar link**: Verify "Uploads" link appears in sidebar navigation
  - Verify: `grep "upload_list" frontend/templates/frontend/components/sidebar.html`

- [ ] **Models inherit TimeStampedModel**: Verify all models have `created_at` and `updated_at`
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python -c "import django; django.setup(); from uploads.models import FileUpload, Workflow, WorkflowRun; [print(m.__name__, hasattr(m, 'created_at')) for m in (FileUpload, Workflow, WorkflowRun)]"`

### Integration Checks

- [ ] **Full upload-to-result workflow**: Upload a text file → start echo workflow → wait for completion → view result
  - Steps: 1. Login 2. Go to `/app/uploads/new/` 3. Upload a `.txt` file 4. Click "Start" on Echo workflow 5. Watch progress update 6. Verify result text appears
  - Expected: Result shows "Processed: <filename> (<size> bytes, text/plain)"

- [ ] **Access control**: Login as user A, upload a file. Login as user B, navigate to `/app/uploads/`. Verify user B cannot see user A's uploads.
  - Steps: 1. Create two users 2. Upload as user A 3. Switch to user B 4. Check upload list and direct URL access
  - Expected: User B sees empty list and gets 404 on user A's upload detail page

### Regression Checks

- [ ] `python manage.py check` passes
  - Verify: `source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check`
- [ ] `ruff check .` passes
  - Verify: `ruff check .`

## Completion

- [ ] **Update `PEPs/IMPLEMENTED/LATEST.md`** — Add entry with PEP number, title, commit hash(es), and summary
- [ ] **Update `PEPs/INDEX.md`** — Remove the PEP row
- [ ] **Remove PEP directory** — Delete `PEPs/PEP_0001_ai_upload_portal/`
