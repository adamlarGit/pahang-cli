"""Settings menu actions, such as version rollback for Pahang CLI."""

from __future__ import annotations

import subprocess
import sys

from src import cli_selectors


def run_rollback() -> None:
    """Prompt the operator to select a previous version (commit) and roll back to it."""
    print("\nFetching recent versions...")
    try:
        subprocess.check_call(["git", "fetch", "--tags"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        output = subprocess.check_output(
            ["git", "log", "-n", "5", "--format=%h|%D|%s|%ar"],
            text=True,
        )
    except Exception as exc:
        print(f"❌ Error fetching version history: {exc}")
        return

    lines = [line.strip() for line in output.split("\n") if line.strip()]
    if not lines:
        print("No version history found.")
        return

    options = []
    for i, line in enumerate(lines):
        parts = line.split("|", 3)
        if len(parts) == 4:
            commit_hash, refs, subject, rel_time = parts

            version_tag = ""
            if refs:
                for ref in refs.split(","):
                    ref = ref.strip()
                    if ref.startswith("tag: "):
                        version_tag = f"[{ref.replace('tag: ', '')}]"
                        break

            version_padded = f"{version_tag:10}"
            time_padded = f"({rel_time})".ljust(17)

            label = f"{version_padded} {commit_hash}  {time_padded}  {subject}"
            if i == 0:
                label += "  <-- CURRENT"
            options.append(cli_selectors.SelectOption(label, commit_hash))

    options.append(cli_selectors.SelectOption("Cancel", "__cancel__", shortcut_key="c"))

    selection = cli_selectors.select_one(
        "ROLLBACK VERSION\nSelect a version to roll back to:",
        options,
    )

    if selection in (None, "__cancel__"):
        return

    if selection == options[0].value:
        print("\n✓ You are already on this version. No changes made.")
        return

    print(f"\nRolling back to {selection}...")
    try:
        subprocess.check_call(["git", "reset", "--hard", selection])

        print("Syncing dependencies (uv sync)...")
        subprocess.check_call(["uv", "sync"], shell=True)
    except Exception as exc:
        print(f"\n❌ Error during rollback: {exc}")
        return

    print("\n✓ Rollback successful!")
    print("The application will now exit. Please start it again using start_cli.bat.")
    print("Note: When starting, you can choose 'N' to skip the update prompt to stay on this version.")
    input("\nPress Enter to exit...")
    sys.exit(0)
