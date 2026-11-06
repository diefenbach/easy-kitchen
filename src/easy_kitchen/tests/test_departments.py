import pytest
from django.urls import reverse

from easy_kitchen.api.serializers import ShoppingListSerializer
from easy_kitchen.models import Article, ShoppingItem, ShoppingList
from easy_kitchen.services import create_item, shopping_list_export_data

pytestmark = pytest.mark.django_db


def test_item_inherits_only_its_owners_article_department(shopping_list, other_user):
    Article.objects.create(user=other_user, name="Milk", department="fish")
    own = Article.objects.create(user=shopping_list.user, name="Milk", department="dairy")
    item = create_item(shopping_list, name=" MILK ")
    assert item.department == "dairy"
    own.refresh_from_db()
    assert own.department == "dairy"


def test_department_changes_update_default_but_preserve_other_lists(shopping_list):
    first = create_item(shopping_list, name="Milk", department="dairy")
    second_list = ShoppingList.objects.create(user=shopping_list.user, title="Other")
    second = create_item(second_list, name="Milk", department="fresh")
    first.refresh_from_db()
    assert first.department == "dairy"
    assert second.department == "fresh"
    assert Article.objects.get(user=shopping_list.user, name="Milk").department == "fresh"
    merged = create_item(second_list, name="milk", quantity="2", department="")
    assert merged.pk == second.pk
    assert merged.department == ""
    assert Article.objects.get(user=shopping_list.user, name="Milk").department == ""


def test_grouping_is_ordered_and_has_a_separate_unassigned_group(client, user, shopping_list):
    create_item(shopping_list, name="Unknown", department="")
    create_item(shopping_list, name="Milk", department="dairy")
    create_item(shopping_list, name="Apple", department="produce")
    client.force_login(user)
    html = client.get(reverse("easy_kitchen:detail", args=[shopping_list.pk])).content.decode()
    assert html.index('data-department="produce"') < html.index('data-department="dairy"')
    assert html.index('data-department="dairy"') < html.index('data-department=""')
    assert "Without department" in html


