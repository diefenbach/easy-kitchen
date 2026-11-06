import importlib

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_department_migration_preserves_every_assignment_and_is_reversible():
    old = [("shopping", "0015_article_department_shoppingitem_department")]
    new = [("shopping", "0016_department_table")]
    executor = MigrationExecutor(connection)
    executor.migrate(old)
    try:
        apps = executor.loader.project_state(old).apps
        user = apps.get_model("auth", "User").objects.create(username="migration-owner")
        shopping_list = apps.get_model("shopping", "ShoppingList").objects.create(user_id=user.pk, title="Migration")
        catalog = importlib.import_module("easy_kitchen.migrations.0016_department_table").INITIAL_DEPARTMENTS
        codes = [code for code, name in catalog] + [""]
        for code in codes:
            apps.get_model("shopping", "Article").objects.create(user_id=user.pk, name=code or "Unassigned", department=code)
            apps.get_model("shopping", "ShoppingItem").objects.create(shopping_list_id=shopping_list.pk, name=code or "Unassigned", department=code)
        executor = MigrationExecutor(connection)
        executor.migrate(new)
        apps = executor.loader.project_state(new).apps
        assert apps.get_model("shopping", "Department").objects.count() == 21
        for model_name in ("Article", "ShoppingItem"):
            for record in apps.get_model("shopping", model_name).objects.all():
                if record.name == "Unassigned":
                    assert record.department_id is None
                else:
                    assert record.department.code == record.name
        executor = MigrationExecutor(connection)
        executor.migrate(old)
        apps = executor.loader.project_state(old).apps
        for model_name in ("Article", "ShoppingItem"):
            assert set(apps.get_model("shopping", model_name).objects.values_list("department", flat=True)) == set(codes)
    finally:
        MigrationExecutor(connection).migrate(new)
