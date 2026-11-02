# Installation

## Requirements

- Python 3.10 or newer (CI and the Docker image use 3.13)
- [uv](https://docs.astral.sh/uv/)
- Docker, for the local PostgreSQL service
- Chromium, once, if you run the browser tests

## Local development

Copy the environment file and set `POSTGRES_PASSWORD` and `DJANGO_SECRET_KEY`:

```sh
cp .env.example .env
```

Start PostgreSQL. `docker-compose.yaml` is only this database. The port is bound to `127.0.0.1:5432`:

```sh
docker compose up -d
docker compose ps
```

Read database settings from `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, and `POSTGRES_PORT`. Do not introduce `DATABASE_URL`. When you run Django on the host, set `POSTGRES_HOST=localhost` if `.env` still says `postgres`.

Then install dependencies and run the app:

```sh
uv sync --all-groups
POSTGRES_HOST=localhost uv run --env-file .env python src/manage.py migrate
POSTGRES_HOST=localhost uv run --env-file .env python src/manage.py createsuperuser
POSTGRES_HOST=localhost uv run --env-file .env python src/manage.py runserver
```

The site is at `http://localhost:8000`. Development settings enable `DEBUG`, so Django serves static files from `src/easy_kitchen/static/`.

## MCP locally

```sh
DJANGO_SETTINGS_MODULE=project.settings.development PYTHONPATH=src POSTGRES_HOST=localhost \
  uv run --env-file .env python -m easy_kitchen.mcp_server
```

It listens on `http://127.0.0.1:8001/mcp`. Create a token with `drf_create_token` and send it as `Authorization: Token <token>`. See {doc}`mcp`.

## Production

GitHub Actions builds a SHA-tagged image on every push to `main`:

```text
ghcr.io/diefenbach/easy-kitchen:<git-sha>
```

The deploy job SSHs to the server, writes `EASYKITCHEN_IMAGE` in the Compose `.env`, and restarts `kitchen`, `kitchen-mcp`, and `nginx`. The production Compose file uses `image: ${EASYKITCHEN_IMAGE}` with no fallback tag.

Minimum Django environment on the server:

```ini
DJANGO_SECRET_KEY=<long-random-value>
DJANGO_ALLOWED_HOSTS=kitchen.iqpp.de
DJANGO_CSRF_TRUSTED_ORIGINS=https://kitchen.iqpp.de
POSTGRES_DB=easykitchen
POSTGRES_USER=<user>
POSTGRES_PASSWORD=<password>
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
```

The container runs migrations and `collectstatic` on start. Static files go to a shared Nginx volume at `/static/`. Uploaded recipe pictures go to `/media/`. Do not commit `src/staticfiles/` or `src/media/`.

To roll back, pin the previous SHA in `EASYKITCHEN_IMAGE` and bring the stack up again.
