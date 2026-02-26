# Dependencies Reference

## Dependency Management

Dependencies are managed using **uv** with a `.in` -> `.txt` compile pattern:

- `requirements.in` -- production dependencies (human-edited)
- `requirements-dev.in` -- dev dependencies, includes `-r requirements.in` (human-edited)
- `requirements.txt` -- locked production deps with hashes (generated, **do not edit**)
- `requirements-dev.txt` -- locked dev deps with hashes (generated, **do not edit**)

### Adding Dependencies

```bash
# Production dependency:
# 1. Edit requirements.in
# 2. Recompile both lockfiles:
uv pip compile --generate-hashes requirements.in -o requirements.txt
uv pip compile --generate-hashes requirements-dev.in -o requirements-dev.txt
uv pip install -r requirements-dev.txt

# Dev-only dependency:
# 1. Edit requirements-dev.in
# 2. Recompile dev lockfile:
uv pip compile --generate-hashes requirements-dev.in -o requirements-dev.txt
uv pip install -r requirements-dev.txt
```

## Production Dependencies (requirements.in)

### Core Framework
| Package | Version | Purpose |
|---------|---------|---------|
| Django | >=5.2,<7.0 | Web framework |
| django-configurations | >=2.5 | Class-based settings (Base/Dev/Production) |
| python-dotenv | >=1.0 | Environment variable loading from `.env` |
| psycopg[binary] | >=3.1 | PostgreSQL database adapter |
| dj-database-url | >=2.0 | Database URL parsing for `DATABASE_URL` |

### Static Files
| Package | Version | Purpose |
|---------|---------|---------|
| whitenoise | >=6.6 | Static file serving (dev and production) |

### Background Tasks
| Package | Version | Purpose |
|---------|---------|---------|
| celery | >=5.4 | Distributed task queue |
| sqlalchemy | >=2.0 | Celery broker transport (Postgres via SQLAlchemy) |
| django-celery-results | >=2.5 | Store task results in Django database |
| django-celery-beat | >=2.6,<3.0 | Periodic task scheduling (database scheduler) |

Transitive dependencies (pulled by django-celery-beat): `django-timezone-field`, `python-crontab`, `cron-descriptor`, `tzdata`.

### Production Server
| Package | Version | Purpose |
|---------|---------|---------|
| gunicorn | >=23.0 | Production WSGI server |

### CLI
| Package | Version | Purpose |
|---------|---------|---------|
| click | >=8.0 | CLI framework for `doorito` script |
| rich | >=13.0 | Terminal output formatting (tables, progress bars) |

### Frontend
| Package | Version | Purpose |
|---------|---------|---------|
| django-htmx | >=1.19 | HTMX server-side helpers (`request.htmx`, `HtmxMiddleware`) |

### Frontend (Non-Python, vendored)
| Asset | Location | Purpose |
|-------|----------|---------|
| Tailwind CSS standalone CLI | `./tailwindcss` (gitignored) | Utility-first CSS compilation (no Node.js) |
| HTMX | `static/js/htmx.min.js` | HTML-over-the-wire partial page updates |
| Alpine.js | `static/js/alpine.min.js` | Lightweight client-side UI state |

## Development Dependencies (requirements-dev.in)

| Package | Version | Purpose |
|---------|---------|---------|
| black | >=25.1 | Code formatter (88-char line length) |
| ruff | >=0.9 | Fast linter (replaces flake8, isort, etc.) |
| pre-commit | >=4.0 | Git pre-commit hooks |
| pytest | >=8.0 | Test framework |
| pytest-django | >=4.8 | Django test integration for pytest |
| honcho | >=2.0 | Procfile-based process manager |

## System Dependencies (in Dockerfile)

| Package | Purpose |
|---------|---------|
| libpq-dev | PostgreSQL C library (required by psycopg) |

## Runtime Requirements

| Service | Version | Required In |
|---------|---------|------------|
| Python | >=3.12 | All environments |
| PostgreSQL | >=16 | All environments (database + Celery broker) |
