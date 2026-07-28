"""Workflow for removing desktop.ini files recursively from a specified directory."""

from __future__ import annotations

import logging
import os
import stat
import subprocess
import sys
from pathlib import Path


def remove_desktop_ini_files(target_directory: str | Path) -> int:
    """Recursively remove all desktop.ini files from target_directory."""
    target_path = Path(target_directory).expanduser().resolve()
    if not target_path.exists() or not target_path.is_dir():
        raise FileNotFoundError(f"Target directory not found: '{target_path}'")

    print(f"\nScanning for 'desktop.ini' files in '{target_path}' and its subfolders...")

    script_path = Path(__file__).parent.parent / "scripts" / "remove_desktop_ini.ps1"
    if sys.platform == "win32" and script_path.exists():
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path), "-FolderPath", str(target_path)],
                text=True,
                check=False,
            )
            if res.returncode == 0:
                return 0
        except Exception as exc:
            logging.warning("PowerShell script execution encountered issue, falling back to Python removal: %s", exc)

    removed_count = 0
    for root, _, files in os.walk(target_path):
        for file in files:
            if file.lower() == "desktop.ini":
                full_path = Path(root) / file
                try:
                    os.chmod(full_path, stat.S_IWRITE)
                    full_path.unlink()
                    removed_count += 1
                    print(f"  ✓ Removed: {full_path}")
                except Exception as exc:
                    print(f"  ❌ Failed to remove {full_path}: {exc}")

    if removed_count > 0:
        print(f"\n✓ Successfully removed {removed_count} 'desktop.ini' file(s).")
    else:
        print("\nNo 'desktop.ini' files found.")

    return removed_count


def run_remove_desktop_ini() -> int:
    """Interactive entrypoint for removing desktop.ini files."""
    default_path = Path.cwd()
    print("\n" + "=" * 55)
    print("  🧹 REMOVE DESKTOP.INI FILES")
    print("=" * 55)
    raw_path = input(f"Enter target folder path to scan [{default_path}]: ").strip().strip('"')
    target_path = Path(raw_path) if raw_path else default_path

    if not target_path.exists():
        print(f"❌ Error: Path '{target_path}' does not exist.")
        return 0

    return remove_desktop_ini_files(target_path)
