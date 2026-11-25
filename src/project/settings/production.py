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
DEFAULT_FROM_EMAIL = required("DJANGO_DEFAULT_FROM_EMAIL")
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = required("EMAIL_HOST")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "true").lower() == "true"
EMAIL_USE_SSL = os.environ.get("EMAIL_USE_SSL", "false").lower() == "true"
SERVER_EMAIL = DEFAULT_FROM_EMAIL
ACCOUNT_DEFAULT_HTTP_PROTOCOL = "https"
# Without this, Django sends errors only by mail to ADMINS (empty) and shows nothing: log warnings and errors,
# with traceback, to stderr, where `docker logs kitchen` shows them next to gunicorn's output.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "[{asctime}] {levelname} {name}: {message}", "style": "{"}},
    "handlers": {"stderr": {"class": "logging.StreamHandler", "stream": "ext://sys.stderr", "formatter": "plain"}},
    "root": {"handlers": ["stderr"], "level": "WARNING"},
    # Django's default config sets its logger to INFO; keep it at WARNING like the rest.
    "loggers": {"django": {"level": "WARNING"}},
}
