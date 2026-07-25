"""Processing history store for Pahang CLI workflows."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any, Sequence

from src.testsheet.models import SubstationTestsheetPackage


def format_package_history_key(pkg: SubstationTestsheetPackage) -> str:
    """Format package history key: <STATION>/<MONTH>/<DD-MM-YYYY>."""
    date_str = pkg.date_str or (pkg.data.date_str if pkg.data else "")
    parts = [p for p in (pkg.station, pkg.month, date_str) if p]
    return "/".join(parts)


class ProcessingHistoryStore:
    """Manages persistent JSON history for workflow package processing."""

    def __init__(self, history_file: Path) -> None:
        self.history_file = history_file

    def load(self) -> dict[str, Any]:
        """Load processing history dictionary from disk."""
        if not self.history_file.exists():
            return {}
        try:
            with self.history_file.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def record_processed_packages(
        self,
        processed_packages: Sequence[SubstationTestsheetPackage],
    ) -> list[str]:
        """Record processed packages into JSON history file.

        Returns list of newly updated/recorded package keys.
        """
        if not processed_packages:
            return []

        history = self.load()

        files_per_key: dict[str, int] = {}
        for pkg in processed_packages:
            key = format_package_history_key(pkg)
            if key:
                files_per_key[key] = files_per_key.get(key, 0) + 1

        now_iso = datetime.now().isoformat()
        newly_processed_keys: list[str] = []

        for key, count in files_per_key.items():
            history[key] = {
                "last_processed": now_iso,
                "files_scanned": count,
            }
            newly_processed_keys.append(key)

        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        with self.history_file.open("w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)

        return sorted(list(set(newly_processed_keys)))
