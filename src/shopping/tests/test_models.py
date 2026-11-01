import pytest
from shopping.services import create_item, reorder_items


@pytest.mark.django_db
def test_items_are_created_and_ordered(shopping_list):
    milk = create_item(shopping_list, name="Milch", quantity="1 l")
    bread = create_item(shopping_list, name="Brot")
    reorder_items(shopping_list, [bread.id, milk.id])
    assert list(shopping_list.items.values_list("name", flat=True)) == ["Brot", "Milch"]


@pytest.mark.django_db
def test_adding_the_same_item_keeps_one_row_and_shows_different_quantities(shopping_list):
    first = create_item(shopping_list, name="Milch", quantity="1 l")
    same = create_item(shopping_list, name=" milch ", quantity="1 l")
    both = create_item(shopping_list, name="MILCH", quantity="500 ml")

    assert shopping_list.items.count() == 1
    assert same.id == first.id == both.id
    assert both.name == "Milch"
    assert both.quantity == "2 l, 500 ml"


@pytest.mark.django_db
def test_quantities_with_the_same_unit_are_added(shopping_list):
    create_item(shopping_list, name="Milch", quantity="1 l")
    item = create_item(shopping_list, name="Milch", quantity="2 l")
    assert shopping_list.items.count() == 1
    assert item.quantity == "3 l"

    create_item(shopping_list, name="Mehl", quantity="1,5 kg")
    flour = create_item(shopping_list, name="Mehl", quantity="0,5 kg")
    assert flour.quantity == "2 kg"

    create_item(shopping_list, name="Zitronen", quantity="2")
    lemons = create_item(shopping_list, name="Zitronen", quantity="3")
    assert lemons.quantity == "5"


@pytest.mark.django_db
def test_adding_a_checked_item_again_makes_it_active(shopping_list):
    item = create_item(shopping_list, name="Milch", quantity="1 l")
    item.checked = True
    item.save(update_fields=["checked"])

    updated = create_item(shopping_list, name="Milch", quantity="500 ml")

    assert updated.id == item.id
    assert updated.checked is False


@pytest.mark.django_db
def test_reorder_rejects_foreign_item(shopping_list, other_user):
    foreign_list = type(shopping_list).objects.create(user=other_user, title="Privat")
    foreign_item = create_item(foreign_list, name="Geheim")
    with pytest.raises(ValueError):
        reorder_items(shopping_list, [foreign_item.id])
