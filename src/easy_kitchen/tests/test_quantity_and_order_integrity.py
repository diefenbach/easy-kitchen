from datetime import date

import pytest

from easy_kitchen.services import (
    create_item, create_recipe, create_shopping_list, reorder_items, reorder_recipe_lines,
)


@pytest.mark.django_db
@pytest.mark.parametrize("quantity", ["1/2 l", "1 1/2 cups", "1-2 pieces", "1–2 pieces"])
def test_unsupported_amounts_are_preserved_across_repeated_merges(user, quantity):
    shopping_list = create_shopping_list(user, title="Shop", date=date.today())
    for count in range(1, 4):
        item = create_item(shopping_list, name="Ingredient", quantity=quantity)
        assert item.quantity == ", ".join([quantity] * count)


@pytest.mark.django_db
def test_merged_quantity_overflow_does_not_change_item_or_article(user):
    shopping_list = create_shopping_list(user, title="Shop", date=date.today())
    item = create_item(shopping_list, name="Milk", quantity="1 " + "a" * 98, checked=True)
    with pytest.raises(ValueError, match="100"):
        create_item(shopping_list, name="Milk", quantity="1 " + "b" * 98)
    item.refresh_from_db()
    assert item.quantity == "1 " + "a" * 98
    assert item.checked is True
    item.full_clean()


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["items", "ingredient", "step"])
def test_reordering_requires_all_children_and_preserves_existing_positions(user, kind):
    if kind == "items":
        parent = create_shopping_list(user, title="Shop", date=date.today(), items=[{"name": "A"}, {"name": "B"}])
        manager = parent.items
        def reorder(ids):
            return reorder_items(parent, ids)
    else:
        parent = create_recipe(user, title="Recipe", ingredients=[{"name": "A"}, {"name": "B"}], steps=["A", "B"])
        manager = parent.ingredients if kind == "ingredient" else parent.steps
        def reorder(ids):
            return reorder_recipe_lines(parent, kind, ids)
    original = list(manager.values_list("pk", "position"))
    ids = [pk for pk, _ in original]
    for invalid in [[], [ids[-1]], [ids[0], ids[0]], [ids[0], 9999999]]:
        with pytest.raises(ValueError):
            reorder(invalid)
        assert list(manager.values_list("pk", "position")) == original
    reorder(ids[::-1])
    assert list(manager.values_list("pk", flat=True)) == ids[::-1]

