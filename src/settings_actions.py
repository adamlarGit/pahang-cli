"""Settings menu actions, such as version rollback."""

from __future__ import annotations

import subprocess
import sys

from src import cli_selectors
from src.project.models import CameraConfig, PrpdConfig
from src.project.repository import JsonFileProjectRepository


def _safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        safe_text = text.replace("✓", "[OK]").replace("❌", "[ERROR]")
        encoding = getattr(sys.stdout, "encoding", None) or "ascii"
        print(safe_text.encode(encoding, errors="replace").decode(encoding))


def run_rollback() -> None:
    """Prompt the operator to select a previous version (commit) and roll back to it."""
    print("\nFetching recent versions...")
    try:
        # Silently fetch latest tags from remote so colleagues always see the human-readable versions
        subprocess.check_call(["git", "fetch", "--tags"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        output = subprocess.check_output(
            ["git", "log", "-n", "5", "--format=%h|%D|%s|%ar"], 
            text=True
        )
    except Exception as exc:
        _safe_print(f"❌ Error fetching version history: {exc}")
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
        _safe_print("\n✓ You are already on this version. No changes made.")
        return

    print(f"\nRolling back to {selection}...")
    try:
        subprocess.check_call(["git", "reset", "--hard", selection])
        
        print("Syncing dependencies (uv sync)...")
        # In windows environments where uv is used, this ensures correct python deps
        subprocess.check_call(["uv", "sync", "--frozen"], shell=True)
    except Exception as exc:
        _safe_print(f"\n❌ Error during rollback: {exc}")
        return

    _safe_print("\n✓ Rollback successful!")
    print("The application will now exit. Please start it again using start_cli.bat.")
    print("Note: When starting, you can choose 'N' to skip the update prompt to stay on this version.")
    input("\nPress Enter to exit...")
    sys.exit(0)


def run_configure_camera_patterns() -> None:
    """Interactive settings menu to configure IR and DG photo filename patterns independently."""
    repo = JsonFileProjectRepository()

    while True:
        current = repo.get_camera_config()

        ir_desc = (
            f"Dual IR/DC Pair ({current.ir_prefix}{{num}}* thermal + {current.dc_prefix}{{num+{current.dc_offset}}}* visual)"
            if current.ir_mode == "dual_pair"
            else (
                f"FLIR Series ({current.ir_prefix}{{num}}* thermal & visual pair)"
                if current.ir_prefix.upper() == "FLIR"
                else f"Single Prefix ({current.ir_prefix}{{num}}*)"
            )
        )
        dg_desc = f"{current.dg_prefix}{{num}}*"

        menu_title = (
            "CAMERA PHOTO PATTERN SETTINGS\n"
            f"Current Active Patterns:\n"
            f"  • IR Pattern : {ir_desc}\n"
            f"  • DG Pattern : {dg_desc}"
        )

        options = [
            cli_selectors.SelectOption("Configure IR Camera Pattern", "configure_ir"),
            cli_selectors.SelectOption("Configure DG Camera Pattern", "configure_dg"),
            cli_selectors.SelectOption("Back to Settings Menu", "__cancel__", shortcut_key="c"),
        ]

        choice = cli_selectors.select_one(menu_title, options, default_value="configure_ir")

        if choice in (None, "__cancel__"):
            return

        if choice == "configure_ir":
            _configure_ir_pattern(repo, current)
        elif choice == "configure_dg":
            _configure_dg_pattern(repo, current)


def _configure_ir_pattern(repo: JsonFileProjectRepository, current: CameraConfig) -> None:
    """Sub-menu for configuring IR camera pattern with explicit cancel option."""
    print("\n--- CONFIGURE IR CAMERA PATTERN ---")
    ir_options = [
        cli_selectors.SelectOption(
            "FLIR Camera        (e.g., FLIR0001.jpg thermal & FLIR0001 -photo.jpg visual pair)",
            "flir_single",
        ),
        cli_selectors.SelectOption(
            "Dual IR_ & DC_ Pair (e.g., IR_0001.jpg thermal + DC_0002.jpg visual pair)",
            "ir_dc_pair",
        ),
        cli_selectors.SelectOption(
            "IR_ Single Prefix  (e.g., IR_0001.jpg thermal photo only)",
            "ir_single",
        ),
        cli_selectors.SelectOption(
            "Custom IR & Visual Pattern...",
            "custom_ir",
        ),
        cli_selectors.SelectOption("Cancel / Back", "__cancel__", shortcut_key="c"),
    ]

    ir_sel = cli_selectors.select_one(
        "Select IR Camera Photo Pattern:",
        ir_options,
        default_value="flir_single" if (current.ir_mode == "single" and current.ir_prefix == "FLIR") else ("ir_single" if current.ir_mode == "single" else "ir_dc_pair"),
    )


    if ir_sel in (None, "__cancel__"):
        return

    new_mode = current.ir_mode
    new_ir_prefix = current.ir_prefix
    new_dc_prefix = current.dc_prefix
    new_dc_offset = current.dc_offset

    if ir_sel == "flir_single":
        new_mode = "single"
        new_ir_prefix = "FLIR"
    elif ir_sel == "ir_single":
        new_mode = "single"
        new_ir_prefix = "IR_"
    elif ir_sel == "ir_dc_pair":
        new_mode = "dual_pair"
        new_ir_prefix = "IR_"
        new_dc_prefix = "DC_"
        new_dc_offset = 1

    elif ir_sel == "custom_ir":
        mode_opt = cli_selectors.select_one(
            "Select IR File Mode:",
            [
                cli_selectors.SelectOption("Single file per reading", "single"),
                cli_selectors.SelectOption("Dual file pair (Thermal IR + Visual DC)", "dual_pair"),
                cli_selectors.SelectOption("Cancel / Back", "__cancel__", shortcut_key="c"),
            ],
        )
        if mode_opt in (None, "__cancel__"):
            return
        new_mode = mode_opt

        ir_p = input(f"Enter IR thermal file prefix [{new_ir_prefix}] (or press Enter to keep): ").strip()
        if ir_p:
            new_ir_prefix = ir_p

        if new_mode == "dual_pair":
            dc_p = input(f"Enter visual DC file prefix [{new_dc_prefix}] (or press Enter to keep): ").strip()
            if dc_p:
                new_dc_prefix = dc_p
            off_s = input(f"Enter visual DC file number offset [{new_dc_offset}] (or press Enter to keep): ").strip()
            if off_s:
                try:
                    new_dc_offset = int(off_s)
                except ValueError:
                    pass

    updated = CameraConfig(
        ir_mode=new_mode,
        ir_prefix=new_ir_prefix,
        dc_prefix=new_dc_prefix,
        dc_offset=new_dc_offset,
        dg_prefix=current.dg_prefix,
    )
    repo.save_camera_config(updated)
    _safe_print("\n✓ IR Camera pattern updated successfully!")


def _configure_dg_pattern(repo: JsonFileProjectRepository, current: CameraConfig) -> None:
    """Sub-menu for configuring DG camera pattern with explicit cancel option."""
    print("\n--- CONFIGURE DG CAMERA PATTERN ---")
    dg_options = [
        cli_selectors.SelectOption(
            "Standard IMG_ Prefix  (e.g., IMG_0001.jpg)",
            "img_std",
        ),
        cli_selectors.SelectOption(
            "P / P1000 Series      (e.g., P1000022.JPG / P0001.JPG)",
            "p_series",
        ),
        cli_selectors.SelectOption(
            "Custom DG Prefix...",
            "custom_dg",
        ),
        cli_selectors.SelectOption("Cancel / Back", "__cancel__", shortcut_key="c"),
    ]

    dg_sel = cli_selectors.select_one(
        "Select DG Camera Photo Pattern:",
        dg_options,
        default_value="img_std" if current.dg_prefix.upper().startswith("IMG") else "p_series",
    )

    if dg_sel in (None, "__cancel__"):
        return

    new_dg_prefix = current.dg_prefix

    if dg_sel == "img_std":
        new_dg_prefix = "IMG_"
    elif dg_sel == "p_series":
        new_dg_prefix = "P"
    elif dg_sel == "custom_dg":
        dg_p = input(f"Enter DG file prefix [{new_dg_prefix}] (or press Enter to keep): ").strip()
        if dg_p:
            new_dg_prefix = dg_p

    updated = CameraConfig(
        ir_mode=current.ir_mode,
        ir_prefix=current.ir_prefix,
        dc_prefix=current.dc_prefix,
        dc_offset=current.dc_offset,
        dg_prefix=new_dg_prefix,
    )
    repo.save_camera_config(updated)
    _safe_print("\n✓ DG Camera pattern updated successfully!")


def run_configure_prpd_style() -> None:
    """Interactive settings menu to configure PRPD graph generation style."""
    repo = JsonFileProjectRepository()
    current = repo.get_prpd_config()

    current_desc = (
        "Option C: Composite Table + PRPD Graph (Headless Chrome) [Default]"
        if current.mode == "option_c"
        else "Option B: Pure PRPD Scatter Graph (Native Python Matplotlib)"
    )

    menu_title = (
        "PRPD GRAPH GENERATION STYLE SETTINGS\n"
        f"Current Active Style:\n"
        f"  • {current_desc}\n\n"
        "Choose PRPD graph rendering strategy for Quick Report CBM defect detail pages:"
    )

    options = [
        cli_selectors.SelectOption(
            "Option C: Composite Table + PRPD Graph (Headless Chrome) [Default]",
            "option_c",
        ),
        cli_selectors.SelectOption(
            "Option B: Pure PRPD Scatter Graph (Native Python Matplotlib)",
            "option_b",
        ),
        cli_selectors.SelectOption("Cancel / Back", "__cancel__", shortcut_key="c"),
    ]

    choice = cli_selectors.select_one(menu_title, options, default_value=current.mode)

    if choice in (None, "__cancel__"):
        return

    if choice != current.mode:
        updated = PrpdConfig(mode=choice)
        repo.save_prpd_config(updated)
        mode_label = (
            "Option C (Composite Table + PRPD Graph)"
            if choice == "option_c"
            else "Option B (Pure PRPD Scatter Graph)"
        )
        _safe_print(f"\n✓ PRPD graph generation style set to {mode_label} successfully!")
    else:
        _safe_print("\n✓ PRPD graph generation style unchanged.")