def test_web_create_and_edit_regroup_and_remember(client, user, shopping_list):
    client.force_login(user)
    response = client.post(reverse("easy_kitchen:item-create", args=[shopping_list.pk]),
                           {"name": "Milk", "department": "dairy"}, HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    assert 'data-department="dairy"' in response.content.decode()
    item = shopping_list.items.get()
    response = client.post(reverse("easy_kitchen:item-update", args=[shopping_list.pk, item.pk]),
                           {"name": "Milk", "department": "fresh"}, HTTP_HX_REQUEST="true")
    assert response["HX-Retarget"] == "#items"
    assert 'data-department="fresh"' in response.content.decode()
    assert Article.objects.get(user=user, name="Milk").department == "fresh"
    item.refresh_from_db()
    assert item.department == "fresh"


def test_invalid_department_is_rejected(client, user, shopping_list):
    client.force_login(user)
    response = client.post(reverse("easy_kitchen:item-create", args=[shopping_list.pk]),
                           {"name": "Milk", "department": "invalid"})
    assert response.status_code == 422
    assert not shopping_list.items.exists()
    serializer = ShoppingListSerializer(data={"title": "Bad", "items": [{"name": "Milk", "department": "invalid"}]})
    assert not serializer.is_valid()


def test_departments_survive_json_roundtrip(shopping_list):
    create_item(shopping_list, name="Milk", department="dairy")
    data = shopping_list_export_data(shopping_list)
    assert data["items"][0]["department"] == "dairy"
    serializer = ShoppingListSerializer(data=data)
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["items"][0]["department"] == "dairy"


def test_edit_is_scoped_to_owner(client, other_user, shopping_list):
    item = ShoppingItem.objects.create(shopping_list=shopping_list, name="Milk")
    client.force_login(other_user)
    response = client.post(reverse("easy_kitchen:item-update", args=[shopping_list.pk, item.pk]),
                           {"name": "Milk", "department": "dairy"})
    assert response.status_code == 404


def test_saving_old_list_does_not_reset_article_default(client, user, shopping_list):
    from easy_kitchen.tests.test_list_editor import list_editor_data

    item = create_item(shopping_list, name="Milk", department="dairy")
    user.articles.filter(name="Milk").update(department="fresh")
    client.force_login(user)
    data = list_editor_data(shopping_list, title="Updated title", **{"items-0-department": "dairy"})
    response = client.post(reverse("easy_kitchen:update", args=[shopping_list.pk]), data)
    assert response.status_code == 302
    assert user.articles.get(name="Milk").department == "fresh"
    item.refresh_from_db()
    assert item.department == "dairy"
    data["items-0-department"] = ""
    response = client.post(reverse("easy_kitchen:update", args=[shopping_list.pk]), data)
    assert response.status_code == 302
    assert user.articles.get(name="Milk").department == ""


def test_article_management_saves_department_without_changing_lists(client, user, shopping_list):
    item = create_item(shopping_list, name="Milk", department="dairy")
    article = user.articles.get(name="Milk")
    client.force_login(user)
    response = client.post(reverse("easy_kitchen:article-update", args=[article.pk]),
                           {"name": "Milk", "department": "fresh"})
    assert response.status_code == 302
    article.refresh_from_db()
    item.refresh_from_db()
    assert article.department == "fresh"
    assert item.department == "dairy"


def test_department_labels_are_translated(client, user, shopping_list):
    from django.utils.translation import override

    create_item(shopping_list, name="Milk", department="dairy")
    client.force_login(user)
    with override("de"):
        html = client.get(reverse("easy_kitchen:detail", args=[shopping_list.pk])).content.decode()
    for label in ["Abteilung", "Milchprodukte", "Ohne Abteilung", "Öl &amp; Soßen", "Schreibwaren"]:
        assert label in html


def test_mcp_item_department_is_saved_and_returned(user, shopping_list):
    from mcp.server.mcpserver.exceptions import ToolError
    from rest_framework.authtoken.models import Token
    from easy_kitchen.mcp_server import add_item_to_list, list_shopping_lists
    from easy_kitchen.tests.test_mcp import authorization_context

    ctx = authorization_context(Token.objects.create(user=user))
    payload = add_item_to_list(name="Milk", department="dairy", list_id=shopping_list.pk, ctx=ctx)
    assert payload["department"] == "dairy"
    assert list_shopping_lists(ctx)[0]["items"][0]["department"] == "dairy"
    with pytest.raises(ToolError, match="Invalid department"):
        add_item_to_list(name="Milk", department="invalid", list_id=shopping_list.pk, ctx=ctx)
    assert shopping_list.items.get().department == "dairy"


@pytest.mark.parametrize("language, expected", [
    ("en", ["Baby", "Baking ingredients", "Bread", "Breakfast", "Canned food", "Cleaning products",
            "Cosmetics & personal care", "Dairy products", "Drinks", "Fish", "Fresh food", "Frozen food",
            "Fruit & vegetables", "Household goods", "Meat & sausages", "Oil & sauces", "Pasta & rice",
            "Pet supplies", "Spices", "Stationery", "Sweets & snacks"]),
    ("de", ["Baby", "Backzutaten", "Brot", "Fisch", "Fleisch & Wurst", "Frischwaren", "Frühstück",
            "Getränke", "Gewürze", "Haushaltswaren", "Konserven", "Kosmetik & Körperpflege",
            "Milchprodukte", "Nudeln & Reis", "Obst & Gemüse", "Öl & Soßen", "Reinigungsmittel",
            "Schreibwaren", "Süßigkeiten & Snacks", "Tiefkühlwaren", "Tierbedarf"]),
])
def test_department_selects_sort_by_the_active_language(user, shopping_list, language, expected):
    from django.utils.translation import override
    from easy_kitchen.forms import ArticleEditorForm, ArticleForm, ShoppingItemEditorFormSet, ShoppingItemForm
    from easy_kitchen.templatetags.departments import department_choices

    with override(language):
        fields = [ShoppingItemForm().fields["department"], ArticleEditorForm().fields["department"],
                  ArticleForm(user=user).fields["department"],
                  ShoppingItemEditorFormSet(instance=shopping_list).empty_form.fields["department"]]
        for choices in [*[field.choices for field in fields], department_choices()]:
            options = [(value, str(label)) for value, label in choices]
            assert options[0][0] == ""
            assert [label for value, label in options[1:]] == expected
