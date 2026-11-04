# REST API

Base path: `/api/v1/`. Authentication is `Authorization: Token <token>`, not Bearer. Every list, recipe, and meal-plan query is limited to the token owner.

Create a token through Django admin or:

```sh
uv run --env-file .env python src/manage.py drf_create_token <username>
```

Swagger UI is public at `/api/v1/`. The OpenAPI document is at `/api/v1/schema/`. List and recipe operations stay authenticated.

## Shopping lists

- Collection: `/api/v1/shopping-lists/`
- The view set creates, reads, updates, and deletes lists with nested items.
- `POST /api/v1/shopping-lists/{id}/reorder/` accepts `{"item_ids": [3, 1, 2]}`.
- `POST /api/v1/shopping-lists/import_json/` accepts `{"lists": [...]}` or a bare list. See {doc}`json`.

```sh
curl -H "Authorization: Token <token>" http://localhost:8000/api/v1/shopping-lists/
curl -X POST -H "Authorization: Token <token>" -H "Content-Type: application/json" \
  -d '{"lists":[{"title":"Pasta","date":"2026-10-30","items":[{"name":"Pasta","quantity":"500 g"}]}]}' \
  http://localhost:8000/api/v1/shopping-lists/import_json/
```

## Recipes

- Collection: `/api/v1/recipes/`
- The same token and the same user scope as shopping lists.
- `POST /api/v1/recipes/{id}/reorder-ingredients/` and `POST /api/v1/recipes/{id}/reorder-steps/` accept `{"line_ids": [3, 1, 2]}`.
- `POST /api/v1/recipes/import_json/` accepts `{"recipes": [...]}` or a bare list. An image file is not part of the JSON; send `image_url` or upload the file in the app.


## Meal planner

All planner endpoints use the same authentication and services as the web planner.

| Method | Path | Input | Result |
| --- | --- | --- | --- |
| GET | `/api/v1/meal-planner/` | Optional `week=YYYY-MM-DD` query parameter | A Monday–Sunday week with seven days; omitted means the current local week. |
| PUT | `/api/v1/meal-planner/{date}/` | `{"recipe_id": 12}` | Assign or replace that date's recipe. Repeating the same request leaves one entry. |
| DELETE | `/api/v1/meal-planner/{date}/` | None | Clear that date. Returns 204, including when it is already empty. |
| POST | `/api/v1/meal-planner/add-to-list/` | `week` and exactly one of `shopping_list_id` or `title` | Copy the week's ingredients to an existing owned list or a new list, returning the list and its items. |

`date` and `week` use ISO calendar dates. Any day in a week selects the Monday on or before it. Week reads include empty days as `{"date": "2027-01-02", "recipe": null}`; planned days contain a recipe summary with `id` and `title`. Full recipe details are available from `/api/v1/recipes/{id}/`.

For example, `GET /api/v1/meal-planner/?week=2027-01-01` returns:

```json
{
  "week_start": "2026-12-28",
  "week_end": "2027-01-03",
  "days": [
    {"date": "2026-12-28", "recipe": null},
    {"date": "2026-12-29", "recipe": null},
    {"date": "2026-12-30", "recipe": null},
    {"date": "2026-12-31", "recipe": null},
    {"date": "2027-01-01", "recipe": {"id": 12, "title": "Soup"}},
    {"date": "2027-01-02", "recipe": null},
    {"date": "2027-01-03", "recipe": null}
  ]
}
```

To create a shopping list, send `{"week": "2027-01-01", "title": "Weekly shop"}`. To use an existing list, send `{"week": "2027-01-01", "shopping_list_id": 8}`. Supplying both targets or neither is a validation error. A week with no planned recipes is rejected without creating a list.

Matching ingredients and compatible quantities are merged using the existing shopping-list rules. Recipes planned on several days contribute once per day. **Repeating the POST adds the ingredients again**; this operation is not idempotent. Copying never clears the plan. Validation failures return 400; all data stays scoped to the token owner.
