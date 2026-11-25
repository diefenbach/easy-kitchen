"""Canonical public record shapes shared by REST and MCP."""


def article_data(article):
    """Return an article as JSON-ready data with its department code."""
    return {"id": article.pk, "name": article.name, "department": article.department_code}


def item_data(item):
    """Return a shopping item as JSON-ready data, including its list id and position."""
    return {
        **article_data(item), "quantity": item.quantity, "checked": item.checked,
        "position": item.position, "list_id": item.shopping_list_id,
    }


def shopping_list_data(shopping_list, *, summary=False):
    """Return a shopping list as JSON-ready data; without `summary` it includes the items."""
    data = {
        "id": shopping_list.pk, "title": shopping_list.title, "icon": shopping_list.icon,
        "date": shopping_list.date.isoformat(), "position": shopping_list.position,
        "created_at": shopping_list.created_at.isoformat(),
        "updated_at": shopping_list.updated_at.isoformat(),
    }
    if not summary:
        data["items"] = [item_data(item) for item in shopping_list.items.all()]
    return data


def recipe_data(recipe, *, absolute_url=lambda value: value, summary=False):
    """Return a recipe as JSON-ready data; without `summary` it includes ingredients and steps.

    `absolute_url` turns the uploaded image's path into a full URL for API and MCP clients.
    """
    picture_url = absolute_url(recipe.image.url) if recipe.image else recipe.image_url
    data = {
        "id": recipe.pk, "title": recipe.title, "description": recipe.description,
        "is_favorite": recipe.is_favorite, "picture_url": picture_url,
        "calories": recipe.calories, "protein": recipe.protein,
        "carbohydrates": recipe.carbohydrates, "fat": recipe.fat,
        "preparation_minutes": recipe.preparation_minutes, "position": recipe.position,
        "created_at": recipe.created_at.isoformat(), "updated_at": recipe.updated_at.isoformat(),
    }
    if not summary:
        data["ingredients"] = [{"id": line.pk, "name": line.name, "quantity": line.quantity,
                                "position": line.position} for line in recipe.ingredients.all()]
        data["steps"] = [{"id": line.pk, "text": line.text, "position": line.position}
                         for line in recipe.steps.all()]
    return data
