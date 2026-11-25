import importlib
import json
import re

import pytest
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse

from easy_kitchen.tests.test_settings import _production_environment

BACKEND = "project.storage.HashedStaticFilesStorage"


def test_production_hashes_static_file_names(monkeypatch):
    _production_environment(monkeypatch)
    production = importlib.reload(importlib.import_module("project.settings.production"))

    assert production.STORAGES["staticfiles"]["BACKEND"] == BACKEND


@pytest.fixture
def collected(tmp_path, settings):
    settings.STATIC_ROOT = tmp_path
    with override_settings(STORAGES={**settings.STORAGES, "staticfiles": {"BACKEND": BACKEND}}):
        call_command("collectstatic", interactive=False, verbosity=0)
        yield tmp_path, json.loads((tmp_path / "staticfiles.json").read_text())["paths"]


def test_collectstatic_hashes_names_and_rewrites_module_imports(collected):
    root, paths = collected

    hashed = paths["easy_kitchen/easykitchen.js"]
    assert re.fullmatch(r"easy_kitchen/easykitchen\.[0-9a-f]{12}\.js", hashed)
    list_detail = (root / paths["easy_kitchen/list-detail.js"]).read_text()
    assert f'from "./{hashed.rsplit("/", 1)[1]}"' in list_detail
    assert 'from "./easykitchen.js"' not in list_detail


@pytest.mark.django_db
def test_pages_link_hashed_files(collected, client, user):
    _root, paths = collected

    with override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.InMemoryStorage"}, "staticfiles": {"BACKEND": BACKEND}}):
        login = client.get(reverse("account_login")).content.decode()
        client.force_login(user)
        page = client.get("/").content.decode()

    css = paths["easy_kitchen/vendor/bootstrap/css/bootstrap.min.css"]
    assert f"/static/{css}" in page
    assert f"/static/{css}" in login
