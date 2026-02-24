# Doorito

A clean Django 6.0 project skeleton with authentication, a dashboard shell, background task infrastructure, and a structured enhancement proposal workflow — ready to build on.

## What's Included

- **Django 6.0** with django-configurations (class-based settings: Dev/Production)
- **PostgreSQL** (psycopg adapter)
- **Celery** with PostgreSQL broker (SQLAlchemy transport) — no Redis needed
- **WhiteNoise** for static file serving
- **Tailwind CSS v4** (standalone CLI, no Node.js)
- **HTMX + Alpine.js** for frontend interactivity
- **Click CLI** (`doorito` script with example commands)
- **Docker Compose** (web + db + celery-worker)
- **uv** package manager with `.in` → `.txt` lockfile workflow
- **Ruff + pre-commit** code quality
- **PEPs** — Project Enhancement Proposals for structured development
- **aikb** — AI knowledge base for Claude Code / AI agent context

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
docker compose exec web manage createsuperuser
```

Services: **web** (8000, gunicorn), **db** (PostgreSQL 16), **celery-worker**.

## Project Structure

```
doorito/
├── boot/               # Django project config (settings, urls, wsgi, asgi, celery)
├── common/             # Shared utilities: TimeStampedModel, MoneyField
├── accounts/           # Custom User model (email-based, extends AbstractUser)
├── frontend/           # Web UI: auth, dashboard — server-rendered with HTMX + Alpine.js
├── aikb/               # AI knowledge base for agent context (11 files)
├── PEPs/               # Project Enhancement Proposals
├── static/             # CSS (Tailwind input + compiled), JS (HTMX, Alpine.js)
├── templates/          # Global base template
├── scripts/            # PEP helper scripts and Claude prompt templates
├── doorito             # Click CLI entry point
├── Makefile            # Developer convenience targets
├── Procfile.dev        # Development process definitions (honcho)
├── docker-compose.yml  # Docker Compose configuration
├── Dockerfile          # Container image definition
└── manage.py           # Django management script
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

## Configuration

Doorito uses [django-configurations](https://django-configurations.readthedocs.io/) for class-based settings:

- **`Dev`** — Development: `DEBUG=True`, eager Celery (no broker needed), console email
- **`Production`** — Production: security hardening, WhiteNoise compressed storage

Set via `DJANGO_CONFIGURATION` environment variable. See [.env.example](.env.example) for all options.

## How to Extend

1. **Add a new app**: `python manage.py startapp myapp`, add to `INSTALLED_APPS` in `boot/settings.py`
2. **Add models**: Inherit from `common.models.TimeStampedModel` for automatic `created_at`/`updated_at`
3. **Add views**: Create views in the `frontend` app or a new app, wire up in `urls.py`
4. **Add Celery tasks**: Follow conventions in `aikb/tasks.md`
5. **Propose changes**: Use the PEP workflow — `make claude-pep-draft DESC="description"`

## PEPs (Project Enhancement Proposals)

All development is tracked through PEPs in the `PEPs/` directory. See [PEPs/ABOUT.md](PEPs/ABOUT.md) for the full workflow, and [CLAUDE.md](CLAUDE.md) for AI agent instructions.

## License

[Business Source License 1.1](LICENSE.md) — you can use, modify, and redistribute Doorito, but you may not offer it as a hosted service competing with the Licensor. Each version converts to Apache 2.0 four years after release.
