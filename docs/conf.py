"""Sphinx configuration for the EasyKitchen documentation on Read the Docs."""

from __future__ import annotations

import tomllib
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_PYPROJECT = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

project = "EasyKitchen"
author = "Kai Diefenbach"
copyright = "2026, Kai Diefenbach"
release = _PYPROJECT["project"]["version"]
version = release

extensions = [
    "myst_parser",
    "sphinx_rtd_theme",
]

source_suffix = {
    ".md": "markdown",
    ".rst": "restructuredtext",
}

myst_enable_extensions = [
    "colon_fence",
    "deflist",
]
myst_heading_anchors = 3

exclude_patterns = ["_build", "chatgpt", "Thumbs.db", ".DS_Store"]

templates_path = ["_templates"]
html_static_path = ["_static"]
html_theme = "sphinx_rtd_theme"
html_logo = "_static/logo.png"
html_title = "EasyKitchen"
html_context = {
    "display_github": True,
    "github_user": "diefenbach",
    "github_repo": "easy-kitchen",
    "github_version": "main",
    "conf_py_path": "/docs/",
}

language = "en"
