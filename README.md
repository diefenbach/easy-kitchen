# EasyList

A private, responsive shopping list application built with Django 5.2 LTS. It uses server-rendered Django templates, HTMX for small partial updates, Bootstrap 5.3, and SortableJS for ordering.

## Features

### Shopping lists

- Each user has their own lists. A list has a title, a date, and ordered items.
- An item has a name, a quantity, and a completed state. Drag the handle to reorder it.
- Check an item off with the checkbox or by tapping its name. The name and the quantity are then struck through.
- Hide completed items, or mark every completed item as open again.
- Adding an item whose name already exists updates that row. Matching ignores case and extra spaces.
- Quantities with the same unit are added. `1 l` plus `2 l` becomes `3 l`, and `6` plus `2` becomes `8`. A decimal comma is accepted, so `1,5 kg` plus `0,5 kg` becomes `2 kg`.
- A different unit stays beside the others. `1 l` plus `500 ml` stays `1 l, 500 ml`, and `2 packs` plus `2` stays `2 packs, 2`.
- Adding the item again clears its completed state, so it returns to the open list.

### Articles

- Every item name is saved once per user as an article.
- The item field suggests those saved articles while typing.
- The Articles page, next to Log out, lists them. Rename or delete an article there. Deleting it removes the suggestion and leaves items already on a list unchanged.

### Recipes

- Each user has their own recipes. A recipe has a title, a description, one picture, ordered ingredients, and ordered cooking steps.
- The picture is a file uploaded in the app, or an image URL supplied by the API, MCP, or JSON import. The uploaded file is shown when both are present.
- An ingredient has a name and a quantity, in the same way a shopping-list item does. A step is one block of text. Drag the handle to reorder either list.
- **Add to list** copies those ingredients onto a shopping list that belongs to the same user. Choose an existing list, or enter a title to create one for today. The ingredient name and quantity are copied onto the new item.

### Web application

