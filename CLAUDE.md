# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Doorito is a clean Django 6.0 project skeleton designed as a starting point for new web applications. It provides authentication, a dashboard shell, background task infrastructure, and a structured enhancement proposal workflow — ready to build on.

### Technology Stack
- **Framework**: Django 6.0 with django-configurations (class-based settings)
- **Database**: PostgreSQL 16+ (psycopg adapter)
- **Task Queue**: Celery 5.4+ with PostgreSQL broker (SQLAlchemy transport)
- **Static Files**: WhiteNoise
- **Frontend CSS**: Tailwind CSS v4 (standalone CLI, no Node.js)
- **Frontend Interactivity**: HTMX (server-driven) + Alpine.js (client-side)
- **CLI**: Click + Rich (`doorito` script)
- **Package Manager**: uv

## Deep Context (aikb/)

The `aikb/` directory contains detailed contextual documentation for AI agents. **Read these files before working on complex tasks** to avoid unnecessary codebase exploration:

| File | Contents |
|------|----------|
| `aikb/architecture.md` | 3-app structure, request flow, template hierarchy |
| `aikb/models.md` | User model, TimeStampedModel, MoneyField |
| `aikb/services.md` | Service layer convention (empty — no services yet) |
| `aikb/tasks.md` | Celery configuration, task conventions (no tasks yet) |
| `aikb/signals.md` | Signal conventions (no signals yet) |
| `aikb/admin.md` | UserAdmin registration |
| `aikb/cli.md` | `doorito` CLI commands (hello, check) |
| `aikb/deployment.md` | Docker, environment variables, production configuration |
| `aikb/conventions.md` | Code patterns, naming conventions, import order |
| `aikb/dependencies.md` | All dependencies with versions and purpose |
| `aikb/specs-roadmap.md` | Skeleton status, next steps |

## Project Enhancement Proposals (PEPs/)

The `PEPs/` directory contains enhancement proposals for evolving the project, inspired by Python Enhancement Proposals (PEPs). Use these for proposing and tracking changes.

### PEP Structure
Each PEP is a directory `PEPs/PEP_NNNN_<title>/` with 2 required + 3 optional files:
- **`summary.md`** (required): Problem, solution, rationale, out of scope, impact, acceptance criteria, risk level, status history, dependencies
- **`plan.md`** (required): Context files, implementation steps as checkable list with inline verification commands, testing, rollback, aikb impact map, final verification (acceptance + integration + regression), completion checklist. Large plans can be split: `plan_a.md`, `plan_b.md`, etc. Plans can be amended during implementation with dated notes.
- **`research.md`** (optional): Investigative findings before planning — current state analysis, key files, technical constraints, pattern analysis, risks, recommendations. Include when the PEP requires codebase exploration or non-trivial analysis.
- **`discussions.md`** (optional): Q&A log for resolved questions, design decisions, and open threads. Include when the PEP has design tensions or unresolved questions.
- **`journal.md`** (optional): Multi-session resumption log. Created only when implementation spans multiple sessions. Uses structured "Left Off" format.

### Creating a PEP

**Automated (recommended):** `make claude-pep-draft DESC="description of the enhancement"` — Claude infers a title, creates the PEP directory, fills in summary.md and plan.md, and adds the INDEX.md row.

**Manual:**
1. Check `PEPs/INDEX.md` for the next available number (or use `make pep-new TITLE=name`)
2. Create directory `PEPs/PEP_NNNN_<title>/` with `summary.md` and `plan.md` from templates
3. Fill in the summary (problem, solution, out of scope, acceptance criteria, risk, dependencies)
4. Optionally create `research.md` if codebase exploration or analysis is needed before planning
5. Fill in the plan (context files, implementation steps with verification commands, aikb impact map, final verification)
6. Optionally create `discussions.md` if there are design tensions or open questions
7. Set status to **Proposed** when summary and plan are complete
8. Add a row to `PEPs/INDEX.md` with risk level

### Implementing a PEP

