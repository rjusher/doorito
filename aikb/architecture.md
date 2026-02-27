# Architecture Overview

This document describes the high-level architecture of Doorito, a Django 6.0 skeleton project.

## Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Web Framework | Django 6.0 | Core application framework |
| Settings | django-configurations | Class-based settings (Base/Dev/Production) |
| Database | PostgreSQL 16 | Primary data store (psycopg adapter) |
| Task Queue | Celery 5.4+ | Async background processing |
| Message Broker | PostgreSQL (SQLAlchemy transport) | Celery broker -- no Redis required |
| Static Files | WhiteNoise | Static asset serving |
| CSS Framework | Tailwind CSS v4 (standalone CLI) | Utility-first CSS |
| Server Interactivity | HTMX + django-htmx | HTML-over-the-wire partial page updates |
| Client Interactivity | Alpine.js | Lightweight client-side UI state |
| CLI | Click + Rich | Project CLI (`doorito` script) |
| Package Manager | uv | Fast dependency resolution and installation |

## Configuration System

Uses **django-configurations** with a class hierarchy in `boot/settings.py`:

```
Base (shared settings)
├── Dev (DEBUG=True, eager Celery, console email, insecure secret key)
└── Production (security hardening, HSTS, secure cookies)
```

Environment is selected via `DJANGO_CONFIGURATION` env var. All configurable values use `values.*` wrappers from django-configurations, falling back to `.env` via python-dotenv.

**Running manage.py** always requires:
```bash
DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py <command>
```

## Django App Structure

```
doorito/
├── boot/           # Project configuration
│   ├── settings.py     # Class-based settings (Base, Dev, Production)
│   ├── urls.py         # Root URL routing → healthz + admin + frontend
│   ├── celery.py       # Celery app setup (configurations.setup() integration)
│   ├── wsgi.py         # WSGI entry point
│   └── asgi.py         # ASGI entry point
├── common/         # Shared utilities and cross-cutting infrastructure
│   ├── models.py       # TimeStampedModel (abstract), OutboxEvent, WebhookEndpoint
│   ├── fields.py       # MoneyField (DecimalField 12,2)
│   ├── utils.py        # uuid7(), generate_reference(), apply_date_range(), safe_dispatch()
│   ├── admin.py        # OutboxEventAdmin, WebhookEndpointAdmin
│   ├── services/       # outbox.py (emit_event, process_pending_events, cleanup), webhook.py (compute_signature, deliver_to_endpoint)
│   ├── tasks.py        # deliver_outbox_events_task, cleanup_delivered_outbox_events_task
│   ├── tests/          # test_models.py, test_services.py, test_tasks.py, test_webhook.py, test_admin.py
│   ├── migrations/     # 0001_initial.py (OutboxEvent), 0002_webhookendpoint.py
│   └── management/     # Custom management commands
├── accounts/       # Users and authentication
│   ├── models.py       # User (AbstractUser)
│   └── admin.py        # UserAdmin
├── frontend/       # Web UI: auth + dashboard + upload
│   ├── decorators.py   # @frontend_login_required
│   ├── forms/          # auth.py (login/register forms)
│   ├── views/          # auth.py, dashboard.py, upload.py
│   ├── templatetags/   # frontend_tags.py
│   ├── templates/      # frontend/ namespace (base, auth, dashboard, upload, errors, components)
│   ├── tests/          # test_views_upload.py
│   └── urls.py         # /app/ URL prefix
├── uploads/        # Batched, chunked file upload infrastructure
│   ├── models.py       # UploadBatch, UploadFile, UploadSession, UploadPart (UUID v7 PKs)
│   ├── admin.py        # UploadBatchAdmin, UploadFileAdmin, UploadSessionAdmin, UploadPartAdmin
│   ├── services/       # uploads.py (file + batch services), sessions.py (session + part services)
│   ├── tasks.py        # cleanup_expired_upload_files_task, notify_expiring_files_task
│   ├── tests/          # test_models.py, test_services.py, test_sessions.py, test_tasks.py
│   └── migrations/     # 0001_initial.py
├── templates/      # Project-level templates
│   └── base.html       # Root base template (loads Tailwind, HTMX, Alpine.js)
├── static/         # Static assets (CSS, JS)
├── doorito         # CLI entry point script
└── PEPs/           # Project Enhancement Proposals
```

