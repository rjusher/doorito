# Deployment & Infrastructure

## Docker Setup

### Dockerfile
- **Base image**: `python:3.12-slim`
- **System dependencies**: `libpq-dev` (PostgreSQL)
- **Package manager**: `uv` for fast dependency installation
- **Tailwind CSS**: Standalone CLI downloaded at build time, rebuilds `static/css/main.css` (safety net -- compiled CSS is also committed to git)
- **Static files**: Collected at build time via `collectstatic`
- **Entrypoint**: `docker-entrypoint.sh` with role dispatch
- **Default CMD**: `web` (gunicorn on port 8000)
- **Security**: Non-root `django` user (UID/GID 1001)
- **Port**: Configurable via `WEB_PORT` (default 8000)

### docker-entrypoint.sh

A single entrypoint script dispatches by role argument. Sets `DJANGO_SETTINGS_MODULE` and `DJANGO_CONFIGURATION` defaults and supports optional pre-start migrations.

| Argument | Process launched |
|----------|-----------------|
| `web` (default) | `gunicorn boot.wsgi:application --bind 0.0.0.0:$WEB_PORT --workers $WEB_WORKERS` |
| `celery-worker` | `celery -A boot worker -Q high,default -c $CELERY_CONCURRENCY --loglevel=$LOG_LEVEL` |
| `celery-beat` | `celery -A boot beat --scheduler DatabaseScheduler --loglevel=$LOG_LEVEL` |
| `doorito` | CLI with remaining args (`python /app/doorito "$@"`) |
| `dev` | Runs `collectstatic --noinput` then `python manage.py runserver 0.0.0.0:$WEB_PORT` |
| `manage` | `python manage.py` with remaining args |
| `*` (anything else) | `exec "$@"` -- passthrough to shell |

### docker-compose.yml Services

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| `web` | Build from Dockerfile | 8000 | Django application server (gunicorn) |
| `db` | postgres:16-alpine | 5432 | PostgreSQL database |
| `celery-worker` | Build from Dockerfile | -- | Async task processing |
| `celery-beat` | Build from Dockerfile | -- | Periodic task scheduling |

**No Redis** -- Celery uses PostgreSQL as broker via SQLAlchemy transport.
**No Daphne** -- no WebSocket support.
**celery-beat** -- periodic task scheduling via `django-celery-beat` DatabaseScheduler.

### Volumes
- `postgres_data` -- persistent database storage

### Health Checks
- `db`: `pg_isready -U doorito`

### docker-compose.dev.yml (Development Override)

Layers on top of `docker-compose.yml` for Dev-appropriate settings:

- **web**: Uses `dev` entrypoint role (runserver with auto-reload), sets `DJANGO_CONFIGURATION=Dev`, `DJANGO_DEBUG=True`, `CELERY_TASK_ALWAYS_EAGER=True`. Mounts source code as volume.
- **celery-worker**: Moved to `celery` profile (not started by default since tasks run eagerly in dev).
- **celery-beat**: Moved to `celery` profile (not started by default since tasks run eagerly in dev).

```bash
# Start dev stack (web + db only, no celery worker)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

# Or use Makefile shortcut
make docker-up     # start
make docker-down   # stop

# Opt into celery worker when needed
docker compose -f docker-compose.yml -f docker-compose.dev.yml --profile celery up --build
```

## Procfile.dev (Local Development)

```
web: DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev python manage.py runserver 0.0.0.0:${WEB_PORT:-8000}
worker: DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev celery -A boot worker -Q high,default -c 4 --loglevel=info
beat: DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev celery -A boot beat --scheduler django_celery_beat.schedulers:DatabaseScheduler --loglevel=info
```

Run all processes: `honcho start -f Procfile.dev`

Port is configurable via `WEB_PORT` environment variable (default 8000).

## Environment Variables

### Core Django
| Variable | Default | Description |
|----------|---------|-------------|
| `DJANGO_SETTINGS_MODULE` | `boot.settings` | Settings module path |
| `DJANGO_CONFIGURATION` | `Dev` | Settings class (Dev/Production) |
| `DJANGO_SECRET_KEY` | (insecure default in Dev) | Required in production |
| `DJANGO_DEBUG` | `True` (Dev) | Debug mode |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated hosts |

### Database
| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///db.sqlite3` | Database connection URL |

### Celery
| Variable | Default | Description |
|----------|---------|-------------|
| `CELERY_BROKER_URL` | `sqla+postgresql://doorito:doorito@localhost:5432/doorito` | Postgres broker URL |
| `CELERY_TASK_ALWAYS_EAGER` | `True` (Dev) | Sync execution in dev |
| `CLEANUP_UPLOADS_INTERVAL_HOURS` | `6` | Hours between upload cleanup runs (crontab) |

### Docker Entrypoint
| Variable | Default | Description |
|----------|---------|-------------|
| `RUN_MIGRATIONS` | `false` | Run `migrate --noinput` before web/dev start |
| `WEB_PORT` | `8000` | Web server bind port |
| `WEB_WORKERS` | `4` | Gunicorn worker count |
| `CELERY_CONCURRENCY` | `4` | Celery worker concurrency |
| `LOG_LEVEL` | `info` | Log level for celery worker |

## No Kubernetes

The skeleton does not include Kubernetes manifests. K8s deployment can be added via a PEP when needed.

## Production Considerations

### Security
- `DJANGO_SECRET_KEY` must be set (never use default)
- `DJANGO_DEBUG=False`
- `DJANGO_ALLOWED_HOSTS` restricted to actual domains
- CSRF, session cookie security, HSTS headers enabled in Production class

### Database
- PostgreSQL 16 required (also serves as Celery broker)
- Connection URL via `DATABASE_URL` env var

### Static Files
- WhiteNoise serves static files in both dev and production
- No S3 configured (can be added via PEP)
