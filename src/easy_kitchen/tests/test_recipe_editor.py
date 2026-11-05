from unittest.mock import patch

import pytest
from django.urls import reverse

from easy_kitchen.models import RecipeIngredient, RecipeStep
from easy_kitchen.services import create_recipe


def editor_data(recipe, **overrides):
    data = {"title": recipe.title, "description": recipe.description}
    for prefix in ("ingredients", "steps"):
        lines = list(getattr(recipe, prefix).all())
        data.update({f"{prefix}-TOTAL_FORMS": str(len(lines)), f"{prefix}-INITIAL_FORMS": str(len(lines))})
        for index, line in enumerate(lines):
            data[f"{prefix}-{index}-id"] = str(line.pk)
            data[f"{prefix}-{index}-ORDER"] = str(index + 1)
            for field in (("name", "quantity") if prefix == "ingredients" else ("text",)):
                data[f"{prefix}-{index}-{field}"] = getattr(line, field)
    return data | overrides


@pytest.mark.django_db
def test_editor_saves_recipe_lines_deletions_and_order_together(client, user):
    recipe = create_recipe(user, title="Soup", ingredients=[{"name": "Onion", "quantity": "1"}, {"name": "Carrot"}], steps=["Chop", "Simmer"])
    onion, carrot = recipe.ingredients.all()
    chop, simmer = recipe.steps.all()
    client.force_login(user)
    data = editor_data(recipe, title="New soup", **{
        "ingredients-TOTAL_FORMS": "3", "ingredients-0-name": "Red onion", "ingredients-0-quantity": "2",
        "ingredients-0-ORDER": "2", "ingredients-1-DELETE": "on",
        "ingredients-2-name": "Salt", "ingredients-2-quantity": "1 tsp", "ingredients-2-ORDER": "1",
        "steps-0-ORDER": "2", "steps-1-ORDER": "1",
    })
    response = client.post(reverse("easy_kitchen:recipe-update", args=[recipe.pk]), data)
    assert response.status_code == 302
    recipe.refresh_from_db()
    assert recipe.title == "New soup"
    assert list(recipe.ingredients.values_list("name", "quantity")) == [("Salt", "1 tsp"), ("Red onion", "2")]
    assert recipe.ingredients.get(name="Red onion").pk == onion.pk
    assert not RecipeIngredient.objects.filter(pk=carrot.pk).exists()
    assert list(recipe.steps.values_list("pk", flat=True)) == [simmer.pk, chop.pk]


@pytest.mark.django_db
@pytest.mark.parametrize("invalid", [{"title": ""}, {"ingredients-0-name": ""}, {"steps-0-text": ""}])
def test_editor_errors_preserve_the_draft_and_leave_database_unchanged(client, user, invalid):
    recipe = create_recipe(user, title="Soup", ingredients=[{"name": "Onion"}], steps=["Chop"])
    client.force_login(user)
    response = client.post(reverse("easy_kitchen:recipe-update", args=[recipe.pk]), editor_data(recipe, description="Draft description", **invalid))
    assert response.status_code == 422
    recipe.refresh_from_db()
    assert recipe.title == "Soup" and recipe.description == ""
    assert recipe.ingredients.get().name == "Onion"
    assert recipe.steps.get().text == "Chop"
    assert "Draft description" in response.content.decode()


@pytest.mark.django_db
def test_editor_rejects_foreign_line_ids_and_foreign_recipes(client, user, other_user):
    recipe = create_recipe(user, title="Soup", ingredients=[{"name": "Onion"}], steps=["Chop"])
    foreign = create_recipe(other_user, title="Private", ingredients=[{"name": "Secret"}], steps=["Private step"])
    client.force_login(user)
    response = client.post(reverse("easy_kitchen:recipe-update", args=[recipe.pk]), editor_data(recipe, title="Changed", **{
        "ingredients-0-id": str(foreign.ingredients.get().pk), "steps-0-id": str(foreign.steps.get().pk),
    }))
    assert response.status_code == 422
    recipe.refresh_from_db()
    assert recipe.title == "Soup"
    assert foreign.ingredients.get().name == "Secret" and foreign.steps.get().text == "Private step"
    assert client.get(reverse("easy_kitchen:recipe-update", args=[foreign.pk])).status_code == 404
    assert client.post(reverse("easy_kitchen:recipe-update", args=[foreign.pk]), editor_data(foreign)).status_code == 404


