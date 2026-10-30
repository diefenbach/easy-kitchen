from .base import *  # noqa: F403
from .base import SRC_DIR

SECRET_KEY = "test-secret-key"
DEBUG = False
LANGUAGE_CODE = "en"
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": SRC_DIR / "test.sqlite3"}}
STORAGES = {"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}
