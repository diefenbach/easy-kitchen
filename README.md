# EasyList

A private, responsive shopping list application built with Django 5.2 LTS. It uses server-rendered Django templates, HTMX for small partial updates, Bootstrap 5.3, and SortableJS exclusively for item ordering.

## Features

- Multiple lists per user: title, date, items, quantity, completion state, and drag-and-drop ordering
- English-first source strings with German as the default interface language
- Built-in Django authentication and Django admin
- REST API at `/api/v1/` using token authentication and strictly user-scoped queries
- JSON import: `POST /api/v1/shopping-lists/import_json/`
- Gunicorn container for a reverse-proxying Nginx; PostgreSQL configured through `POSTGRES_*` variables
- pytest coverage for models, web UI, API, and permissions

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

The container runs migrations and `collectstatic` when it starts. The output is placed in a shared `easylist_static` volume that Nginx serves at `/static/`. Do not commit the generated `src/staticfiles/` directory. A separate media volume can be added later for uploads.

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

The API accepts and returns lists with nested items. Every endpoint is restricted to the authenticated user. While logged in, open `http://localhost:8000/api/v1/` in a browser for Swagger UI. The OpenAPI document is at `http://localhost:8000/api/v1/schema/`.

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

Browser tests are located in `e2e/` and run automatically with pytest. Install Chromium once:

```sh
uv run playwright install chromium
```

To run browser tests only:

```sh
uv run pytest e2e
```

The data model is intentionally small. A future recipe feature can be added as a separate model related to `ShoppingList`.
