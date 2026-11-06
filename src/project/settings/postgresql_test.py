"""Opt-in PostgreSQL tests; this filename is excluded from pytest discovery."""

from .test import *  # noqa: F403
from .base import postgres_database_from_environment

DATABASES = {"default": postgres_database_from_environment()}
DATABASES["default"]["CONN_MAX_AGE"] = 0
