"""
Celery application configuration for Doorito.

Integrates Celery with django-configurations for class-based settings.
Must call configurations.setup() before creating the Celery app.
"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "boot.settings")
os.environ.setdefault("DJANGO_CONFIGURATION", "Dev")

import configurations

configurations.setup()

from celery import Celery  # noqa: E402

app = Celery("doorito")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
