# Doorito

An open-source file ingest portal built on Django 6.0 — designed for chunked uploads, batch processing, and reliable event-driven integration with AI runners.

Built on a clean Django skeleton with authentication, a dashboard shell, background task infrastructure, and a structured enhancement proposal workflow.

## What's Included

### Infrastructure (implemented)

- **Django 6.0** with django-configurations (class-based settings: Dev/Production)
- **PostgreSQL** (psycopg adapter)
- **Celery** with PostgreSQL broker (SQLAlchemy transport) — no Redis needed
- **WhiteNoise** for static file serving
- **Tailwind CSS v4** (standalone CLI, no Node.js)
- **HTMX + Alpine.js** for frontend interactivity
- **Click CLI** (`doorito` script with example commands)
- **Docker Compose** (web + db + celery-worker + celery-beat)
- **uv** package manager with `.in` → `.txt` lockfile workflow
- **Ruff + pre-commit** code quality
- **Event Outbox** — Durable outbox pattern for reliable event emission
- **Upload Infrastructure** — Upload models (batch, file, session, part) with cleanup tasks
- **PEPs** — Project Enhancement Proposals for structured development
- **aikb** — AI knowledge base for Claude Code / AI agent context

### OSS Ingest Portal (roadmap)

The portal pipeline is being developed through a series of PEPs (0008–0019):

- **Canonical Domain Model** — IngestFile, UploadSession, UploadPart, UploadBatch, PortalEventOutbox
- **Storage Backend Abstraction** — Pluggable local/S3 storage with streaming support
- **Authentication & API Access** — Session + token-based auth for UI and API
- **Chunked Upload Pipeline** — Session creation, chunk upload, resume, and finalization
- **Batch Upload Support** — Group multiple files with progress tracking
- **Event Schema & Outbox Dispatcher** — Stable `file.uploaded` events with durable delivery to AI runners
- **Minimal OSS UI** — Upload, file list, batch detail, and event monitoring
- **Operational Guardrails** — Cleanup jobs, health endpoints, structured logging

See [PEPs/INDEX.md](PEPs/INDEX.md) for the full dependency graph and status.

## Requirements

- Python 3.12+
- PostgreSQL 16+
- [uv](https://docs.astral.sh/uv/) (package manager)

## Quick Start

### Local Development

```bash
# Clone the repository
git clone <repo-url>
cd doorito

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
uv pip install -r requirements-dev.txt

# Configure environment
cp .env.example .env
# Edit .env — the defaults work for local PostgreSQL with user/pass "doorito"

# Install pre-commit hooks
pre-commit install

# Run migrations
make migrate

# Create a superuser
make superuser

# Start the development server
make server

# Or start web + celery worker together
make run
```

The web server runs at `http://localhost:8000`.

### Docker

```bash
# Build and start all services
docker compose up --build

# In another terminal — create a superuser
docker compose run --rm web manage createsuperuser
```

Services: **web** (8000, gunicorn), **db** (PostgreSQL 16), **celery-worker**, **celery-beat**.

### Docker Development

A `docker-compose.dev.yml` override runs the full stack with Dev settings (runserver with auto-reload, eager Celery, DEBUG=True):

```bash
# Start dev stack (web + db)
make docker-up

# Stop dev stack
make docker-down

# Tail logs
make docker-logs

# Shell into web container
make docker-shell

# Opt into celery container (non-eager task processing)
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile celery up --build
```

## Project Structure

```
doorito/
├── boot/                   # Django project config (settings, urls, wsgi, asgi, celery)
├── common/                 # Shared utilities: TimeStampedModel, MoneyField, OutboxEvent, uuid7
├── accounts/               # Custom User model (email-based, extends AbstractUser)
├── uploads/                # Upload infrastructure: models, services, admin, cleanup tasks
├── frontend/               # Web UI: auth, dashboard — server-rendered with HTMX + Alpine.js
├── aikb/                   # AI knowledge base for agent context (11 files)
├── PEPs/                   # Project Enhancement Proposals
├── static/                 # CSS (Tailwind input + compiled), JS (HTMX, Alpine.js)
├── templates/              # Global base template
├── scripts/                # PEP helper scripts and Claude prompt templates
├── doorito                 # Click CLI entry point
├── Makefile                # Developer convenience targets
├── Procfile.dev            # Development process definitions (honcho)
├── docker-compose.yml      # Production Docker Compose
├── docker-compose.dev.yml  # Development Docker Compose override
├── Dockerfile              # Container image definition
├── LICENSE.md              # Business Source License 1.1
└── manage.py               # Django management script
```

## Development Workflow

The [Makefile](Makefile) wraps common commands:

| Command | Description |
|---------|-------------|
| `make help` | Show all available targets |
| `make install` | Install dev dependencies with uv |
| `make migrate` | Run database migrations |
| `make makemigrations` | Create new migration files |
| `make run` | Start web + celery worker (honcho) |
| `make server` | Start only the Django dev server |
| `make shell` | Open Django shell |
| `make test` | Run tests with pytest |
| `make lint` | Run ruff linter |
| `make format` | Run ruff formatter |
| `make check` | Run Django system checks |
| `make superuser` | Create a superuser account |
| `make clean` | Remove Python cache files |
| `make css` | Compile Tailwind CSS |
| `make css-watch` | Watch and recompile CSS |
| `make docker-up` | Start dev stack in Docker |
| `make docker-down` | Stop Docker dev stack |
| `make docker-logs` | Tail Docker dev stack logs |
| `make docker-shell` | Shell into web container |

## Configuration

Doorito uses [django-configurations](https://django-configurations.readthedocs.io/) for class-based settings:

- **`Dev`** — Development: `DEBUG=True`, eager Celery (no broker needed), console email
- **`Production`** — Production: security hardening, WhiteNoise compressed storage

Set via `DJANGO_CONFIGURATION` environment variable. See [.env.example](.env.example) for all options.

## URL Structure

| Path | Description |
|------|-------------|
| `/healthz/` | Health check endpoint (JSON) |
| `/admin/` | Django admin |
| `/app/login/` | Login page |
| `/app/register/` | Registration page |
| `/app/logout/` | Logout |
| `/app/` | Dashboard (requires login) |

## How to Extend

1. **Add a new app**: `python manage.py startapp myapp`, add to `INSTALLED_APPS` in `boot/settings.py`
2. **Add models**: Inherit from `common.models.TimeStampedModel` for automatic `created_at`/`updated_at`
3. **Add views**: Create views in the `frontend` app or a new app, wire up in `urls.py`
4. **Add Celery tasks**: Follow conventions in `aikb/tasks.md`
5. **Emit events**: Use `common.services.outbox.emit_event()` for durable event emission
6. **Propose changes**: Use the PEP workflow — `make claude-pep-draft DESC="description"`

## PEPs (Project Enhancement Proposals)

All development is tracked through PEPs in the `PEPs/` directory. See [PEPs/ABOUT.md](PEPs/ABOUT.md) for the full workflow, and [CLAUDE.md](CLAUDE.md) for AI agent instructions.

### Current Roadmap

The OSS Ingest Portal pipeline (PEPs 0008–0019) is the primary development focus. These PEPs form a dependency chain starting from the canonical domain model through to the complete upload, event, and UI layers. See [PEPs/INDEX.md](PEPs/INDEX.md) for status and the full dependency graph.

## License

[Business Source License 1.1](LICENSE.md) — you can use, modify, and redistribute Doorito, but you may not offer it as a hosted service competing with the Licensor. Each version converts to Apache 2.0 four years after release.
