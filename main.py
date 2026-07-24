"""Pahang CLI main entrypoint."""

from __future__ import annotations

import logging
import sys

from src.workflow_cli import run_cli


logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)


if __name__ == "__main__":
    try:
        run_cli()
    except Exception as exc:
        logging.error("Startup failed: %s", exc)
        sys.exit(1)