## Request Flow

```
HTTP Request
  → Django Middleware Stack
    → WhiteNoiseMiddleware (static files)
    → HtmxMiddleware (request.htmx properties)
    → SessionMiddleware + AuthenticationMiddleware
      → View
        → Template Response
```

No multi-tenancy. No RBAC system. No custom middleware beyond WhiteNoise and django-htmx.

## URL Routing

- `/healthz/` → `boot.urls.healthz` -- Liveness probe (no I/O, always returns 200)
- `/admin/` → Django admin (UserAdmin only)
- `/app/` → `frontend.urls` -- Web UI (session-based auth)
  - `/app/login/`, `/app/register/`, `/app/logout/` -- Authentication
  - `/app/` -- Dashboard (requires login)
  - `/app/upload/` -- File upload page (requires login)

## Authentication

Session-based authentication only. The `@frontend_login_required` decorator redirects unauthenticated users to `/app/login/` with a `?next=` parameter. No API authentication, no JWT, no API keys.

## Frontend Tooling

Three lightweight tools complement Django's server-rendered architecture:

- **Tailwind CSS v4** (standalone CLI, no Node.js) -- utility-first CSS framework with CSS-first configuration. Design tokens defined via `@theme {}` in `static/css/input.css`. Compiled to `static/css/main.css` (committed to git). Build: `make css`, watch: `make css-watch`.
- **HTMX** (vendored `static/js/htmx.min.js`) -- HTML-over-the-wire interactivity. Integrated with `django-htmx` middleware (`request.htmx` properties). CSRF handled via `hx-headers` on `<body>`.
- **Alpine.js** (vendored `static/js/alpine.min.js`) -- client-only UI state (modals, toggles, dropdowns). Uses `x-data`, `x-show`, `x-on` attributes in templates. Loaded with `defer`.

**Template hierarchy**:
- `templates/base.html` -- Root base template loading Tailwind CSS, HTMX, Alpine.js
- `frontend/base.html` -- App shell for authenticated pages
- `frontend/base_auth.html` -- Centered card layout for auth pages (login, register)
- `frontend/base_minimal.html` -- Centered message for error pages (403, 404, 500)

## Storage

- **Static files**: WhiteNoise with `CompressedManifestStaticFilesStorage` (both environments)
- **Media files** (uploads):
  - **Dev**: Local filesystem via `FileSystemStorage` (`MEDIA_ROOT = BASE_DIR / "media"`, `MEDIA_URL = "media/"`)
  - **Production**: S3-compatible storage via `django-storages[s3]` (`S3Boto3Storage`). Configured through environment variables: `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_ENDPOINT_URL`, `AWS_S3_REGION_NAME`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_QUERYSTRING_AUTH`, `AWS_QUERYSTRING_EXPIRE`, `AWS_S3_FILE_OVERWRITE`. Works with AWS S3, MinIO, R2, Spaces, and other S3-compatible providers.
  - Upload files stored at `uploads/%Y/%m/` (date-based subdirectories, used as S3 key prefixes in Production)
  - `media/` directory is gitignored (Dev only)

## Background Processing

See [tasks.md](tasks.md) for details.

- **Celery** with PostgreSQL broker via SQLAlchemy transport (no Redis)
- **Tasks**: `deliver_outbox_events_task` and `cleanup_delivered_outbox_events_task` (common app) -- outbox event delivery via HTTP webhook and cleanup; `cleanup_expired_upload_files_task` and `notify_expiring_files_task` (uploads app) -- TTL-based cleanup and pre-expiry notifications
- **Outbox pattern**: `emit_event()` writes events to `OutboxEvent` table in the caller's transaction, dispatches delivery via `transaction.on_commit()`. `process_pending_events()` delivers events via HTTP POST to matching active `WebhookEndpoint` records. Periodic sweep via celery-beat catches missed events.
- **Periodic scheduling**: `django-celery-beat` with DatabaseScheduler (schedules stored in PostgreSQL). Beat process dispatches tasks on configured intervals. Schedule: outbox delivery sweep every 5 min, outbox cleanup every 6 hours, upload cleanup every 6 hours, pre-expiry notification sweep every hour.
- **Dev mode**: `CELERY_TASK_ALWAYS_EAGER=True` (synchronous, no broker needed)
