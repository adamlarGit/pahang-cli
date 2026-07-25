"""WhatsApp report workflow orchestrator for Pahang CLI."""

from __future__ import annotations

from pathlib import Path

from src import cli_selectors
from src.project.environment import ProjectEnvironment
from src.whatsapp import (
    WhatsAppReportSummary,
    build_quick_report_batch_confirmation_lines,
    generate_whatsapp_report,
    get_quick_report_batch_option_title,
    is_selectable_quick_report_batch,
)


def select_quick_report_batch(root_dir: str | Path) -> Path | None:
    """Interactively select a quick-report batch folder from the project tree."""
    root_path = Path(root_dir)
    return cli_selectors.select_directory_tree(
        root_path,
        title="Select Quick Report Batch",
        is_selectable=is_selectable_quick_report_batch,
        get_child_title=lambda path, selectable: get_quick_report_batch_option_title(path),
        get_confirmation_lines=lambda path: build_quick_report_batch_confirmation_lines(root_path, path),
    )


def run_generate_whatsapp_report(
    env: ProjectEnvironment,
    report_dir: str | Path | None = None,
) -> WhatsAppReportSummary | None:
    """Interactive / programmatic entrypoint for WhatsApp report generation workflow."""
    if report_dir is None:
        resources = env.get_whatsapp_report_resources()
        report_dir = select_quick_report_batch(resources.quick_report_dir)
        if report_dir is None:
            print("WhatsApp report generation cancelled.")
            return None

    summary = generate_whatsapp_report(env, report_dir)
    print(f"WhatsApp report generated: {summary.output_path}")
    return summary
