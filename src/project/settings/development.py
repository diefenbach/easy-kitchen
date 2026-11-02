import os

from .base import *  # noqa: F403
from .base import postgres_database_from_environment


def _allowed_hosts_from_environment():
    hosts = []
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(","):
        host = host.strip()
        if not host:
            continue
        if host.count(":") == 1 and host.rsplit(":", 1)[1].isdigit():
            host = host.rsplit(":", 1)[0]
        hosts.append(host)
    return hosts


DEBUG = True
ALLOWED_HOSTS = _allowed_hosts_from_environment() or ["localhost", "127.0.0.1"]
CSRF_TRUSTED_ORIGINS = [
    origin.strip() for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if origin.strip()
]
DATABASES = {"default": postgres_database_from_environment()}
