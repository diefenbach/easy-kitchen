from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier

import pytest
from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, connections
from django.db.models.query import QuerySet

from easy_kitchen.models import Article, ShoppingItem, ShoppingList
from easy_kitchen.services import create_item, create_shopping_list, remember_article

pytestmark = [pytest.mark.django_db(transaction=True)]


def postgres_only():
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row locks and varchar constraints")


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("same_list", [False, True])
def test_simultaneous_additions_preserve_quantities_and_article_uniqueness(existing, same_list):
    postgres_only()
    user = get_user_model().objects.create_user(username="concurrent")
    lists = [create_shopping_list(user, title=str(i), date=date.today()) for i in range(2)]
    if existing:
        for shopping_list in lists:
            create_item(shopping_list, name="Milk", quantity="1 l")
    barrier = Barrier(2)

    def add(index):
        close_old_connections()
        try:
            target = ShoppingList.objects.get(pk=lists[0 if same_list else index].pk)
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '10s'")
            barrier.wait(timeout=10)
            create_item(target, name="Milk", quantity="1 l")
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(add, index) for index in range(2)]
        for future in futures:
            future.result(timeout=20)
    assert Article.objects.filter(user=user, name__iexact="Milk").count() == 1
    if same_list:
        assert lists[0].items.count() == 1
        assert lists[0].items.get().quantity == ("3 l" if existing else "2 l")
    else:
        for shopping_list in lists:
            assert shopping_list.items.count() == 1
            assert shopping_list.items.get().quantity == ("2 l" if existing else "1 l")


def test_postgres_quantity_overflow_is_validation_error_and_rolls_back():
    postgres_only()
    user = get_user_model().objects.create_user(username="quantity-limit")
    shopping_list = create_shopping_list(user, title="Test", date=date.today())
    item = create_item(shopping_list, name="Milk", quantity="1 " + "a" * 98)
    with pytest.raises(ValueError, match="100"):
        create_item(shopping_list, name="Milk", quantity="1 " + "b" * 98)
    item.refresh_from_db()
    assert item.quantity == "1 " + "a" * 98
    assert ShoppingItem.objects.count() == 1
    item.full_clean()


def test_simultaneous_recipe_partial_updates_preserve_both_changes():
    from easy_kitchen.services import create_recipe, update_owned_recipe

    postgres_only()
    user = get_user_model().objects.create_user(username="recipe-race")
    recipe = create_recipe(user, title="Soup", calories=100)
    barrier = Barrier(2)

    def update(changes):
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '10s'")
            barrier.wait(timeout=10)
            update_owned_recipe(user, recipe_id=recipe.pk, changes=changes)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(update, {"title": "Dinner"}), pool.submit(update, {"fat": 65})]
        for future in futures:
            future.result(timeout=20)
    recipe.refresh_from_db()
    assert recipe.title == "Dinner" and recipe.fat == 65 and recipe.calories == 100


def test_simultaneous_first_article_creation_recovers_unique_conflict(monkeypatch):
    postgres_only()
    user = get_user_model().objects.create_user(username="article-race")
    barrier = Barrier(2)
    original = QuerySet.create

    def synchronized_create(queryset, **kwargs):
        if queryset.model is Article:
            barrier.wait(timeout=10)
        return original(queryset, **kwargs)

    monkeypatch.setattr(QuerySet, "create", synchronized_create)

    def remember():
        close_old_connections()
        try:
            return remember_article(user, "Milk").pk
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(remember) for _ in range(2)]
        ids = [future.result(timeout=20) for future in futures]
    assert ids[0] == ids[1]
    assert Article.objects.filter(user=user).count() == 1


def test_persistent_connection_recovers_after_backend_termination():
    from project.settings.base import postgres_database_from_environment

    postgres_only()
    recovered = connection.copy(alias="recovery_test")
    terminator = connection.copy(alias="termination_test")
    recovered.settings_dict.update({
        "CONN_MAX_AGE": 600,
        "CONN_HEALTH_CHECKS": postgres_database_from_environment()["CONN_HEALTH_CHECKS"],
    })
    try:
        with recovered.cursor() as cursor:
            cursor.execute("SELECT pg_backend_pid()")
            original_pid = cursor.fetchone()[0]
        # Terminate only the connection created by this test, not application connections.
        with terminator.cursor() as cursor:
            cursor.execute("SELECT pg_terminate_backend(%s)", [original_pid])
            assert cursor.fetchone()[0] is True
        # Django runs this at request boundaries before reusing a persistent connection.
        recovered.close_if_unusable_or_obsolete()
        with recovered.cursor() as cursor:
            cursor.execute("SELECT pg_backend_pid(), 1")
            new_pid, result = cursor.fetchone()
        assert new_pid != original_pid
        assert result == 1
    finally:
        recovered.close()
        terminator.close()
