"""Settings used to collect static assets while building the Cloud Run image."""

from .base import *  # noqa: F403
from .base import SRC_DIR


DEBUG = False
STATIC_ROOT = SRC_DIR / "staticfiles"
