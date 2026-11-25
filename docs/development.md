# Development

## Checks and tests

```bash
# Pre-commit (lint / format / mypy)
uv run poe check

# Tests (unit + integration)
uv run poe test
```

Integration tests in `tests/integration/` run the real app against PostgreSQL. Start it with
`uv run poe start-local-run`; the suite creates and migrates a `labchain_test` database
(override with `TEST_DATABASE_URL`). Without a reachable database they are skipped.

## API contract (`openapi.json`)

`openapi.json` at the repository root is the public API contract. API clients, including the
web frontend, generate their types from it. Regenerate it after any API change:

```bash
uv run poe openapi
```

CI fails when the committed file is stale.

## Documentation (MkDocs)

Install the docs extra (alongside `dev` if you also use `poe`):

```bash
uv sync --extra dev --extra docs
uv run poe docs-serve
```

Or without poe:

```bash
uv sync --extra docs
uv run mkdocs serve
```

Open http://127.0.0.1:8000 (MkDocs default; if the API already uses that port, MkDocs will pick the next free port).

Build a static site:

```bash
uv run poe docs-build
```

Output is written to `site/` (gitignored). On push to `main`, GitHub Actions builds and deploys to GitHub Pages.
