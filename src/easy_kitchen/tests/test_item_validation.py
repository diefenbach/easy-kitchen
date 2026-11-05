import pytest
from django.urls import reverse
from django.utils import translation

from easy_kitchen.models import ShoppingItem


@pytest.mark.django_db
@pytest.mark.parametrize("editing", [False, True])
def test_item_validation_response_keeps_values_and_marks_422(client, user, shopping_list, editing):
    client.force_login(user)
    item = ShoppingItem.objects.create(shopping_list=shopping_list, name="Milk", quantity="1 l")
    url = reverse("easy_kitchen:item-update", args=[shopping_list.pk, item.pk]) if editing else reverse("easy_kitchen:item-create", args=[shopping_list.pk])
    response = client.post(url, {"name": "", "quantity": "2 l"}, HTTP_HX_REQUEST="true")
    assert response.status_code == 422
    assert response["X-Item-Form"] == "true"
    content = response.content.decode()
    assert "This field is required." in content
    assert 'value="2 l"' in content
    if not editing:
        assert response["HX-Retarget"] == "#item-form"
        assert response["HX-Reswap"] == "innerHTML"
    item.refresh_from_db()
    assert item.name == "Milk"
    assert item.quantity == "1 l"


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["en", "de"])
def test_browser_save_error_message_is_translated(client, user, shopping_list, language):
    client.force_login(user)
    with translation.override(language):
        content = client.get(reverse("easy_kitchen:detail", args=[shopping_list.pk])).content.decode()
    message = "Your changes could not be saved." if language == "en" else "Deine Änderungen konnten nicht gespeichert werden."
    assert message in content
