import pytest
from shopping.services import create_item, reorder_items


@pytest.mark.django_db
def test_items_are_created_and_ordered(shopping_list):
    milk = create_item(shopping_list, name="Milch", quantity="1 l")
    bread = create_item(shopping_list, name="Brot")
    reorder_items(shopping_list, [bread.id, milk.id])
    assert list(shopping_list.items.values_list("name", flat=True)) == ["Brot", "Milch"]


@pytest.mark.django_db
def test_reorder_rejects_foreign_item(shopping_list, other_user):
    foreign_list = type(shopping_list).objects.create(user=other_user, title="Privat")
    foreign_item = create_item(foreign_list, name="Geheim")
    with pytest.raises(ValueError):
        reorder_items(shopping_list, [foreign_item.id])