@pytest.mark.django_db
def test_editor_uses_one_transaction(client, user):
    recipe = create_recipe(user, title="Soup", ingredients=[{"name": "Onion"}], steps=["Chop"])
    client.force_login(user)
    with patch.object(RecipeStep, "save", side_effect=RuntimeError("Could not save step")):
        with pytest.raises(RuntimeError, match="Could not save step"):
            client.post(reverse("easy_kitchen:recipe-update", args=[recipe.pk]), editor_data(recipe, title="Changed", **{"ingredients-0-name": "Changed onion", "steps-0-text": "Changed step"}))
    recipe.refresh_from_db()
    assert recipe.title == "Soup" and recipe.ingredients.get().name == "Onion"
    assert recipe.steps.get().text == "Chop"


@pytest.mark.django_db
def test_editor_requires_management_forms_and_detail_is_read_only(client, user):
    recipe = create_recipe(user, title="Soup", ingredients=[{"name": "Onion"}], steps=["Chop"])
    client.force_login(user)
    response = client.post(reverse("easy_kitchen:recipe-update", args=[recipe.pk]), {"title": "Changed"})
    assert response.status_code == 422
    recipe.refresh_from_db()
    assert recipe.title == "Soup"
    content = client.get(reverse("easy_kitchen:recipe-detail", args=[recipe.pk])).content.decode()
    assert 'data-edit-toggle' not in content
    assert 'id="ingredient-form"' not in content and 'id="step-form"' not in content
    assert 'aria-label="Edit ingredient"' not in content
    assert 'aria-label="Edit recipe"' in content


@pytest.mark.django_db
def test_htmx_editor_save_returns_updated_recipe_and_pushes_detail_url(client, user):
    recipe = create_recipe(user, title="Soup", ingredients=[{"name": "Onion"}], steps=["Chop"])
    client.force_login(user)
    response = client.post(reverse("easy_kitchen:recipe-update", args=[recipe.pk]), editor_data(recipe, title="New soup"), HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    assert response["HX-Push-Url"] == reverse("easy_kitchen:recipe-detail", args=[recipe.pk])
    assert "New soup" in response.content.decode()
    assert 'id="recipe-editor-form"' not in response.content.decode()
    assert "Recipe updated." in response.content.decode()


@pytest.mark.django_db
def test_htmx_editor_error_keeps_form_and_url(client, user):
    recipe = create_recipe(user, title="Soup", ingredients=[{"name": "Onion"}])
    client.force_login(user)
    response = client.post(reverse("easy_kitchen:recipe-update", args=[recipe.pk]), editor_data(recipe, title="", description="Draft"), HTTP_HX_REQUEST="true")
    assert response.status_code == 422
    assert "HX-Push-Url" not in response
    assert 'id="recipe-editor-form"' in response.content.decode()
    assert "Draft" in response.content.decode()
    assert recipe.ingredients.get().name == "Onion"


@pytest.mark.django_db
def test_htmx_editor_from_overview_returns_the_overview(client, user):
    recipe = create_recipe(user, title="Soup")
    client.force_login(user)
    response = client.post(f'{reverse("easy_kitchen:recipe-update", args=[recipe.pk])}?return_to=overview', editor_data(recipe, title="New soup"), HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    assert response["HX-Push-Url"] == reverse("easy_kitchen:recipes")
    assert "New soup" in response.content.decode()
    assert 'id="recipe-editor-form"' not in response.content.decode()


@pytest.mark.django_db
def test_recipe_delete_action_is_only_in_the_editor(client, user):
    recipe = create_recipe(user, title="Soup")
    client.force_login(user)
    detail = client.get(reverse("easy_kitchen:recipe-detail", args=[recipe.pk])).content.decode()
    editor = client.get(reverse("easy_kitchen:recipe-update", args=[recipe.pk])).content.decode()
    assert 'id="delete-recipe-modal"' not in detail
    assert 'aria-label="Delete"' not in detail
    assert 'id="delete-recipe-modal"' in editor
    assert 'aria-label="Delete"' in editor
    assert 'data-editor-delete' in editor
