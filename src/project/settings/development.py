import os

from .base import *  # noqa: F403
from .base import postgres_database_from_environment

DEBUG = True
ALLOWED_HOSTS = [
    host.strip() for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if host.strip()
]
CSRF_TRUSTED_ORIGINS = [
    origin.strip() for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if origin.strip()
]
DATABASES = {"default": postgres_database_from_environment()}
