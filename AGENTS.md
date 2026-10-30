# EasyList development conventions

- Keep the application Django-first. Use Django forms, templates, and class-based views where practical.
- The application is English-first. Write user-facing strings in English and mark them for translation. Add the German translation in `src/locale/de/LC_MESSAGES/django.po`.
- Keep browser JavaScript small. HTMX is preferred for partial page updates; SortableJS is reserved for item ordering.
- All data is scoped to `request.user`; never trust an object ID without filtering through the current user.
- Use Django's `BigAutoField` primary keys. Foreign keys must use `settings.AUTH_USER_MODEL`.
- Put business operations that are shared by the web UI and API in `shopping/services.py`.
- Use the environment-specific settings modules deliberately: `development` for local Django work, `production` in the Docker image, and `test` for pytest. Read configuration only from environment variables.
- Use `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, and `POSTGRES_PORT` for database configuration; do not introduce `DATABASE_URL` or dotenv-loading dependencies.
- `docker-compose.yaml` exists only for the local PostgreSQL service. Develop the Django app locally with `uv run --env-file .env python src/manage.py runserver`; the production Compose stack lives separately.
- Keep source assets in `src/shopping/static/`. Generated `staticfiles/` are production output for the shared Nginx volume and must never be committed.
- Every new feature and every bug fix requires appropriate automated tests written or updated in the same change. Start feature work with a failing test whenever practical, then implement the smallest change that makes it pass, then refactor.
- Keep Django model, service, API, permission, and view tests under `src/shopping/tests/`. Put browser journeys in `e2e/`, using Playwright through pytest-playwright. Browser tests run with `uv run pytest`; install Chromium once with `uv run playwright install chromium`.
- For HTMX state-changing requests outside a form, send Django's CSRF token explicitly. Cover the browser interaction with an E2E test when it is user-visible.
- Run `uv run pytest` before handing off.
- Do not add a PWA, SPA, or dependency without a clear product need.
