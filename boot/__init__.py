"""
Django project initialization for Doorito.

Exports celery_app so that Celery is loaded when Django starts (required by
django-configurations). The celery app is configured in boot/celery.py.
"""

from .celery import app as celery_app

__all__ = ("celery_app",)
