# REST API

Base path: `/api/v1/`. Authentication is `Authorization: Token <token>`, not Bearer. Every list and recipe query is limited to the token owner.

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
