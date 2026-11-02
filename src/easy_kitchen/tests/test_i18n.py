import pytest
from django.urls import reverse
from django.utils import translation
from rest_framework.authtoken.models import Token
from easy_kitchen.models import ShoppingList


@pytest.mark.django_db
def test_interface_is_english_by_default(client, user):
    client.force_login(user)

    response = client.get(reverse("easy_kitchen:home"))

    content = response.content.decode()
    assert response.status_code == 200
    assert 'lang="en"' in content
    assert "Shopping lists" in content
    assert "See all lists" in content
    assert "See all recipes" in content
    assert "Overview" in content
    assert 'aria-label="kai"' in content
    assert "New list" in content
    assert "New recipe" in content
    assert "Einkaufslisten" not in content
    assert "Übersicht" not in content
    assert "Alle Listen ansehen" not in content
    assert reverse("easy_kitchen:list") == "/lists/"
    assert reverse("easy_kitchen:create") == "/lists/new/"


@pytest.mark.django_db
def test_german_translation_is_available(client, user, shopping_list):
    client.force_login(user)

    with translation.override("de"):
        home = client.get(reverse("easy_kitchen:home"))
        overview = client.get(reverse("easy_kitchen:list"))
    home_content = home.content.decode()
    overview_content = overview.content.decode()
    assert 'lang="de"' in home_content
    assert "Alle Listen ansehen" in home_content
    assert "Alle Rezepte ansehen" in home_content
    assert "Neue Liste" in home_content
    assert "Neues Rezept" in home_content
    assert "Übersicht" in home_content
    assert 'aria-label="kai"' in home_content
    assert "Einkaufslisten" in overview_content
    assert "Neue Liste" in overview_content
    assert "Bearbeiten" in overview_content
    assert "Fertig" in overview_content

    with translation.override("de"):
        detail = client.get(reverse("easy_kitchen:detail", args=[shopping_list.pk]))
    detail_content = detail.content.decode()
    assert "Einkaufslisten" in detail_content
    assert "Artikel" in detail_content
    assert "Menge" in detail_content
    assert "Hinzufügen" in detail_content
    assert "Erledigte ausblenden" in detail_content

    with translation.override("de"):
        edit = client.get(reverse("easy_kitchen:update", args=[shopping_list.pk]))
    edit_content = edit.content.decode()
    assert "Liste bearbeiten" in edit_content
    assert "Titel" in edit_content
    assert "Datum" in edit_content
    assert ">Abbrechen</span>" in edit_content


@pytest.mark.django_db
def test_article_management_uses_the_active_language(client, user):
    client.force_login(user)

    english = client.get(reverse("easy_kitchen:articles")).content.decode()
    assert "<h1" in english and "Articles" in english
    assert "These articles are offered in the dropdown when you add an item to a shopping list." in english
    assert ">Edit articles</span>" in client.get(reverse("easy_kitchen:list")).content.decode()

    with translation.override("de"):
        german = client.get(reverse("easy_kitchen:articles")).content.decode()
        overview = client.get(reverse("easy_kitchen:list")).content.decode()
    assert "Artikel" in german
    assert "Diese Artikel werden im Dropdown angeboten, wenn du einer Einkaufsliste einen Eintrag hinzufügst." in german
    assert ">Artikel bearbeiten</span>" in overview


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

    english = client.get(reverse("easy_kitchen:recipes")).content.decode()
    assert "Recipes" in english
    assert "New recipe" in english
    overview = client.get(reverse("easy_kitchen:list")).content.decode()
    assert ">Recipes</span>" in overview
    assert f'href="{reverse("easy_kitchen:list")}"' in overview
    assert ">Shopping lists</span>" in overview

    with translation.override("de"):
        german = client.get(reverse("easy_kitchen:recipes")).content.decode()
        overview = client.get(reverse("easy_kitchen:list")).content.decode()
    assert "Rezepte" in german
    assert "Neues Rezept" in german
    assert ">Rezepte</span>" in overview
    assert ">Einkaufslisten</span>" in overview


@pytest.mark.django_db
def test_import_page_uses_the_active_language(client, user):
    client.force_login(user)

    english = client.get(reverse("easy_kitchen:import-json")).content.decode()
    assert "Import JSON" in english
    assert "Paste one shopping list, one recipe, or several of either." in english
    assert "A title, a date, and items. Each item has a name and a quantity." in english
    assert "A title. Add ingredients, steps, or nutrition when you have them." in english

    with translation.override("de"):
        german = client.get(reverse("easy_kitchen:import-json")).content.decode()
    assert "JSON importieren" in german
    assert "Füge eine Einkaufsliste, ein Rezept oder mehrere davon ein." in german
    assert "Ein Titel, ein Datum und Artikel." in german
    assert "Zutaten, Schritte oder Nährwerte kannst du ergänzen." in german


@pytest.mark.django_db
def test_export_page_uses_the_active_language(client, user):
    client.force_login(user)

    english = client.get(reverse("easy_kitchen:export-json")).content.decode()
    assert "Export JSON" in english
    assert "Choose the shopping lists and recipes to download as JSON." in english
    assert ">Export JSON</span>" in client.get(reverse("easy_kitchen:list")).content.decode()

    with translation.override("de"):
        german = client.get(reverse("easy_kitchen:export-json")).content.decode()
        overview = client.get(reverse("easy_kitchen:list")).content.decode()
    assert "JSON exportieren" in german
    assert "Wähle die Einkaufslisten und Rezepte, die du als JSON herunterladen willst." in german
    assert ">JSON exportieren</span>" in overview


@pytest.mark.django_db
def test_list_and_recipe_status_messages_use_the_active_language(client, user):
    client.force_login(user)

    with translation.override("de"):
        created_list = client.post(
            reverse("easy_kitchen:create"),
            {"title": "Markt", "date": "2026-11-01"},
            follow=True,
        )
        created_recipe = client.post(
            reverse("easy_kitchen:recipe-create"),
            {"title": "Suppe", "description": "", "image_url": ""},
            follow=True,
        )
    assert "Einkaufsliste erstellt." in created_list.content.decode()
    assert "Rezept erstellt." in created_recipe.content.decode()


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
