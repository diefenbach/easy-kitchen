# Development

Work on a feature or bug-fix branch. Open a pull request and merge to `main` only when CI is green. Documentation-only updates may go straight to `main` without a pull request; CI still runs there, and deploy is skipped when no runtime paths changed (see below).

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

### PostgreSQL write regressions

The normal suite uses SQLite. To verify row locking, concurrent article creation
and merged quantity limits, run against a dedicated local PostgreSQL instance:

```sh
POSTGRES_DB=easykitchen_test POSTGRES_USER=easykitchen_test \
POSTGRES_PASSWORD=test-only-password POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=5432 \
uv run python -m pytest --ds=project.settings.postgresql_test -n 0 \
  src/easy_kitchen/tests/test_postgresql_writes.py \
  src/easy_kitchen/tests/test_write_integrity.py \
  src/easy_kitchen/tests/test_quantity_and_order_integrity.py \
  src/easy_kitchen/tests/test_export_regressions.py \
  src/easy_kitchen/tests/test_pdf_image_regressions.py \
  src/easy_kitchen/tests/test_planner_boundaries.py
```

Use a test role with permission to create databases. pytest creates and removes
its own `test_<POSTGRES_DB>` database; do not point this at production. The
`postgres` CI job runs the same tests against PostgreSQL 17 and is required by
the production image build. PostgreSQL-only tests skip during SQLite runs.

## JavaScript checks

Node.js 24 or newer is needed for the development checks and vendor updates.
Install the exact package versions from the committed lockfile and run the same
checks as CI:

```sh
npm ci --ignore-scripts
npm run lint
npm run format:check
npm run test:vendor
npm run vendor:check
```

Run `npm run format` to apply the shared Prettier format to the JavaScript and its
tooling configuration. ESLint checks browser globals and correctness rules across
application JavaScript and the Node scripts. Generated vendor files are excluded
from lint and formatting. The `javascript` CI job checks lint, formatting, the
vendor build tests, and the committed vendor files; the production build requires
this job as well as the Python and browser tests.

## Vendor assets

Bootstrap 5.3.3, Bootstrap Icons 1.11.3, HTMX 2.0.4, and SortableJS 1.15.6 are
pinned npm development dependencies. Their runtime files and license notices are
committed under `src/easy_kitchen/static/easy_kitchen/vendor/` and served through
Django staticfiles. Bootstrap's bundle includes Popper, whose license is copied
as well. Production and ordinary Python development do not need Node.js or an
asset build. The Google Fonts stylesheet remains an external request; browser
font fallbacks work when that service is unavailable.

To regenerate the vendor files:

```sh
npm ci --ignore-scripts
npm run vendor:build
npm run vendor:check
```

`scripts/vendor.mjs` uses Node's filesystem APIs and an explicit copy list.
It verifies installed versions against the lockfile and prepares all assets in
a temporary sibling directory before replacing `vendor/`. Copy failures leave
the current vendor files intact. If the final rename fails, the script restores
the previous directory; if restoration also fails, it preserves the backup and
prints its recovery path. Run builds with the development server stopped because
the two renames briefly remove the destination directory.

Only the compiled Bootstrap CSS and bundle, the minified Bootstrap Icons CSS
with its two referenced fonts, and the minified HTMX and SortableJS scripts are
shipped. Bootstrap Icons retains its `font/fonts/` layout so relative URLs resolve.
SCSS, icon metadata, alternative CSS files, and source maps are omitted.
Source-map comments are removed from the copied CSS and JavaScript to avoid
requests for maps and source trees that are not shipped. Debugging uses the
distributed minified files.

For an intentional dependency update, change its exact version in `package.json`,
run `npm install --package-lock-only --ignore-scripts`, then run the commands
above and the test suite. Commit `package.json`, `package-lock.json`, and the
regenerated vendor files together. `vendor:check` compares filenames and bytes,
detects missing, changed, and unexpected files, and never replaces the current
vendor directory.

Cards and editor rows use `createSortable`, which returns the SortableJS instance
and destroys it during HTMX cleanup.
Article and recipe suggestion lists display at most 20 matches. Typing a more
specific query still searches the complete catalog.

## Documentation

Build the HTML locally:

```sh
uv sync --all-groups
uv run sphinx-build -W -b html docs docs/_build/html
```

Open `docs/_build/html/index.html`. Read the Docs reads `.readthedocs.yaml` and `docs/requirements.txt`. After the GitHub repository is imported at [readthedocs.org](https://readthedocs.org/), each push to `main` publishes this tree.

## CI/CD

`.github/workflows/ci-cd.yml` runs on pull requests and on `main`:

- **javascript** — ESLint, Prettier, vendor build tests, and vendor consistency checks using locked npm dependencies.
- **test** — Ruff, pytest, and the browser suite (every pull request and every push to `main`).
- **build** — only on `main`, and only when runtime paths changed (`src/`, `Dockerfile`, lockfiles, deploy script). Pushes `ghcr.io/diefenbach/easy-kitchen:<sha>`.
- **deploy** — same gate as **build**. SSHs to production and runs `.github/scripts/deploy.sh`.

Documentation-only changes (for example `docs/`, `AGENTS.md`, or `README.md`) still run **test** but skip **build** and **deploy**. Read the Docs publishes the docs tree separately.

Feature branches are tested. They are not deployed.
