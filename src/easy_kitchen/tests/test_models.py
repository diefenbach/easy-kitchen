import pytest
from easy_kitchen.services import create_item, reorder_items, reorder_shopping_lists


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

    combined = create_item(shopping_list, name="Milch", quantity="2 l")
    assert combined.quantity == "4 l, 500 ml"


@pytest.mark.django_db
def test_only_quantities_with_the_same_unit_are_added(shopping_list):
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

    create_item(shopping_list, name="Äpfel", quantity="5")
    create_item(shopping_list, name="Äpfel", quantity="4")
    create_item(shopping_list, name="Äpfel", quantity="2 Stück")
    apples = create_item(shopping_list, name="Äpfel", quantity="4 Teile")
    assert apples.quantity == "9, 2 Stück, 4 Teile"

    create_item(shopping_list, name="Bananen", quantity="2 Stück")
    bananas = create_item(shopping_list, name="Bananen", quantity="2 Stück")
    assert bananas.quantity == "4 Stück"

    create_item(shopping_list, name="Orangen", quantity="6")
    create_item(shopping_list, name="Orangen", quantity="2 Stück")
    oranges = create_item(shopping_list, name="Orangen", quantity="2")
    assert oranges.quantity == "8, 2 Stück"

    create_item(shopping_list, name="Saft", quantity="2 l")
    juice = create_item(shopping_list, name="Saft", quantity="2 Kartons")
    assert juice.quantity == "2 l, 2 Kartons"

    create_item(shopping_list, name="Müsli", quantity="2 Packungen")
    cereal = create_item(shopping_list, name="Müsli", quantity="2")
    assert cereal.quantity == "2 Packungen, 2"


@pytest.mark.django_db
def test_adding_a_checked_item_again_makes_it_active(shopping_list):
    item = create_item(shopping_list, name="Milch", quantity="1 l")
    item.checked = True
    item.save(update_fields=["checked"])

    updated = create_item(shopping_list, name="Milch", quantity="500 ml")

    assert updated.id == item.id
    assert updated.checked is False


@pytest.mark.django_db
def test_adding_an_item_remembers_one_article_per_user(shopping_list, other_user):
    from easy_kitchen.models import Article, ShoppingList

    create_item(shopping_list, name=" Milch ")
    create_item(shopping_list, name="milch", quantity="1 l")
    other_list = ShoppingList.objects.create(user=other_user, title="Privat")
    create_item(other_list, name="Milch")

    assert list(Article.objects.filter(user=shopping_list.user).values_list("name", flat=True)) == ["Milch"]
    assert list(Article.objects.filter(user=other_user).values_list("name", flat=True)) == ["Milch"]


@pytest.mark.django_db
def test_a_new_list_is_placed_first_and_the_overview_can_be_reordered(user):
    from easy_kitchen.models import ShoppingList

    first = ShoppingList.objects.create(user=user, title="First")
    second = ShoppingList.objects.create(user=user, title="Second")

    assert list(user.shopping_lists.values_list("title", flat=True)) == ["Second", "First"]
    reorder_shopping_lists(user, [first.id, second.id])
    assert list(user.shopping_lists.values_list("title", flat=True)) == ["First", "Second"]


@pytest.mark.django_db
def test_reordering_lists_rejects_a_foreign_list(user, other_user):
    from easy_kitchen.models import ShoppingList

    own = ShoppingList.objects.create(user=user, title="Own")
    foreign = ShoppingList.objects.create(user=other_user, title="Foreign")

    with pytest.raises(ValueError):
        reorder_shopping_lists(user, [own.id, foreign.id])
    assert list(user.shopping_lists.values_list("title", flat=True)) == ["Own"]


@pytest.mark.django_db
def test_reorder_rejects_foreign_item(shopping_list, other_user):
    foreign_list = type(shopping_list).objects.create(user=other_user, title="Privat")
    foreign_item = create_item(foreign_list, name="Geheim")
    with pytest.raises(ValueError):
        reorder_items(shopping_list, [foreign_item.id])
