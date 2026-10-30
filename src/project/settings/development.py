from .base import *  # noqa: F403
from .base import postgres_database_from_environment

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
DATABASES = {"default": postgres_database_from_environment()}
