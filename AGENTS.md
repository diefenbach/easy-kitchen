# EasyKitchen development conventions

Project-specific rules. General working rules and engineering principles come from the maintainer's global agent
conventions (`~/Development/agents/AGENTS.md`); where they disagree, this file wins.

- Keep the application Django-first. Use Django forms, templates, and class-based views where practical.
- The application is English-first. Write user-facing strings in English and mark them for translation. Add the German translation in `src/locale/de/LC_MESSAGES/django.po`.
- Keep browser JavaScript small. HTMX is preferred for partial page updates; SortableJS is reserved for item ordering.
- All data is scoped to `request.user`; never trust an object ID without filtering through the current user.
- Use Django's `BigAutoField` primary keys. Foreign keys must use `settings.AUTH_USER_MODEL`.
- Put business operations that are shared by the web UI and API in `easy_kitchen/services.py`.
- Use the environment-specific settings modules deliberately: `development` for local Django work, `production` in the Docker image, and `test` for pytest. Read configuration only from environment variables.
- Use `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, and `POSTGRES_PORT` for database configuration; do not introduce `DATABASE_URL` or dotenv-loading dependencies.
- `docker-compose.yaml` exists only for the local PostgreSQL service. Develop the Django app locally with `uv run --env-file .env python src/manage.py runserver`; the production Compose stack lives separately.
- Keep source assets in `src/easy_kitchen/static/`. Generated `staticfiles/` are production output for the shared Nginx volume and must never be committed.
- Do not commit or push directly to `main` for runtime or user-visible application changes; they go through a pull request.
- Documentation-only and housekeeping changes (`docs/`, `AGENTS.md`, `README.md` without matching `src/` changes, and CI tweaks such as skipping deploy for those paths) do not need a separate GitHub branch or pull request. Commit sensible chunks on `main`, push, and let CI on `main` run; production deploy is skipped when only non-runtime paths changed (see `.github/workflows/ci-cd.yml`).
- Git and pull requests (agents, for application work):
  - Before every commit that touches Python code, run `uv run ruff check src e2e` and `uv run pyright` (same as CI) and fix any findings first.
  - Push with `git push -u origin HEAD:your-branch` so the remote branch name matches the feature branch.
  - Open the PR with `gh pr create --base main --head your-branch`.
- Keep Django model, service, API, permission, and view tests under `src/easy_kitchen/tests/`. Put browser journeys in `e2e/`, using Playwright through pytest-playwright. Browser tests run with `uv run pytest`; install Chromium once with `uv run playwright install chromium`.
- For HTMX state-changing requests outside a form, send Django's CSRF token explicitly. Cover the browser interaction with an E2E test when it is user-visible.
- Run `uv run pytest` before handing off. pytest-xdist runs that command in parallel (`-n auto`).
- Do not add a PWA, SPA, or dependency without a clear product need.

## Engineering principles

The general principles (YAGNI, TDD, DRY, typing, docstrings, skills) are in the maintainer's global agent
conventions. In this project:

- Application code is `src/easy_kitchen`, `src/project`, and `src/accounts`; typing and docstring rules apply
  there. ruff checks docstrings (`D100`–`D105`); test modules need only a module docstring. CI runs `uv run pyright` (standard mode, `[tool.pyright]` in `pyproject.toml`) and it must report no
  errors. Use `# pyright: ignore[<rule>]` only where the Django/DRF stubs cannot describe correct code, with a
  comment saying why. In views behind a login, get a typed user with `signed_in_user(request)`.
- Sources of truth: business rules in `easy_kitchen/services.py`, choices on the model, versions in
  `package.json` and `pyproject.toml`, settings in the settings modules.
- Project skills go in `.claude/skills/<name>/SKILL.md`.