**Automated workflow** (each step is a `make claude-pep-*` command):
1. `make claude-pep-draft DESC="..."` — Create the PEP
2. `make claude-pep-research PEP=NNNN` — Deep codebase exploration → research.md
3. `make claude-pep-plan PEP=NNNN` — Refine plan with codebase-grounded analysis
4. `make claude-pep-discuss PEP=NNNN` — Resolve open questions → discussions.md
5. `make claude-pep-todo PEP=NNNN` — Break plan into granular checklist
6. `make claude-pep-preflight PEP=NNNN` — Validate plan against current codebase
7. `make claude-pep-implement PEP=NNNN` — Execute plan steps (repeatable across sessions)
8. `make claude-pep-review PEP=NNNN` — Review and resolve `<!-- REVIEW: ... -->` inline notes (run anytime)
9. `make claude-pep-finalize PEP=NNNN` — aikb updates, LATEST.md entry, cleanup

**Manual:**
1. Read the **context files** listed in the plan before writing any code
2. If a **research file** exists, read it for investigative findings and codebase analysis
3. If a **journal file** exists, read it to see where the last session left off
4. If a **discussions file** exists, read it for prior decisions and open threads
5. Follow the **plan** — check off each step after running its verification command
6. If the implementation spans multiple sessions, create `journal.md` and append progress
7. After all steps are done, run the **final verification** checks in the plan

### PEP Lifecycle
`Proposed → Accepted → Implementing → Implemented` (or `Rejected` / `Deferred` / `Withdrawn`)

### When a PEP Is Implemented
After all code changes are complete, these steps are **mandatory**:
1. **Follow the aikb impact map** in the plan — update all listed `aikb/` files
2. **Update `CLAUDE.md`** — If architecture, commands, dependencies, or conventions changed
3. **Run final verification** — Execute acceptance, integration, and regression checks from the plan
4. **Add entry to `PEPs/IMPLEMENTED/LATEST.md`** — Record PEP number, git commit(s), and brief summary. Keep only the latest 10 entries; archive older ones to `IMPLEMENTED/PAST_YYYYMMDD.md`
5. **Update `PEPs/INDEX.md`** — Remove the PEP's row
6. **Delete PEP directory** — Remove the entire `PEPs/PEP_NNNN_<title>/` directory (git history preserves them)

See `PEPs/ABOUT.md` for full documentation on conventions and usage.

## Development Commands

### Running manage.py Commands (Claude Code)

This project uses django-configurations, which requires specific environment variables. Claude Code must use this pattern for all manage.py commands:

```bash
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py <command>
```

Examples:
```bash
# Run migrations
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py migrate

# Make migrations
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py makemigrations

# Run development server
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py runserver

# Django check
source ~/.virtualenvs/inventlily-d22a143/bin/activate && DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py check
```

### Makefile Targets

