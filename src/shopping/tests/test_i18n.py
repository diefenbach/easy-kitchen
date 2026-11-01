import pytest
from django.urls import reverse
from django.utils import translation
from rest_framework.authtoken.models import Token
from shopping.models import ShoppingList


@pytest.mark.django_db
def test_interface_is_english_by_default(client, user):
    client.force_login(user)

    response = client.get(reverse("shopping:list"))

    content = response.content.decode()
    assert response.status_code == 200
    assert 'lang="en"' in content
    assert "Shopping lists" in content
    assert "New list" in content
    assert "Einkaufslisten" not in content
    assert reverse("shopping:create") == "/lists/new/"


@pytest.mark.django_db
def test_german_translation_is_available(client, user, shopping_list):
    client.force_login(user)

    with translation.override("de"):
        overview = client.get(reverse("shopping:list"))
    overview_content = overview.content.decode()
    assert 'lang="de"' in overview_content
    assert "Einkaufslisten" in overview_content
    assert "Neue Liste" in overview_content
    assert "Bearbeiten" in overview_content
    assert "Fertig" in overview_content

    with translation.override("de"):
        detail = client.get(reverse("shopping:detail", args=[shopping_list.pk]))
    detail_content = detail.content.decode()
    assert "Einkaufslisten" in detail_content
    assert "Artikel" in detail_content
    assert "Menge" in detail_content
    assert "Hinzufügen" in detail_content
    assert "Erledigte ausblenden" in detail_content

    with translation.override("de"):
        edit = client.get(reverse("shopping:update", args=[shopping_list.pk]))
    edit_content = edit.content.decode()
    assert "Liste bearbeiten" in edit_content
    assert "Titel" in edit_content
    assert "Datum" in edit_content
    assert ">Abbrechen</span>" in edit_content


@pytest.mark.django_db
def test_article_management_uses_the_active_language(client, user):
    client.force_login(user)

    english = client.get(reverse("shopping:articles")).content.decode()
    assert "<h1" in english and "Articles" in english
    assert ">Articles</span>" in client.get(reverse("shopping:list")).content.decode()

    with translation.override("de"):
        german = client.get(reverse("shopping:articles")).content.decode()
        overview = client.get(reverse("shopping:list")).content.decode()
    assert "Artikel" in german
    assert ">Artikel</span>" in overview


@pytest.mark.django_db
def test_login_page_uses_the_active_language(client):
    english = client.get(reverse("login")).content.decode()
    assert "Sign in" in english
    assert "Username" in english

    with translation.override("de"):
        german = client.get(reverse("login")).content.decode()
    assert "Anmelden" in german
    assert "Benutzername" in german


@pytest.mark.django_db
def test_recipe_pages_use_the_active_language(client, user):
    client.force_login(user)

    english = client.get(reverse("shopping:recipes")).content.decode()
    assert "Recipes" in english
    assert "New recipe" in english
    overview = client.get(reverse("shopping:list")).content.decode()
    assert ">Recipes</span>" in overview
    assert f'href="{reverse("shopping:list")}"' in overview
    assert ">Shopping lists</span>" in overview

    with translation.override("de"):
        german = client.get(reverse("shopping:recipes")).content.decode()
        overview = client.get(reverse("shopping:list")).content.decode()
    assert "Rezepte" in german
    assert "Neues Rezept" in german
    assert ">Rezepte</span>" in overview
    assert ">Einkaufslisten</span>" in overview


@pytest.mark.django_db
def test_import_page_uses_the_active_language(client, user):
    client.force_login(user)

    english = client.get(reverse("shopping:import-json")).content.decode()
    assert "Import shopping lists" in english
    assert "Shopping-list JSON" in english

    with translation.override("de"):
        german = client.get(reverse("shopping:import-json")).content.decode()
    assert "Einkaufslisten importieren" in german
    assert "Einkaufslisten-JSON" in german


@pytest.mark.django_db
def test_api_errors_are_english_and_can_be_german(client, user):
    token = Token.objects.create(user=user)
    shopping_list = ShoppingList.objects.create(user=user, title="Week")
    headers = {"HTTP_AUTHORIZATION": f"Token {token.key}"}
    import_url = reverse("shopping-list-import-json")
    reorder_url = reverse("shopping-list-reorder", args=[shopping_list.pk])

    english_import = client.post(import_url, {"title": "nope"}, content_type="application/json", **headers)
    assert english_import.status_code == 400
    assert english_import.json()["detail"] == "Expected a list or {'lists': [...]}."

    with translation.override("de"):
        german_import = client.post(
            import_url,
            {"title": "nope"},
            content_type="application/json",
            **headers,
        )
    assert german_import.json()["detail"] == "Erwartet wird eine Liste oder {'lists': [...]}."

    english_reorder = client.post(reorder_url, {}, content_type="application/json", **headers)
    assert english_reorder.json()["detail"] == "Invalid order."

    with translation.override("de"):
        german_reorder = client.post(
            reorder_url,
            {},
            content_type="application/json",
            **headers,
        )
    assert german_reorder.json()["detail"] == "Ungültige Reihenfolge."
