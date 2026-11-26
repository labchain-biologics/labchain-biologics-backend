"""Deprecated: use ``titerlane-admin grant-membership`` (same options).

Kept so existing runbooks and the migration 0003 notes keep working.

    uv run python scripts/grant_membership.py --email lead@lab.org --workspace helix \
        --role bioinformatics_lead [--create --name "Helix Genomics"]
"""

from __future__ import annotations

import sys

from app.cli import main

if __name__ == "__main__":
    sys.exit(main(["grant-membership", *sys.argv[1:]]))
