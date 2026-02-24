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
├── common/         # Shared utilities (no models of its own beyond abstract)
│   ├── models.py       # TimeStampedModel (abstract)
│   ├── fields.py       # MoneyField (DecimalField 12,2)
│   ├── utils.py        # generate_reference(), apply_date_range(), safe_dispatch()
│   └── management/     # Custom management commands
├── accounts/       # Users and authentication
│   ├── models.py       # User (AbstractUser)
│   └── admin.py        # UserAdmin
├── frontend/       # Web UI: auth + dashboard
│   ├── decorators.py   # @frontend_login_required
│   ├── forms/          # auth.py (login/register forms)
│   ├── views/          # auth.py, dashboard.py
│   ├── templatetags/   # frontend_tags.py
│   ├── templates/      # frontend/ namespace (base, auth, dashboard, errors, components)
│   └── urls.py         # /app/ URL prefix
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

No multi-tenancy. No RBAC system. No service layer yet. No custom middleware beyond WhiteNoise and django-htmx.

## URL Routing

- `/healthz/` → `boot.urls.healthz` -- Liveness probe (no I/O, always returns 200)
- `/admin/` → Django admin (UserAdmin only)
- `/app/` → `frontend.urls` -- Web UI (session-based auth)
  - `/app/login/`, `/app/register/`, `/app/logout/` -- Authentication
  - `/app/` -- Dashboard (requires login)

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

- **Development**: Local filesystem for media, WhiteNoise for static
- **Production**: WhiteNoise for static, local filesystem for media (no S3 configured yet)

## Background Processing

See [tasks.md](tasks.md) for details.

- **Celery** with PostgreSQL broker via SQLAlchemy transport (no Redis)
- **No tasks defined yet** -- skeleton only
- **Dev mode**: `CELERY_TASK_ALWAYS_EAGER=True` (synchronous, no broker needed)
