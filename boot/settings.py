"""
Django settings for Doorito project.

Uses django-configurations for class-based settings.
See https://docs.djangoproject.com/en/6.0/ref/settings/
"""

from pathlib import Path

from configurations import Configuration, values


class Base(Configuration):
    """Base configuration for all environments."""

    BASE_DIR = Path(__file__).resolve().parent.parent

    SECRET_KEY = values.SecretValue()

    DEBUG = values.BooleanValue(False)

    ALLOWED_HOSTS = values.ListValue([])

    # Application definition
    INSTALLED_APPS = [
        "django.contrib.admin",
        "django.contrib.auth",
        "django.contrib.contenttypes",
        "django.contrib.sessions",
        "django.contrib.messages",
        "django.contrib.staticfiles",
        # Third-party apps
        "django_celery_results",
        "django_celery_beat",
        "django_htmx",
        # Project apps
        "common",
        "accounts",
        "frontend",
        "uploads",
    ]

    MIDDLEWARE = [
        "django.middleware.security.SecurityMiddleware",
        "whitenoise.middleware.WhiteNoiseMiddleware",
        "django_htmx.middleware.HtmxMiddleware",
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
        "django.middleware.clickjacking.XFrameOptionsMiddleware",
    ]

    ROOT_URLCONF = "boot.urls"

    TEMPLATES = [
        {
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "DIRS": [BASE_DIR / "templates"],
            "APP_DIRS": True,
            "OPTIONS": {
                "context_processors": [
                    "django.template.context_processors.request",
                    "django.contrib.auth.context_processors.auth",
                    "django.contrib.messages.context_processors.messages",
                ],
            },
        },
    ]

    WSGI_APPLICATION = "boot.wsgi.application"

    # Database
    DATABASES = values.DatabaseURLValue("sqlite:///db.sqlite3")

    # Custom user model
    AUTH_USER_MODEL = "accounts.User"

    # Auth URLs
    LOGIN_URL = "/app/login/"

    # Password validation
    AUTH_PASSWORD_VALIDATORS = [
        {
            "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
        },
        {
            "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        },
        {
            "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
        },
        {
            "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
        },
    ]

    # Internationalization
    LANGUAGE_CODE = values.Value("en-us")
    TIME_ZONE = values.Value("UTC")
    USE_I18N = True
    USE_TZ = True

    # Static files (CSS, JavaScript, Images)
    STATIC_URL = values.Value("static/")
    STATIC_ROOT = Path(BASE_DIR / "staticfiles")
    STATICFILES_DIRS = [Path(BASE_DIR / "static")]

    # Media files (user uploads)
    MEDIA_URL = values.Value("media/")
    MEDIA_ROOT = Path(BASE_DIR / "media")

    # Email settings
    DEFAULT_FROM_EMAIL = values.Value(
        "noreply@example.com", environ_name="DEFAULT_FROM_EMAIL"
    )
    SITE_URL = values.Value("http://localhost:8000", environ_name="SITE_URL")

    # Celery (Postgres broker via SQLAlchemy transport)
    CELERY_BROKER_URL = values.Value(
        "sqla+postgresql://doorito:doorito@localhost:5432/doorito",
        environ_name="CELERY_BROKER_URL",
    )
    CELERY_RESULT_BACKEND = values.Value(
        "django-db",
        environ_name="CELERY_RESULT_BACKEND",
    )
    CELERY_ACCEPT_CONTENT = ["json"]
    CELERY_TASK_SERIALIZER = "json"
    CELERY_RESULT_SERIALIZER = "json"
    CELERY_TIMEZONE = "UTC"
    CELERY_TASK_TRACK_STARTED = True
    CELERY_TASK_TIME_LIMIT = 300  # 5 min hard limit
    CELERY_TASK_SOFT_TIME_LIMIT = 240  # 4 min soft limit
    CELERY_RESULT_EXPIRES = 86400  # 24 hours
    CELERY_WORKER_HIJACK_ROOT_LOGGER = False

    # Celery Beat (database scheduler)
    CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
    CLEANUP_UPLOADS_INTERVAL_HOURS = 6  # Valid range: 1-24

    @property
    def CELERY_BEAT_SCHEDULE(self):
        from celery.schedules import crontab

        return {
            "cleanup-expired-upload-files": {
                "task": "uploads.tasks.cleanup_expired_upload_files_task",
                "schedule": crontab(
                    minute=0, hour=f"*/{self.CLEANUP_UPLOADS_INTERVAL_HOURS}"
                ),
                "options": {"queue": "default"},
            },
        }

    # File upload settings
    FILE_UPLOAD_MAX_SIZE = 52_428_800  # 50 MB
    FILE_UPLOAD_TTL_HOURS = 24
    FILE_UPLOAD_ALLOWED_TYPES = (
        None  # None = accept all; set to list e.g. ["application/pdf"]
    )

    # Default field
    DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


class Dev(Base):
    """Development configuration."""

    DEBUG = True

    SECRET_KEY = values.Value("django-insecure-dev-key-change-in-production")

    ALLOWED_HOSTS = values.ListValue(["localhost", "127.0.0.1"])

    CSRF_TRUSTED_ORIGINS = values.ListValue([])

    # Email backend - console for development
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

    # Celery: eager mode for development (tasks run synchronously, no broker needed)
    CELERY_TASK_ALWAYS_EAGER = values.BooleanValue(
        True,
        environ_name="CELERY_TASK_ALWAYS_EAGER",
    )
    CELERY_TASK_EAGER_PROPAGATES = True

    # WhiteNoise for serving static files in development
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }


class Production(Base):
    """Production configuration."""

    DEBUG = False

    ALLOWED_HOSTS = values.ListValue([])

    # Security settings
    SECURE_SSL_REDIRECT = values.BooleanValue(True)
    SECURE_HSTS_SECONDS = values.IntegerValue(31536000)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

    # Celery: disable eager mode for production
    CELERY_TASK_ALWAYS_EAGER = False
    CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

    # WhiteNoise for static files
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }
