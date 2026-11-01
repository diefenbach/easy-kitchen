import io
import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone, translation
from PIL import Image
from rest_framework.authtoken.models import Token
from easy_kitchen.models import Recipe, ShoppingList
from easy_kitchen.services import add_recipe_ingredients_to_list, create_recipe, reorder_recipes


def png_upload():
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), "red").save(buffer, format="PNG")
    return SimpleUploadedFile("pancakes.png", buffer.getvalue(), content_type="image/png")


@pytest.mark.django_db
def test_recipe_belongs_to_its_user_and_keeps_line_order(user, other_user):
    recipe = create_recipe(
        user,
        title="  Pancakes  ",
        description="Sunday breakfast",
        image_url="https://example.com/pancakes.jpg",
        ingredients=[{"name": "Flour", "quantity": "200 g"}, {"name": "Eggs", "quantity": "2"}],
        steps=[{"text": "Mix"}, {"text": "Fry"}],
    )

    assert recipe.user == user
    assert recipe.title == "Pancakes"
    assert list(recipe.ingredients.values_list("name", "quantity")) == [("Flour", "200 g"), ("Eggs", "2")]
    assert list(recipe.steps.values_list("text", flat=True)) == ["Mix", "Fry"]
    assert recipe.picture_url == "https://example.com/pancakes.jpg"
    assert recipe.calories is None
    assert recipe.protein is None
    assert recipe.preparation_minutes is None
    assert Recipe.objects.filter(user=other_user).count() == 0


@pytest.mark.django_db
def test_recipe_stores_calories_protein_and_preparation_time(client, user):
    client.force_login(user)

    response = client.post(
        reverse("easy_kitchen:recipe-create"),
        {
            "title": "Pancakes",
            "description": "",
            "image_url": "",
            "calories": "450",
            "protein": "12",
            "preparation_minutes": "25",
        },
    )

    recipe = Recipe.objects.get(user=user, title="Pancakes")
    assert response.status_code == 302
    assert recipe.calories == 450
    assert recipe.protein == 12
    assert recipe.preparation_minutes == 25
    detail = client.get(reverse("easy_kitchen:recipe-detail", args=[recipe.pk])).content.decode()
    assert "450 kcal" in detail
    assert "12 g protein" in detail
    assert "25 min" in detail
    overview = client.get(reverse("easy_kitchen:recipes")).content.decode()
    assert "450 kcal" in overview
    assert "12 g protein" in overview
    assert "25 min" in overview
    assert 'class="card-footer list-card-date"' in overview
    assert 'class="recipe-card-facts mb-0"' in overview
    assert "recipe-card-facts" not in detail
    assert "0 ingredients" not in overview

    with translation.override("de"):
        german = client.get(reverse("easy_kitchen:recipe-detail", args=[recipe.pk])).content.decode()
        form = client.get(reverse("easy_kitchen:recipe-update", args=[recipe.pk])).content.decode()
    assert "12 g Proteine" in german
    assert "25 Min." in german
    assert "Kalorien (kcal)" in form
    assert "Proteine (g)" in form
    assert "Zubereitungszeit (Min.)" in form

    plain = create_recipe(user, title="Soup")
    plain_detail = client.get(reverse("easy_kitchen:recipe-detail", args=[plain.pk])).content.decode()
    assert "recipe-facts" not in plain_detail
    assert "kcal" not in plain_detail
    overview = client.get(reverse("easy_kitchen:recipes")).content.decode()
    plain_card = overview.split(f'data-list-id="{plain.pk}"', 1)[1].split("data-list-id=", 1)[0]
    assert "recipe-facts" not in plain_card
    assert "list-card-date" not in plain_card
    assert "kcal" not in plain_card

    timed = create_recipe(user, title="Salad", preparation_minutes=10)
    timed_detail = client.get(reverse("easy_kitchen:recipe-detail", args=[timed.pk])).content.decode()
    assert "10 min" in timed_detail
    assert "kcal" not in timed_detail
    assert "g protein" not in timed_detail


@pytest.mark.django_db
def test_adding_a_recipe_to_a_list_puts_the_amount_in_the_quantity(user):
    recipe = create_recipe(
        user,
        title="Pancakes",
        ingredients=[
            {"name": "Flour", "quantity": "200 g"},
            {"name": "Eggs", "quantity": "2"},
            {"name": "Salt"},
            {"name": "Milk", "quantity": "1,5 l"},
        ],
    )
    shopping_list = ShoppingList.objects.create(user=user, title="Weekend", date=timezone.localdate())

    add_recipe_ingredients_to_list(recipe, shopping_list)

    assert list(shopping_list.items.values_list("name", "quantity")) == [
        ("Flour", "200 g"),
        ("Eggs", "2"),
        ("Salt", ""),
        ("Milk", "1,5 l"),
    ]


@pytest.mark.django_db
def test_a_new_recipe_is_placed_first_and_the_overview_can_be_reordered(client, user, other_user):
    first = create_recipe(user, title="First")
    second = create_recipe(user, title="Second")
    foreign = create_recipe(other_user, title="Foreign")
    assert list(user.recipes.values_list("title", flat=True)) == ["Second", "First"]

    client.force_login(user)
    overview = client.get(reverse("easy_kitchen:recipes")).content.decode()
    assert 'data-card-reorder' in overview
    assert 'aria-label="Move"' in overview
    assert ">Move</span>" not in overview
    assert f'{reverse("easy_kitchen:recipe-update", args=[second.pk])}?return_to=overview' in overview
    assert 'class="dropdown-item" href="/import/" aria-label="Import JSON"' in overview
    assert 'class="btn btn-outline-secondary" aria-label="Import JSON"' not in overview
    assert "bi-plus-lg" in overview
    assert "New recipe" in overview
    rejected = client.post(
        reverse("easy_kitchen:recipe-reorder"),
        json.dumps({"recipe_ids": [first.pk, foreign.pk]}),
        content_type="application/json",
    )
    assert rejected.status_code == 400
    reordered = client.post(
        reverse("easy_kitchen:recipe-reorder"),
        json.dumps({"recipe_ids": [first.pk, second.pk]}),
        content_type="application/json",
    )
    assert reordered.status_code == 302
    assert list(user.recipes.values_list("title", flat=True)) == ["First", "Second"]
    reorder_recipes(user, [second.pk, first.pk])
    assert list(user.recipes.values_list("title", flat=True)) == ["Second", "First"]


@pytest.mark.django_db
def test_recipe_without_a_picture_uses_the_placeholder_and_the_card_opens_from_the_image(client, user):
    plain = create_recipe(user, title="Pancakes")
    pictured = create_recipe(user, title="Soup", image_url="https://example.com/soup.jpg")
    client.force_login(user)

    overview = client.get(reverse("easy_kitchen:recipes")).content.decode()
    plain_card = overview.split(f'data-list-id="{plain.pk}"', 1)[1].split("data-list-id=", 1)[0]
    pictured_card = overview.split(f'data-list-id="{pictured.pk}"', 1)[1].split("data-list-id=", 1)[0]
    assert 'class="card h-100 shadow-sm list-card position-relative"' in plain_card
    assert 'src="/static/easy_kitchen/recipe-placeholder.svg"' in plain_card
    assert 'src="https://example.com/soup.jpg"' in pictured_card
    assert "recipe-placeholder.svg" not in pictured_card

    detail = client.get(reverse("easy_kitchen:recipe-detail", args=[plain.pk])).content.decode()
    assert 'class="recipe-picture" src="/static/easy_kitchen/recipe-placeholder.svg"' in detail


@pytest.mark.django_db
def test_edit_from_overview_returns_to_recipe_overview(client, user):
    recipe = create_recipe(user, title="Pancakes")
    client.force_login(user)

    response = client.post(
        f'{reverse("easy_kitchen:recipe-update", args=[recipe.pk])}?return_to=overview',
        {"title": "Pfannkuchen", "description": "", "image_url": ""},
    )

    assert response.url == reverse("easy_kitchen:recipes")


@pytest.mark.django_db
def test_edit_from_detail_returns_to_recipe_detail(client, user):
    recipe = create_recipe(user, title="Pancakes")
    client.force_login(user)

    response = client.post(
        reverse("easy_kitchen:recipe-update", args=[recipe.pk]),
        {"title": "Pfannkuchen", "description": "", "image_url": ""},
    )

    assert response.url == reverse("easy_kitchen:recipe-detail", args=[recipe.pk])


@pytest.mark.django_db
def test_edit_from_overview_cancels_to_recipe_overview(client, user):
    recipe = create_recipe(user, title="Pancakes")
    client.force_login(user)

    response = client.get(f'{reverse("easy_kitchen:recipe-update", args=[recipe.pk])}?return_to=overview')

    content = response.content.decode()
    assert f'href="{reverse("easy_kitchen:recipes")}"' in content
    assert 'd-none d-md-inline">Cancel</span>' in content


@pytest.mark.django_db
def test_edit_from_detail_cancels_to_recipe_detail(client, user):
    recipe = create_recipe(user, title="Pancakes")
    client.force_login(user)

    response = client.get(reverse("easy_kitchen:recipe-update", args=[recipe.pk]))

    content = response.content.decode()
    assert f'href="{reverse("easy_kitchen:recipe-detail", args=[recipe.pk])}"' in content
    assert 'd-none d-md-inline">Cancel</span>' in content


@pytest.mark.django_db
def test_recipe_pages_are_private_and_can_send_ingredients_to_a_new_list(client, user, other_user):
    client.force_login(user)
    created = client.post(
        reverse("easy_kitchen:recipe-create"),
        {"title": "Pancakes", "description": "Sunday", "image": png_upload(), "image_url": "https://example.com/pancakes.jpg"},
    )
    recipe = Recipe.objects.get(user=user, title="Pancakes")
    assert created.status_code == 302
    assert recipe.image
    assert recipe.picture_url == recipe.image.url

    detail = client.get(reverse("easy_kitchen:recipe-detail", args=[recipe.pk]))
    assert detail.status_code == 200
    detail_content = detail.content.decode()
    assert "Pancakes" in detail_content
    assert "data-edit-toggle" in detail_content
    assert 'src="/static/easy_kitchen/recipe-detail.js"' in detail_content
    assert detail_content.count('class="row g-2 align-items-end mb-3 edit-only"') == 2

    added = client.post(
        reverse("easy_kitchen:recipe-ingredient-create", args=[recipe.pk]),
        {"name": "Flour", "quantity": "200 g"},
        HTTP_HX_REQUEST="true",
    )
    assert added.status_code == 200
    added_content = added.content.decode()
    assert "Flour" in added_content
    assert 'class="btn-group edit-only" role="group" aria-label="Ingredient actions"' in added_content
    client.post(reverse("easy_kitchen:recipe-step-create", args=[recipe.pk]), {"text": "Mix"})

    sent = client.post(reverse("easy_kitchen:recipe-add-to-list", args=[recipe.pk]), {"title": "Weekend"})
    shopping_list = ShoppingList.objects.get(user=user, title="Weekend")
    assert sent.status_code == 302
    assert sent["Location"] == reverse("easy_kitchen:detail", args=[shopping_list.pk])
    assert list(shopping_list.items.values_list("name", "quantity")) == [("Flour", "200 g")]

    client.force_login(other_user)
    assert client.get(reverse("easy_kitchen:recipe-detail", args=[recipe.pk])).status_code == 404
    assert "Pancakes" not in client.get(reverse("easy_kitchen:recipes")).content.decode()


@pytest.mark.django_db
def test_recipe_json_import_accepts_an_image_url(client, user):
    client.force_login(user)
    payload = {
        "recipes": [
            {
                "title": "Pancakes",
                "description": "Sunday",
                "image_url": "https://example.com/pancakes.jpg",
                "calories": 450,
                "protein": 12,
                "preparation_minutes": 25,
                "ingredients": [{"name": "Flour", "quantity": "200 g"}],
                "steps": [{"text": "Fry"}],
            }
        ]
    }
    response = client.post(reverse("easy_kitchen:import-json"), {"json_data": json.dumps(payload)})
    recipe = Recipe.objects.get(user=user, title="Pancakes")
    assert response.status_code == 302
    assert recipe.image_url == "https://example.com/pancakes.jpg"
    assert recipe.calories == 450
    assert recipe.protein == 12
    assert recipe.preparation_minutes == 25
    ingredient = recipe.ingredients.get()
    assert ingredient.name == "Flour"
    assert ingredient.quantity == "200 g"
    assert recipe.steps.get().text == "Fry"


