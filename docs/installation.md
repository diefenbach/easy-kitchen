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

## Accounts

People sign up at `/accounts/signup/` with their email address and a password, and sign in with their email address. Sign-up sends a confirmation link, and nobody can sign in before confirming. Locally the mail is printed in the `runserver` terminal. The Django admin also signs in with the email address.

The user model is `accounts.User`: the email address is the login and is unique ignoring case, and there is no username. `createsuperuser` asks for an email address. An account created with `createsuperuser` has no confirmed address yet, so confirm it once through the link that the first sign-in sends.

A local database from before 25 November 2026 has the old migration history and the old user table. Drop it and start a fresh one, then run `migrate` again.

### Google sign-in

The "Continue with Google" button appears only when `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are set. Create an OAuth client of type *Web application* in the Google Cloud console (APIs & Services → Credentials) and add these authorized redirect URIs:

```text
http://localhost:8000/accounts/google/login/callback/
https://kitchen.iqpp.de/accounts/google/login/callback/
```

A Google sign-in with an address that already has an account signs in to that account and links Google to it. Otherwise it creates a new, confirmed account.

## MCP locally

```sh
DJANGO_SETTINGS_MODULE=project.settings.development PYTHONPATH=src POSTGRES_HOST=localhost \
  uv run --env-file .env python -m easy_kitchen.mcp_server
```

It listens on `http://127.0.0.1:8001/mcp`. Create a token with `drf_create_token` and send it as `Authorization: Bearer <token>`. See {doc}`mcp`.

## Production

GitHub Actions builds an image on every push to `main` that changes runtime files:

```text
ghcr.io/diefenbach/easy-kitchen:<commit-date>-<short-sha>
```

The deploy workflow runs `iqpp_prod/scripts/deploy.sh` on the server. It backs up the database, migrates, collects static files, restarts `kitchen` and `kitchen-mcp`, and checks the site. Only then does it write `EASYKITCHEN_IMAGE` in the Compose `.env`; on failure the previous image runs again. See `iqpp_prod/docs/deploy.md` for the details and the server setup.

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
DJANGO_DEFAULT_FROM_EMAIL=EasyKitchen <noreply@kitchen.iqpp.de>
EMAIL_HOST=<smtp-host>
EMAIL_PORT=587
EMAIL_HOST_USER=<smtp-user>
EMAIL_HOST_PASSWORD=<smtp-password>
EMAIL_USE_TLS=true
# Optional: enables "Continue with Google".
GOOGLE_CLIENT_ID=<client-id>
GOOGLE_CLIENT_SECRET=<client-secret>
```

Production refuses to start without `DJANGO_DEFAULT_FROM_EMAIL` and `EMAIL_HOST`, because sign-up needs confirmation mail. Use `EMAIL_USE_SSL=true` with `EMAIL_USE_TLS=false` for port 465.

The deploy script runs migrations and `collectstatic`. Static files go to a shared Nginx volume at `/static/`. Production stores them with a content hash in the name (`project.storage.HashedStaticFilesStorage`, Django's `ManifestStaticFilesStorage` that also rewrites ES module imports), so Nginx can let browsers cache `/static/` for good and a deploy still reaches every browser at once. A `{% static %}` path that is not collected makes that page fail with a server error, because hashed names are looked up in the manifest. `collectstatic` does not read templates, so a test (`test_every_static_path_in_the_templates_is_collected`) checks every `{% static %}` path in the templates against the manifest; it requires literal paths so it can see all of them. A CSS `url()` to a missing file makes `collectstatic` fail in the CI image probe. Uploaded recipe pictures go to `/media/`. Do not commit `src/staticfiles/` or `src/media/`.

To roll back, run `gh workflow run deploy.yml -R diefenbach/easy-kitchen -f tag=<older-tag>`.

### Logs

Production logs warnings and errors from Django and the app, with traceback, to stderr. Gunicorn writes every request and its own messages to the same stream. Read both on the server with `docker logs --since 1h kitchen`, and the MCP server with `docker logs kitchen-mcp`. Nginx logs every request for all sites to its own container log; each line starts with the host name, so `docker logs nginx 2>&1 | grep '^kitchen.iqpp.de'` shows kitchen. Docker keeps at most 5 × 10 MB per container. `iqpp_prod/docs/deploy.md` lists the deploy and backup logs.
