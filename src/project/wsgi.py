import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "project.settings.production")
application = get_wsgi_application()

from easy_kitchen.startup import ensure_migrations_applied

ensure_migrations_applied()