@pytest.mark.django_db
def test_api_recipes_stay_with_the_token_owner(client, user, other_user):
    token = Token.objects.create(user=user)
    headers = {"HTTP_AUTHORIZATION": f"Token {token.key}"}
    created = client.post(
        reverse("recipe-list"),
        json.dumps({
            "title": "Pancakes",
            "image_url": "https://example.com/pancakes.jpg",
            "calories": 450,
            "protein": 12,
            "preparation_minutes": 25,
            "ingredients": [{"name": "Flour", "quantity": "200 g"}, {"name": "Eggs", "quantity": "2"}],
            "steps": [{"text": "Mix"}],
        }),
        content_type="application/json",
        **headers,
    )
    assert created.status_code == 201
    body = created.json()
    assert body["picture_url"] == "https://example.com/pancakes.jpg"
    assert body["calories"] == 450
    assert body["protein"] == 12
    assert body["preparation_minutes"] == 25
    assert [(line["name"], line["quantity"]) for line in body["ingredients"]] == [("Flour", "200 g"), ("Eggs", "2")]
    assert Recipe.objects.get(pk=body["id"]).user == user

    hidden = client.get(reverse("recipe-list"), HTTP_AUTHORIZATION=f"Token {Token.objects.create(user=other_user).key}")
    assert hidden.json() == []

    imported = client.post(
        reverse("recipe-import-json"),
        json.dumps([{"title": "Soup", "ingredients": [{"name": "Onion", "quantity": "1"}]}]),
        content_type="application/json",
        **headers,
    )
    assert imported.status_code == 201
    assert Recipe.objects.filter(user=user, title="Soup").exists()

    reversed_ids = [line["id"] for line in reversed(body["ingredients"])]
    reordered = client.post(
        reverse("recipe-reorder-ingredients", args=[body["id"]]),
        json.dumps({"line_ids": reversed_ids}),
        content_type="application/json",
        **headers,
    )
    assert [line["id"] for line in reordered.json()["ingredients"]] == reversed_ids


@pytest.mark.django_db
def test_adding_a_recipe_to_an_existing_list_keeps_the_quantity(client, user):
    client.force_login(user)
    recipe = create_recipe(user, title="Pancakes", ingredients=[{"name": "Flour", "quantity": "200 g"}])
    shopping_list = ShoppingList.objects.create(user=user, title="Weekend", date=timezone.localdate())

    response = client.post(
        reverse("easy_kitchen:recipe-add-to-list", args=[recipe.pk]),
        {"shopping_list": shopping_list.pk},
    )

    assert response.status_code == 302
    assert response["Location"] == reverse("easy_kitchen:detail", args=[shopping_list.pk])
    assert list(shopping_list.items.values_list("name", "quantity")) == [("Flour", "200 g")]
    assert ShoppingList.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_an_ingredient_name_and_quantity_can_be_changed(client, user):
    client.force_login(user)
    recipe = create_recipe(user, title="Pancakes", ingredients=[{"name": "Flour", "quantity": "200 g"}])
    ingredient = recipe.ingredients.get()

    response = client.post(
        reverse("easy_kitchen:recipe-ingredient-update", args=[recipe.pk, ingredient.pk]),
        {"name": "  Whole wheat flour  ", "quantity": "300 g"},
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Whole wheat flour" in content
    assert "300 g" in content
    ingredient.refresh_from_db()
    assert ingredient.name == "Whole wheat flour"
    assert ingredient.quantity == "300 g"


@pytest.mark.django_db
def test_another_user_cannot_change_or_delete_an_ingredient(client, user, other_user):
    recipe = create_recipe(user, title="Pancakes", ingredients=[{"name": "Flour", "quantity": "200 g"}])
    ingredient = recipe.ingredients.get()
    client.force_login(other_user)

    update = client.post(
        reverse("easy_kitchen:recipe-ingredient-update", args=[recipe.pk, ingredient.pk]),
        {"name": "Sugar", "quantity": "1 kg"},
    )
    delete = client.post(reverse("easy_kitchen:recipe-ingredient-delete", args=[recipe.pk, ingredient.pk]))

    assert update.status_code == 404
    assert delete.status_code == 404
    ingredient.refresh_from_db()
    assert ingredient.name == "Flour"
    assert ingredient.quantity == "200 g"


@pytest.mark.django_db
def test_api_hides_a_foreign_recipe_and_can_reorder_steps(client, user, other_user):
    recipe = create_recipe(user, title="Pancakes", steps=[{"text": "Mix"}, {"text": "Fry"}])
    owner = Token.objects.create(user=user)
    other = Token.objects.create(user=other_user)
    detail = reverse("recipe-detail", args=[recipe.pk])

    assert client.get(detail, HTTP_AUTHORIZATION=f"Token {other.key}").status_code == 404
    stolen = client.patch(
        detail,
        json.dumps({"title": "Stolen"}),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Token {other.key}",
    )
    assert stolen.status_code == 404
    assert client.delete(detail, HTTP_AUTHORIZATION=f"Token {other.key}").status_code == 404
    recipe.refresh_from_db()
    assert recipe.title == "Pancakes"

    step_ids = [step.id for step in reversed(list(recipe.steps.all()))]
    reordered = client.post(
        reverse("recipe-reorder-steps", args=[recipe.pk]),
        json.dumps({"line_ids": step_ids}),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Token {owner.key}",
    )

    assert reordered.status_code == 200
    assert [step["id"] for step in reordered.json()["steps"]] == step_ids
