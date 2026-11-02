import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import SRC_DIR, postgres_database_from_environment


def required(name):
    value = os.environ.get(name)
    if not value:
        raise ImproperlyConfigured(f"{name} must be set in production.")
    return value


DEBUG = False
SECRET_KEY = required("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = [host.strip() for host in required("DJANGO_ALLOWED_HOSTS").split(",") if host.strip()]
CSRF_TRUSTED_ORIGINS = [
    origin.strip() for origin in required("DJANGO_CSRF_TRUSTED_ORIGINS").split(",") if origin.strip()
]
for database_setting in ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_HOST"):
    required(database_setting)
DATABASES = {"default": postgres_database_from_environment()}
STATIC_ROOT = SRC_DIR / "staticfiles"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
