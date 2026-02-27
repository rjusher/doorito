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

All development is tracked through PEPs in the `PEPs/` directory. Each PEP is a directory containing a `summary.md` (what and why) and `plan.md` (how, with checkable steps and verification commands), plus optional `research.md`, `discussions.md`, and `journal.md` files. See [PEPs/ABOUT.md](PEPs/ABOUT.md) for the full conventions.

### PEP Lifecycle

```
Proposed -> Accepted -> Implementing -> Implemented
         -> Rejected / Deferred / Withdrawn
```

### Manual PEP Commands

```bash
# Create a new PEP from template (auto-assigns next number)
make pep-new TITLE=my_feature

# Validate PEP completion checklist
make pep-complete PEP=NNNN

# Archive old IMPLEMENTED/LATEST.md entries
make pep-archive
```

### AI-Assisted PEP Workflow (`claude-pep-*`)

The project includes a full suite of `make claude-pep-*` targets that invoke [Claude Code](https://claude.ai/code) with structured prompts to drive each phase of the PEP lifecycle. Each target runs Claude in `--permission-mode acceptEdits` with a phase-specific prompt template from `scripts/prompts/`.

#### Overview

| Step | Command | What It Does |
|------|---------|-------------|
| 1 | `make claude-pep-draft DESC="..."` | Create a new PEP — Claude infers a title, runs `pep-new.sh`, fills in `summary.md` and `plan.md` |
| 2 | `make claude-pep-research PEP=NNNN` | Deep codebase exploration — creates `research.md` with findings, key files, constraints |
| 3 | `make claude-pep-plan PEP=NNNN` | Refine the plan with codebase-grounded analysis — updates `plan.md` with detailed steps |
| 4 | `make claude-pep-discuss PEP=NNNN` | Resolve open questions — creates/updates `discussions.md` with design decisions |
| 5 | `make claude-pep-todo PEP=NNNN` | Break plan into granular checklist — adds detailed sub-steps to `plan.md` |
| 6 | `make claude-pep-preflight PEP=NNNN` | Validate plan against current codebase — returns ready/not-ready verdict |
| 7 | `make claude-pep-implement PEP=NNNN` | Execute unchecked plan steps — checks off steps, updates `journal.md` |
| 8 | `make claude-pep-review PEP=NNNN` | Review and resolve `<!-- REVIEW: ... -->` inline notes in PEP files |
| 9 | `make claude-pep-finalize PEP=NNNN` | Close out — update `aikb/` docs, add `LATEST.md` entry, clean up PEP directory |

#### Typical End-to-End Flow

```bash
# 1. Draft a new PEP from a description
make claude-pep-draft DESC="Add chunked upload support with resumable sessions"

# 2. Research the codebase (optional, for complex PEPs)
make claude-pep-research PEP=0020

# 3. Refine the plan with deep codebase analysis
make claude-pep-plan PEP=0020

# 4. Resolve any open design questions (optional)
make claude-pep-discuss PEP=0020

# 5. Break the plan into granular implementation steps
make claude-pep-todo PEP=0020

# 6. Preflight check — is the plan ready to implement?
make claude-pep-preflight PEP=0020

# 7. Implement! (repeatable — picks up where the last session left off)
make claude-pep-implement PEP=0020

# 8. Review inline notes left during implementation (optional, run anytime)
make claude-pep-review PEP=0020

# 9. Finalize — update docs, record in LATEST.md, remove PEP directory
make claude-pep-finalize PEP=0020
```

#### Prompt Variants

All `claude-pep-*` targets support an optional `PROMPT=variant` parameter to select alternative prompt files. The default prompt is `default.md`. Prompt templates live in `scripts/prompts/pep-<command>/`:

```bash
# Use the default prompt
make claude-pep-implement PEP=0020

# Use a custom prompt variant
make claude-pep-implement PEP=0020 PROMPT=cautious
```

This loads `scripts/prompts/pep-implement/cautious.md` instead of `scripts/prompts/pep-implement/default.md`.

#### Command Reference

**`make claude-pep-draft DESC="description"`**

Creates a new PEP from scratch. Claude infers an appropriate title from the description, calls `pep-new.sh` to scaffold the directory, then fills in `summary.md` (problem, solution, rationale, acceptance criteria) and `plan.md` (context files, implementation steps, verification commands). The PEP is added to `INDEX.md` automatically.

**`make claude-pep-research PEP=NNNN`**

Performs deep codebase exploration for an existing PEP. Claude reads the summary, explores relevant source files, and creates `research.md` with: current state analysis, key files and functions, technical constraints, pattern analysis, risks, and recommendations. Best used before refining the plan for complex PEPs.

**`make claude-pep-plan PEP=NNNN`**

Refines the PEP's `plan.md` using codebase-grounded analysis. Claude reads the summary, any existing research, and the current plan, then updates implementation steps with specific file paths, code patterns, and verification commands drawn from the actual codebase.

**`make claude-pep-discuss PEP=NNNN`**

Resolves open questions and design tensions. Claude reads all PEP files, identifies ambiguities or trade-offs, and creates/updates `discussions.md` with resolved questions (including rationale) and any remaining open threads.

**`make claude-pep-todo PEP=NNNN`**

Adds granular sub-steps to `plan.md`. Takes existing high-level steps and breaks them into atomic, independently verifiable tasks with specific file paths and verification commands.

**`make claude-pep-preflight PEP=NNNN`**

Validates the plan against the current codebase state. Claude checks that referenced files exist, patterns match expectations, dependencies are met, and the plan is internally consistent. Returns a clear **ready** or **not-ready** verdict with specific issues if not ready.

**`make claude-pep-implement PEP=NNNN`**

Executes unchecked steps in the plan. Claude reads the plan (and journal if it exists), finds the next unchecked step, implements it, runs the verification command, and checks it off. Updates `journal.md` for session resumption. Safe to run multiple times — it picks up where the last session left off.

**`make claude-pep-review PEP=NNNN`**

Scans PEP files and implementation code for `<!-- REVIEW: ... -->` inline notes left during planning or implementation, and resolves them. Can be run at any point in the lifecycle.

**`make claude-pep-finalize PEP=NNNN`**

Closes out a fully implemented PEP. Claude updates all `aikb/` files per the plan's impact map, updates `CLAUDE.md` if needed, adds an entry to `PEPs/IMPLEMENTED/LATEST.md`, removes the PEP row from `INDEX.md`, and deletes the PEP directory.

### Current Roadmap

The OSS Ingest Portal pipeline (PEPs 0008–0019) is the primary development focus. These PEPs form a dependency chain starting from the canonical domain model through to the complete upload, event, and UI layers. See [PEPs/INDEX.md](PEPs/INDEX.md) for status and the full dependency graph.

## License

[Business Source License 1.1](LICENSE.md) — you can use, modify, and redistribute Doorito, but you may not offer it as a hosted service competing with the Licensor. Each version converts to Apache 2.0 four years after release.
