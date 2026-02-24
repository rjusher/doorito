#!/bin/bash
set -euo pipefail

# Defaults
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-boot.settings}"
export DJANGO_CONFIGURATION="${DJANGO_CONFIGURATION:-Production}"
WEB_PORT="${WEB_PORT:-8000}"

run_migrations() {
    if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
        echo "[entrypoint] Running migrations..."
        python manage.py migrate --noinput
    fi
}

case "${1:-web}" in
    web)
        run_migrations
        echo "[entrypoint] Starting gunicorn..."
        exec gunicorn boot.wsgi:application \
            --bind "0.0.0.0:${WEB_PORT}" \
            --workers "${WEB_WORKERS:-4}" \
            --access-logfile - \
            --error-logfile -
        ;;
    celery-worker)
        echo "[entrypoint] Starting celery worker..."
        exec celery -A boot worker \
            -Q high,default \
            -c "${CELERY_CONCURRENCY:-4}" \
            --loglevel="${LOG_LEVEL:-info}"
        ;;
    doorito)
        shift
        exec python /app/doorito "$@"
        ;;
    dev)
        run_migrations
        echo "[entrypoint] Collecting static files..."
        python manage.py collectstatic --noinput --ignore "input.css"
        echo "[entrypoint] Starting Django dev server..."
        exec python manage.py runserver "0.0.0.0:${WEB_PORT}"
        ;;
    manage)
        shift
        exec python manage.py "$@"
        ;;
    *)
        exec "$@"
        ;;
esac
