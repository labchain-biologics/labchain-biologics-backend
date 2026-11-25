"""Write the API's OpenAPI schema to ``openapi.json`` (or the path given as argument).

The committed ``openapi.json`` is the public contract consumed by API clients, including the
web frontend, which generates its TypeScript types from it. CI fails if it is out of date.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Importing the app needs settings; the schema does not depend on their values.
os.environ.setdefault("SECRET_KEY", "openapi-export-only-secret-key-not-used-at-runtime")

from app.main import app  # noqa: E402


def main() -> None:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("openapi.json")
    schema = app.openapi()
    target.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"OpenAPI schema written to {target}")


if __name__ == "__main__":
    main()
