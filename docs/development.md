# Development

## Checks and tests

```bash
# Pre-commit (lint / format / mypy)
uv run poe check

# Tests
uv run poe test
```

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
