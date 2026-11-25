"""WSGI entry point for gunicorn. Refuses to start while database migrations are pending."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings.production")
application = get_wsgi_application()

# Imported after get_wsgi_application(): the app registry must be ready first.
from easy_kitchen.startup import ensure_migrations_applied  # noqa: E402

ensure_migrations_applied()
