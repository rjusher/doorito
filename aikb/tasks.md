# Background Tasks Reference

Doorito uses Celery for background task processing with `django-celery-beat` for periodic scheduling.

## Configuration

- **Celery app**: `boot/celery.py` (calls `configurations.setup()` before creating the Celery app)
- **Exported in**: `boot/__init__.py` as `celery_app`
- **Broker**: PostgreSQL via SQLAlchemy transport (`sqla+postgresql://...`)
- **Result backend**: django-celery-results (database storage)
- **Dev mode**: `CELERY_TASK_ALWAYS_EAGER=True` -- tasks run synchronously, no broker connection needed
- **No Redis** -- the project uses Postgres as both database and Celery broker

### Broker URL Format

```
CELERY_BROKER_URL=sqla+postgresql://user:password@host:5432/dbname
```

This uses Celery's SQLAlchemy transport to store task messages in a `kombu_message` table within the same PostgreSQL database. No separate message broker service is needed.

### Settings

```python
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 300      # 5 min hard limit
CELERY_TASK_SOFT_TIME_LIMIT = 240  # 4 min soft limit
CELERY_RESULT_EXPIRES = 86400      # 24 hours
```

## Queue Routing

Two queues are configured for future use:

| Queue | Purpose |
|-------|---------|
| `high` | Time-sensitive operations (webhooks, payments, notifications) |
| `default` | Background processing (maintenance, batch jobs) |

## Current State

The first task module exists in the `uploads` app. Celery autodiscovery (`boot/celery.py`) automatically discovers `tasks.py` in all `INSTALLED_APPS`. When adding tasks to a new app, create `{app}/tasks.py` and follow the conventions below.

---

## Uploads App

### uploads/tasks.py

**`cleanup_expired_upload_files_task`**
- **Name**: `uploads.tasks.cleanup_expired_upload_files_task`
- **Purpose**: Deletes upload files older than `FILE_UPLOAD_TTL_HOURS` (default 24 hours). Removes both physical files from disk and database records.
- **Model**: `UploadFile` (lazy import inside task body)
- **Batch limit**: Processes at most 1000 expired records per run to stay within `CELERY_TASK_TIME_LIMIT` (300s).
- **Settings read**: `FILE_UPLOAD_TTL_HOURS` (via `getattr` with 24-hour default)
- **Queue**: `default` (Celery's default routing — appropriate for maintenance tasks)
- **Return format**: `{"deleted": int, "remaining": int}`
- **Retry**: `max_retries=2`, `default_retry_delay=60`
- **Notes**: Uses lazy imports. Handles `FileNotFoundError` gracefully for already-deleted files. In Dev mode, runs synchronously via `CELERY_TASK_ALWAYS_EAGER=True`. Scheduled via celery-beat every 6 hours (at 00:00, 06:00, 12:00, 18:00 UTC) using `CLEANUP_UPLOADS_INTERVAL_HOURS` setting. Can also be invoked manually.

## Task Conventions

All tasks should follow these patterns:

```python
@shared_task(
    name="app.tasks.module.task_name",   # Explicit name
    bind=True,                           # Access to self for retry
    max_retries=2,                       # Retry limit
    default_retry_delay=60,              # Seconds between retries
)
def my_task(self, object_id):
    # Lazy imports to avoid circular dependencies
    from app.models import MyModel
    from app.services.my_service import do_thing

    try:
        obj = MyModel.objects.get(id=object_id)
    except MyModel.DoesNotExist:
        logger.warning("Object %s not found", object_id)
        return

    try:
        result = do_thing(obj)
    except Exception as exc:
        logger.exception("Failed for object %s", object_id)
        raise self.retry(exc=exc)

    return {"status": "ok", "result": result}
```

Key patterns:
- `@shared_task` decorator with `bind=True` for retry support
- Lazy imports inside task body to avoid circular imports
- Structured return values (dict with counts/status)
- Logging with `logger.info` for success, `logger.exception` for errors
- Service delegation: tasks should be thin wrappers around service function calls

## Running Celery

```bash
# Worker (processes both queues)
DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev \
  celery -A boot worker -Q high,default -c 4 --loglevel=info

# Or use honcho (starts web + worker + beat together)
honcho start -f Procfile.dev
```

## Celery Beat (Periodic Task Scheduling)

Periodic tasks are managed by `django-celery-beat` with the DatabaseScheduler, which stores schedules in PostgreSQL.

### Configuration

- **Scheduler**: `django_celery_beat.schedulers:DatabaseScheduler` (set via `CELERY_BEAT_SCHEDULER`)
- **Schedule source**: `CELERY_BEAT_SCHEDULE` in `boot/settings.py` (synced to database on beat startup)
- **Admin UI**: `django-celery-beat` registers admin models automatically (PeriodicTask, IntervalSchedule, CrontabSchedule, etc.)

### Current Schedule

| Task Name | Task Path | Schedule | Queue |
|-----------|-----------|----------|-------|
| `cleanup-expired-upload-files` | `uploads.tasks.cleanup_expired_upload_files_task` | Every 6 hours (crontab) | default |

### Adding a New Periodic Task

1. Add the task entry to `CELERY_BEAT_SCHEDULE` in `boot/settings.py`
2. Restart the beat process (or modify via Django admin for runtime changes)
3. Update this file with the new task

### Running Beat

```bash
# Standalone
DJANGO_SETTINGS_MODULE=boot.settings DJANGO_CONFIGURATION=Dev \
  celery -A boot beat --scheduler django_celery_beat.schedulers:DatabaseScheduler --loglevel=info

# Via honcho (starts web + worker + beat)
honcho start -f Procfile.dev
```

### Operational Notes

- **Single instance**: Only one beat process must run at a time. Running multiple instances causes duplicate task dispatch.
- **Removed schedules**: Tasks removed from `CELERY_BEAT_SCHEDULE` are NOT automatically deleted from the database. Remove via Django admin or database query.
- **Schedule changes**: Runtime schedule changes via Django admin take effect within 5 seconds (beat polls `PeriodicTasks.last_update`).
