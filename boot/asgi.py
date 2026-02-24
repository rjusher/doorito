"""
ASGI config for Doorito.

Exposes the ASGI callable as a module-level variable named ``application``.
"""

import os

from dotenv import load_dotenv

load_dotenv()

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "boot.settings")
os.environ.setdefault("DJANGO_CONFIGURATION", "Production")

from configurations.asgi import get_asgi_application

application = get_asgi_application()
