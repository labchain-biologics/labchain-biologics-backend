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

## Releasing the Python SDK

`labchain-biologics-sdk` is published to PyPI by `.github/workflows/sdk-release.yml` when a
tag `sdk-vX.Y.Z` is pushed. It uses [trusted publishing](https://docs.pypi.org/trusted-publishers/):
no PyPI token is stored in GitHub.

### One-time setup

1. On PyPI, add a *pending trusted publisher* for the project `labchain-biologics-sdk`:
   owner `labchain-biologics`, repository `labchain-biologics-backend`, workflow
   `sdk-release.yml`, environment `pypi`.
2. In the GitHub repository settings, create the environment `pypi`. Adding required
   reviewers makes every publication wait for a manual approval.

### Each release

1. Set the version in `sdk/src/labchain/_version.py` (the only place it is defined).
2. In `sdk/CHANGELOG.md`, give that version's section its date instead of `(unreleased)`.
3. Merge to `main`, then tag the merge commit and push the tag:

    ```bash
    git tag -a sdk-v0.2.0 -m "labchain-biologics-sdk 0.2.0"
    git push origin sdk-v0.2.0
    ```

The workflow refuses a tag that does not match `_version.py` or a version still marked
unreleased. It runs the SDK tests and type checks, builds the sdist and wheel, checks them
with `twine check --strict`, installs the wheel with the `cli` extra in a clean environment,
and only then publishes. A version published to PyPI can never be replaced, only yanked.