- Django 5.2 templates and class-based views. HTMX updates items in place. SortableJS is used only for reordering.
- Bootstrap 5.3, with touch targets large enough for a phone.
- English source strings. German is the default interface language.
- Django accounts, login, logout, and the Django admin.
- A JSON import page at `/lists/import/` accepts the same document as the API. The format is described under [JSON import](#json-import).
- Recipes have the same shape at `/recipes/`, including `/recipes/import/`. The format is described under [Recipe JSON](#recipe-json).

### REST API

- Base path: `/api/v1/shopping-lists/`.
- Authentication is `Authorization: Token <token>`, not Bearer. Every query is limited to the token owner.
- The view set creates, reads, updates, and deletes lists with nested items.
- `POST /api/v1/shopping-lists/{id}/reorder/` accepts `{"item_ids": [3, 1, 2]}`.
- `POST /api/v1/shopping-lists/import_json/` accepts `{"lists": [...]}` or a bare list. Each list needs `title`, `date` (`YYYY-MM-DD`), and `items` with `name` and optional `quantity`.
- Recipes live at `/api/v1/recipes/` with the same token and the same user scope.
- `POST /api/v1/recipes/{id}/reorder-ingredients/` and `POST /api/v1/recipes/{id}/reorder-steps/` accept `{"line_ids": [3, 1, 2]}`.
- `POST /api/v1/recipes/import_json/` accepts `{"recipes": [...]}` or a bare list. The fields are described under [Recipe JSON](#recipe-json). An image file is not part of the JSON; send `image_url` or upload the file in the app.
- Swagger UI at `/api/v1/` and the OpenAPI schema at `/api/v1/schema/` are public. List and recipe operations stay authenticated.
- The web UI, the API, and MCP call the same operations in `shopping/services.py`.

### MCP server

- A second process of the same image serves streamable HTTP at `/mcp` on port `8001`.
- It authenticates the same DRF token. The tools `create_shopping_list` and `create_recipe` have no user argument; the record belongs to the token owner.
- Confirm `title`, an ISO `date`, and `items` before creating a list.
- Confirm `title`, `ingredients`, and `steps` before creating a recipe. `image_url` is optional.
- Host and origin checks use `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS`. Override them with `MCP_ALLOWED_HOSTS` and `MCP_ALLOWED_ORIGINS`.
- In production, Nginx proxies `/mcp` to the MCP container. The process does not call the HTTP API. It uses the shared database and service layer.

### Runtime

- PostgreSQL is configured with `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, and `POSTGRES_PORT`.
- The container runs Gunicorn on port `8000`, applies migrations, and collects static files into the shared Nginx volume.
- pytest covers models, services, views, API, permissions, translations, and browser flows.

## JSON import

Open **Import JSON** on the list overview, or `POST` the same document to `/api/v1/shopping-lists/import_json/` with `Authorization: Token <token>`.

The body is either an object with a `lists` array or the array itself. Every list in the document is created for the signed-in user.

```json
{
  "lists": [
    {
      "title": "Weekend shop",
      "date": "2026-11-01",
      "items": [
        {"name": "Oat milk", "quantity": "2 l"},
        {"name": "Apples", "quantity": "1 kg", "checked": false}
      ]
    }
  ]
}
```

| Field | Required | Meaning |
| --- | --- | --- |
| `title` | yes | List title |
| `date` | yes | Shopping date, `YYYY-MM-DD` |
| `items` | no | Items on that list. Omit it for an empty list. |
| `items[].name` | yes | Item name |
| `items[].quantity` | no | Quantity text, for example `500 g` or `2 pieces`. An empty string is allowed. |
| `items[].checked` | no | `true` when the item is already completed. Defaults to `false`. |
| `items[].position` | no | Order on the list, starting at `1`. Items keep the array order when this is omitted. |

`id`, `created_at`, and `updated_at` are returned by the API and ignored on import.

## Recipe JSON

Open **Import JSON** on the recipe overview, or `POST` the same document to `/api/v1/recipes/import_json/` with `Authorization: Token <token>`.

The body is either an object with a `recipes` array or the array itself. Every recipe in the document is created for the signed-in user.

```json
{
  "recipes": [
    {
      "title": "Pancakes",
      "description": "Sunday breakfast",
      "image_url": "https://example.com/pancakes.jpg",
      "ingredients": [
        {"name": "flour", "quantity": "200 g"},
        {"name": "eggs", "quantity": "2"}
      ],
      "steps": [
        {"text": "Mix the batter."},
        {"text": "Fry until golden."}
      ]
    }
  ]
}
```

| Field | Required | Meaning |
| --- | --- | --- |
| `title` | yes | Recipe title |
| `description` | no | Longer text. An empty string is allowed. |
| `image_url` | no | `http` or `https` address of a picture. Shown when no file has been uploaded. |
| `ingredients` | no | Ordered ingredients. Omit it for a recipe without ingredients. |
| `ingredients[].name` | yes | Ingredient name |
| `ingredients[].quantity` | no | Quantity text, for example `500 g` or `2`. An empty string is allowed. |
| `ingredients[].position` | no | Order, starting at `1`. Ingredients keep the array order when this is omitted. |
| `steps` | no | Ordered cooking steps |
| `steps[].text` | yes | One step |
| `steps[].position` | no | Order, starting at `1`. Steps keep the array order when this is omitted. |

`id`, `image`, `picture_url`, `created_at`, and `updated_at` are returned by the API. `image` is the uploaded file address. `picture_url` is the file when one exists, otherwise `image_url`. Import ignores those read-only fields.

## Local development

Start the local PostgreSQL service:

```sh
cp .env.example .env
# Set POSTGRES_PASSWORD and DJANGO_SECRET_KEY in .env.
docker compose up -d
```

The service is available only at `localhost:5432` and stores its data in the `easylist_postgres` Docker volume. Check its status with:

```sh
docker compose ps
```

Then start EasyList locally:

```sh
cp .env.example .env
# Set DJANGO_SECRET_KEY in .env.
uv sync --all-groups
uv run --env-file .env python src/manage.py migrate
uv run --env-file .env python src/manage.py createsuperuser
uv run --env-file .env python src/manage.py runserver
```

`uv` loads the local `.env`; Django does not require a dotenv library. The application is then available at `http://localhost:8000`. The development settings deliberately enable `DEBUG` so Django serves source static files directly from `src/shopping/static/`.

A database backup can be imported into the running local PostgreSQL container. Run `migrate` afterwards to apply any missing migrations.

## Production: existing iqpp Compose stack

The image is built as `registry.iqpp.de/iqpp/easylist:latest` and listens internally on port `8000`. It is added to the existing `iqpp_prod` Compose stack. Compose loads `./easylist/.env` through `env_file`; Django reads only standard environment variables.

The production environment file requires at least:

```dotenv
DJANGO_SECRET_KEY=<long-random-value>
DJANGO_ALLOWED_HOSTS=easylist.iqpp.de
DJANGO_CSRF_TRUSTED_ORIGINS=https://easylist.iqpp.de
POSTGRES_DB=easylist
POSTGRES_USER=<user>
POSTGRES_PASSWORD=<password>
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
```

The container runs migrations and `collectstatic` when it starts. The output is placed in a shared `easylist_static` volume that Nginx serves at `/static/`. Uploaded recipe pictures are stored in `easylist_media` and served at `/media/`. Do not commit `src/staticfiles/` or `src/media/`.

The MCP server is a second process from the same image. It listens on port `8001` at `/mcp` and creates lists for whichever user owns the DRF token on that request. Publish it only through Nginx, on the internal Docker network:

```yaml
command: ["python", "-m", "shopping.mcp_server"]
```

```nginx
location /mcp {
    proxy_pass http://easylist-mcp:8001;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header Authorization $http_authorization;
    proxy_buffering off;
}
```

Clients call `https://easylist.iqpp.de/mcp` with `Authorization: Token <token>`. There is no user argument. `DJANGO_ALLOWED_HOSTS` is accepted as the MCP host allowlist. Override it with `MCP_ALLOWED_HOSTS` when the proxy host differs.

## API

Create a token, for example through Django admin or the shell:

```sh
uv run --env-file .env python src/manage.py drf_create_token <username>
```

Example:

```sh
curl -H "Authorization: Token <token>" http://localhost:8000/api/v1/shopping-lists/
curl -X POST -H "Authorization: Token <token>" -H "Content-Type: application/json" \
  -d '{"lists":[{"title":"Pasta","date":"2026-10-30","items":[{"name":"Pasta","quantity":"500 g"}]}]}' \
  http://localhost:8000/api/v1/shopping-lists/import_json/
```

The API accepts and returns lists with nested items. The import document is the [JSON import](#json-import) format. Shopping-list endpoints are restricted to the authenticated user. Open `http://localhost:8000/api/v1/` in a browser for Swagger UI. The OpenAPI document is at `http://localhost:8000/api/v1/schema/`.

Run the MCP server locally with the development settings:

```sh
DJANGO_SETTINGS_MODULE=project.settings.development PYTHONPATH=src \
  uv run --env-file .env python -m shopping.mcp_server
```

It listens on `http://127.0.0.1:8001/mcp`. Create a token with `drf_create_token` and send it as `Authorization: Token <token>`.

## Quality

```sh
uv run pytest
```

The suite runs in parallel through pytest-xdist. Browser tests are located in `e2e/` and run automatically with pytest. Install Chromium once:

```sh
uv run playwright install chromium
```

To run browser tests only:

```sh
uv run pytest e2e
```

The web UI, the API, and MCP call the same operations in `shopping/services.py`.
