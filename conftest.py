"""Restore seeded reference data after transaction tests flush the database."""
import importlib

import pytest


@pytest.fixture(autouse=True)
def department_catalog(request):
    uses_database = request.node.get_closest_marker("django_db") or any(
        fixture in request.fixturenames for fixture in ("db", "transactional_db", "live_server")
    )
    if not uses_database:
        return
    request.getfixturevalue("db")
    from easy_kitchen.models import Department

    if not Department.objects.exists():
        migration = importlib.import_module("easy_kitchen.migrations.0016_department_table")
        Department.objects.bulk_create([
            Department(code=code, name=name, position=position)
            for position, (code, name) in enumerate(migration.INITIAL_DEPARTMENTS, start=1)
        ])
