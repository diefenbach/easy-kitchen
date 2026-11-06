import importlib
from types import SimpleNamespace

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_existing_catalogue_and_references_are_copied_to_each_user():
    old = [("shopping", "0016_department_table")]
    new = [("shopping", "0019_require_department_owner")]
    executor = MigrationExecutor(connection)
    executor.migrate(old)
    try:
        apps = executor.loader.project_state(old).apps
        importlib.import_module("easy_kitchen.migrations.0016_department_table").seed_departments(apps, SimpleNamespace(connection=connection))
        User = apps.get_model("auth", "User")
        Department = apps.get_model("shopping", "Department")
        Article = apps.get_model("shopping", "Article")
        ShoppingList = apps.get_model("shopping", "ShoppingList")
        ShoppingItem = apps.get_model("shopping", "ShoppingItem")
        dairy = Department.objects.get(code="dairy")
        dairy.name = "Chilled products"
        dairy.save()
        Department.objects.create(code="garden", name="Garden", position=22)
        users = [User.objects.create(username=name) for name in ("first", "second", "empty")]
        for user in users[:2]:
            Article.objects.create(user_id=user.pk, name="Milk", department_id=dairy.pk)
            shopping_list = ShoppingList.objects.create(user_id=user.pk, title="Shop")
            ShoppingItem.objects.create(shopping_list_id=shopping_list.pk, name="Milk", department_id=dairy.pk)
            ShoppingItem.objects.create(shopping_list_id=shopping_list.pk, name="Unknown")
        executor = MigrationExecutor(connection)
        executor.migrate(new)
        apps = executor.loader.project_state(new).apps
        Department = apps.get_model("shopping", "Department")
        for user in users:
            assert Department.objects.filter(user_id=user.pk).count() == 22
            assert Department.objects.get(user_id=user.pk, code="dairy").name == "Chilled products"
        for model_name in ("Article", "ShoppingItem"):
            for record in apps.get_model("shopping", model_name).objects.select_related("department"):
                if record.department_id:
                    owner_id = record.user_id if model_name == "Article" else record.shopping_list.user_id
                    assert record.department.user_id == owner_id
                    assert record.department.code == "dairy"
        assert Department.objects.filter(code="dairy").values("pk").distinct().count() == 3
        from django.contrib.auth import get_user_model
        new_user = get_user_model().objects.create_user(username="new-after-migration")
        assert new_user.departments.count() == 21
        assert new_user.departments.get(code="dairy").name == "Dairy products"
        assert not new_user.departments.filter(code="garden").exists()
    finally:
        MigrationExecutor(connection).migrate(new)
