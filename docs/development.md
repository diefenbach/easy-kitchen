# Development

Work on a feature or bug-fix branch. Open a pull request and merge to `main` only when CI is green. Do not commit or push directly to `main`.

Shared writes belong in `easy_kitchen/services.py`. Scope every query to the current user. Do not add a PWA, SPA, or dependency without a clear product need.

## Tests

```sh
uv run python -m pytest
```

pytest-xdist runs that command in parallel (`-n auto`). Model, service, API, permission, and view tests live under `src/easy_kitchen/tests/`. Browser journeys live in `e2e/` and use Playwright. Install Chromium once:

```sh
uv run playwright install chromium
```

Browser tests only:

```sh
uv run python -m pytest e2e
```

This documentation is built in the same suite. Sphinx treats warnings as errors.

## Documentation

Build the HTML locally:

```sh
uv sync --all-groups
uv run sphinx-build -W -b html docs docs/_build/html
```

Open `docs/_build/html/index.html`. Read the Docs reads `.readthedocs.yaml` and `docs/requirements.txt`. After the GitHub repository is imported at [readthedocs.org](https://readthedocs.org/), each push to `main` publishes this tree.

## CI/CD

`.github/workflows/ci-cd.yml` runs on pull requests and on `main`:

- **test** — Ruff, pytest, and the browser suite.
- **build** — only on `main`. Pushes `ghcr.io/diefenbach/easy-kitchen:<sha>`.
- **deploy** — only on `main`. SSHs to production and runs `.github/scripts/deploy.sh`.

Feature branches are tested. They are not deployed.