The project includes a `Makefile` that wraps common commands. Human developers should use `make <target>` directly. Claude Code should continue using the explicit `source ... && DJANGO_SETTINGS_MODULE=... python manage.py` pattern above (since `make` doesn't activate the virtualenv).

Key targets: `make help`, `make install`, `make migrate`, `make makemigrations`, `make run`, `make server`, `make shell`, `make test`, `make lint`, `make format`, `make check`, `make superuser`, `make clean`, `make tailwind-install`, `make css`, `make css-watch`, `make pep-new TITLE=name`, `make pep-complete PEP=NNNN`, `make pep-archive`.

Claude PEP workflow targets (invoke `claude -p` with structured prompts):
- `make claude-pep-draft DESC="description"` — Draft a new PEP (Claude infers title, runs pep-new.sh, fills summary and plan)
- `make claude-pep-research PEP=NNNN` — Research codebase for a PEP (creates research.md)
- `make claude-pep-plan PEP=NNNN` — Refine PEP plan with deep codebase analysis
- `make claude-pep-discuss PEP=NNNN` — Resolve open questions (creates/updates discussions.md)
- `make claude-pep-todo PEP=NNNN` — Add detailed todo checklist to plan.md
- `make claude-pep-preflight PEP=NNNN` — Preflight check plan against codebase (ready/not-ready verdict)
- `make claude-pep-implement PEP=NNNN` — Implement unchecked plan steps (updates journal.md)
- `make claude-pep-review PEP=NNNN` — Review and resolve `<!-- REVIEW: ... -->` inline notes
- `make claude-pep-finalize PEP=NNNN` — Finalize PEP (aikb updates, LATEST.md entry, cleanup)

All claude-pep targets support `PROMPT=variant` to select alternative prompt files (default: `default`). Prompt files live in `scripts/prompts/pep-<command>/<variant>.md`.

### Manual Development Setup

```bash
# Activate virtual environment
workon inventlily-d22a143

# Setup
cp .env.example .env
uv pip install -r requirements-dev.txt

# Run development server
python manage.py runserver

# Run all development processes (web + celery worker)
honcho start -f Procfile.dev

# Database
python manage.py migrate
python manage.py makemigrations

# Static files
python manage.py collectstatic

# Generate secret key for production
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### Package Management

Dependencies are managed using **uv** with a `.in` → `.txt` compile pattern:

- `requirements.in` — production dependencies (human-edited)
- `requirements-dev.in` — dev dependencies, includes `-r requirements.in` (human-edited)
- `requirements.txt` — locked production deps with hashes (generated, do not edit)
- `requirements-dev.txt` — locked dev deps with hashes (generated, do not edit)

```bash
# Add a new production dependency
# 1. Edit requirements.in
# 2. Recompile both lockfiles:
uv pip compile --generate-hashes requirements.in -o requirements.txt
uv pip compile --generate-hashes requirements-dev.in -o requirements-dev.txt
uv pip install -r requirements-dev.txt

# Add a new dev-only dependency
# 1. Edit requirements-dev.in
# 2. Recompile dev lockfile:
uv pip compile --generate-hashes requirements-dev.in -o requirements-dev.txt
uv pip install -r requirements-dev.txt
```

### Frontend Tooling (Tailwind CSS + HTMX + Alpine.js)

The project uses Tailwind CSS v4 (standalone CLI), HTMX, and Alpine.js for frontend development. No Node.js required.

```bash
# Install Tailwind CSS standalone CLI (one-time, downloads ~40MB binary)
make tailwind-install

# Compile CSS (minified, writes static/css/main.css — committed to git)
make css

# Watch mode (recompiles on template changes)
make css-watch
```

- **Base template**: `templates/base.html` loads Tailwind CSS, HTMX, Alpine.js, and configures CSRF for HTMX
- **Design tokens**: Brand colors (primary purple, secondary teal, accent amber, neutral slate, state colors) and fonts defined in `static/css/input.css` via `@theme {}`
- **HTMX vendored**: `static/js/htmx.min.js`
- **Alpine.js vendored**: `static/js/alpine.min.js`

### Code Quality

This project uses **Ruff** for linting and formatting, **Black** for editor compatibility, and **pre-commit** for automated checks.

```bash
# Run linter
ruff check .

# Run linter with auto-fix
ruff check --fix .

# Run formatter
ruff format .

# Run all pre-commit hooks
pre-commit run --all-files

# Install pre-commit hooks (first time setup)
pre-commit install
```

Configuration is in `pyproject.toml`.

### Celery (Background Tasks)

Background tasks run via Celery with PostgreSQL as the broker (SQLAlchemy transport). In development, tasks run **eagerly** (synchronously, no broker needed) by default.

```bash
# Start celery worker (only needed if CELERY_TASK_ALWAYS_EAGER=False)
DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev celery -A boot worker -Q high,default -c 4 --loglevel=info

# Or run everything together via honcho
honcho start -f Procfile.dev
```

No tasks are defined yet — see `aikb/tasks.md` for conventions when adding tasks.

### Docker

The image uses `docker-entrypoint.sh` to dispatch by role. Services specify a role name instead of raw commands.

```bash
# Build and run (includes postgres, celery worker)
docker compose up --build

# Run in background
docker compose up -d

# Run CLI commands in container
docker compose run --rm web doorito hello
docker compose run --rm web manage migrate --noinput

# Drop into a shell
docker compose run --rm web bash

# Build image only
docker build -t doorito .
```

Services: web (gunicorn), db (PostgreSQL 16), celery-worker.

Entrypoint environment variables: `RUN_MIGRATIONS` (default `false`), `WEB_PORT` (default `8000`), `WEB_WORKERS` (default `4`), `CELERY_CONCURRENCY` (default `4`), `LOG_LEVEL` (default `info`).

### Docker Development

A `docker-compose.dev.yml` override runs the full stack with Dev settings (runserver with auto-reload, eager Celery, DEBUG=True). Celery worker is skipped by default since tasks run eagerly.

```bash
# Start dev stack (web + db)
make docker-up

# Or explicitly:
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

# Stop dev stack
make docker-down

# Tail logs
make docker-logs

# Shell into web container
make docker-shell

# Opt into celery container (non-eager task processing)
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile celery up --build
```

## Architecture

### Configuration System

Uses **django-configurations** with class-based settings in `boot/settings.py`:
- `Base` — Shared settings across all environments
- `Dev` — Development settings (DEBUG=True, eager Celery, console email)
- `Production` — Production settings with security hardening

Environment is selected via `DJANGO_CONFIGURATION` env var (Dev/Production).

### Django App Structure

The project has 3 apps (see `aikb/architecture.md` for details):

| App | Responsibility |
|-----|---------------|
| `common` | Shared utilities: TimeStampedModel, MoneyField, dispatch helper |
| `accounts` | Custom User model (email-based, extends AbstractUser) |
| `frontend` | Web UI: auth (login/register/logout), dashboard — server-rendered views with HTMX + Alpine.js |

Additional directories:
- `boot/` — Django project configuration (settings, urls, wsgi, asgi, celery)
- `aikb/` — AI knowledge base for agent context
- `PEPs/` — Project Enhancement Proposals

### URL Structure

- `/healthz/` — Health check endpoint (JSON)
- `/admin/` — Django admin
- `/app/login/`, `/app/register/`, `/app/logout/` — Session-based authentication
- `/app/` — Dashboard (requires login)

### Frontend Web UI

The `frontend` app provides the web interface at `/app/`, using session-based auth and server-rendered Django views.

Templates live under `frontend/templates/frontend/` with three base templates (`base.html`, `base_auth.html`, `base_minimal.html`). The `@frontend_login_required` decorator redirects unauthenticated users to `/app/login/`.

The sidebar (`components/sidebar.html`) provides navigation with collapsible desktop sidebar and mobile drawer. Dashboard has placeholder cards ready for customization.

### Storage Configuration

- **Development**: WhiteNoise serves static files locally
- **Production**: WhiteNoise with `CompressedManifestStaticFilesStorage`

### Background Task Infrastructure

Uses **Celery** with **PostgreSQL** broker (SQLAlchemy transport), integrated with django-configurations:
- `boot/celery.py` — Celery app setup (calls `configurations.setup()` before app creation)
- `boot/__init__.py` — Exports `celery_app` so Celery loads when Django starts
- **Dev mode**: `CELERY_TASK_ALWAYS_EAGER=True` — tasks run synchronously, no broker needed
- **Production**: PostgreSQL broker, separate worker process in Docker Compose

## Coding Conventions

### Key Patterns (see aikb/conventions.md for full reference)

- **Models**: Inherit from `TimeStampedModel`, use `MoneyField` for money
- **Services**: Business logic in `{app}/services/`, never in models or views
- **Tasks**: `@shared_task(bind=True)` with lazy imports, service delegation, structured returns
- **Signals**: Side effects in `{app}/signals.py`, registered in `apps.py` `ready()`
- **CLI**: Click commands delegate to services, Rich for output formatting

### Naming
- Models: PascalCase singular (`User`)
- Services: snake_case functions
- Tasks: snake_case with `_task` suffix
- Constants: UPPER_SNAKE_CASE
