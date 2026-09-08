"""The `coral [scope]` console script."""

import argparse
import logging
import sys
from pathlib import Path

from coral.local import default_scope, review
from coral.progress import live_table
from coral.settings import load_settings


def configure_logging() -> None:
    """Send Coral progress to stderr without HTTP request diagnostics."""
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def main() -> int:
    configure_logging()

    parser = argparse.ArgumentParser(prog="coral", description="Review code in this directory.")
    parser.add_argument("scope", nargs="?", help="review scope passed verbatim to each reviewer")
    arguments = parser.parse_args()
    try:
        workspace = Path.cwd()
        scope = arguments.scope if arguments.scope is not None else default_scope(workspace)
        settings = load_settings()
        # The table closes before the review prints, so the final table stays above it.
        with live_table(workspace) as table:
            rendered = review(workspace, scope, settings, table)
        print(rendered)
    except Exception as error:
        print(f"Coral failed: {error}", file=sys.stderr)
        return 1
    return 0
