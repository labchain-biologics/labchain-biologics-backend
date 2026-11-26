"""
The ``titerlane`` command. Needs the ``cli`` extra: ``pip install "titerlane-biologics-sdk[cli]"``.

The entry point is importable without the extra, so a missing dependency gets a clear message
instead of a traceback.
"""

from __future__ import annotations

import sys

CLI_PACKAGES = {"typer", "rich", "shellingham"}


def main() -> None:
    try:
        from titerlane.cli.app import app
    except ImportError as exc:
        if (exc.name or "").split(".")[0] not in CLI_PACKAGES:
            raise
        print(
            'The titerlane command needs the "cli" extra: '
            'pip install "titerlane-biologics-sdk[cli]"',
            file=sys.stderr,
        )
        raise SystemExit(1) from None
    app()
