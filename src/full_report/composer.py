"""FullReportComposer Deep Module for Full Report Generation (Ticket #34 / T6.1).

Assembles planned document parts from FullReportStationPlan, delegates rendering to
stage renderers into an isolated temporary workspace (.temp/temp_parts/<STATION>/),
and compiles the final master deliverable into FULL REPORT/<STATION>/<MONTH>/<DATE>/<STEM>.docx
by reusing WordComDocumentCompiler directly as-is per D03, D14, D40.

Decisions Enforced:
- D03 / D40: Reuse WordComDocumentCompiler and FakeDocumentCompiler without custom margin modifications.
- D14: Managed temp_parts/ workspace lifecycle with automatic cleanup unless --keep-temp is specified.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import gc
import logging
from pathlib import Path
import shutil
from typing import Iterator, Sequence

from src.full_report.census import ExecutiveSummaryCensusBuilder
from src.full_report.plan_builder import FullReportStationPlan
from src.full_report.scan_render import FullReportScanPageRendererCore
from src.full_report.slicer import get_temp_parts_dir, temp_parts_workspace
from src.quick_report.compiler import (
    DocumentCompiler,
    FakeDocumentCompiler,
    WordComDocumentCompiler,
)

logger = logging.getLogger(__name__)

__all__ = [
    "FullReportCompilationResult",
    "FullReportComposer",
    "composer_temp_workspace",
]


@dataclass(frozen=True)
class FullReportCompilationResult:
    """Outcome and telemetry of a Full Report document compilation."""

    station: str
    output_path: Path
    part_count: int
    parts: tuple[Path, ...] = ()
    keep_temp: bool = False
    temp_dir: Path | None = None


@contextmanager
def composer_temp_workspace(
    temp_dir: Path | str | None = None,
    station: str = "",
    base_dir: Path | None = None,
    keep_temp: bool = False,
) -> Iterator[Path]:
    """Temporary working directory lifecycle manager with --keep-temp support (D14).

    Defaults to .temp/temp_parts/<STATION>/ per D14, automatically cleaning up
    in a finally block unless keep_temp is True.
    """
    if temp_dir is not None:
        active_path = Path(temp_dir).resolve()
        active_path.mkdir(parents=True, exist_ok=True)
        try:
            yield active_path
        finally:
            if not keep_temp and active_path.exists():
                shutil.rmtree(active_path, ignore_errors=True)
            gc.collect()
    else:
        st_name = station or "UNKNOWN"
        with temp_parts_workspace(station=st_name, base_dir=base_dir, keep_temp=keep_temp) as workspace_dir:
            yield workspace_dir


class FullReportComposer:
    """Orchestrates stage rendering and Word COM compilation for Full Report deliverables."""

    def __init__(
        self,
        compiler: DocumentCompiler | None = None,
        renderer: FullReportScanPageRendererCore | None = None,
        census_builder: ExecutiveSummaryCensusBuilder | None = None,
    ) -> None:
        self.compiler: DocumentCompiler = compiler or WordComDocumentCompiler()
        self.renderer = renderer
        self.census_builder = census_builder

    @contextmanager
    def session(self) -> Iterator[FullReportComposer]:
        """Manage active Word COM session across batch compilations."""
        if hasattr(self.compiler, "session") and callable(self.compiler.session):
            with self.compiler.session():
                yield self
        else:
            yield self

    def compose(
        self,
        plan: FullReportStationPlan,
        *,
        output_path: Path | str | None = None,
        keep_temp: bool = False,
        temp_dir: Path | str | None = None,
        base_dir: Path | None = None,
    ) -> FullReportCompilationResult:
        """Render planned parts and compile deliverable into master Word document.

        Args:
            plan: Deterministic FullReportStationPlan containing the Bill of Materials.
            output_path: Optional explicit output file path overriding plan.final_output_path.
            keep_temp: If True, preserves intermediate rendered docx parts in temp_parts/.
            temp_dir: Optional custom temporary directory for intermediate parts.
            base_dir: Optional workspace root directory for resolving .temp/ per D14.

        Returns:
            FullReportCompilationResult with compilation status and paths.
        """
        dest_path = (
            Path(output_path).resolve()
            if output_path is not None
            else Path(plan.final_output_path).resolve()
        )
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        with composer_temp_workspace(
            temp_dir=temp_dir,
            station=plan.station,
            base_dir=base_dir,
            keep_temp=keep_temp,
        ) as active_temp_dir:
            parts = self._render_parts(plan, active_temp_dir)
            compiled_path = self.compiler.compile(parts, dest_path)
            return FullReportCompilationResult(
                station=plan.station,
                output_path=compiled_path,
                part_count=len(parts),
                parts=tuple(parts),
                keep_temp=keep_temp,
                temp_dir=active_temp_dir,
            )

    def load(
        self,
        plan: FullReportStationPlan,
        *,
        output_path: Path | str | None = None,
        keep_temp: bool = False,
        temp_dir: Path | str | None = None,
        base_dir: Path | None = None,
    ) -> Path:
        """Render docx parts, compile final deliverable, and return output path."""
        result = self.compose(
            plan,
            output_path=output_path,
            keep_temp=keep_temp,
            temp_dir=temp_dir,
            base_dir=base_dir,
        )
        return result.output_path

    def _render_parts(
        self,
        plan: FullReportStationPlan,
        temp_dir: Path,
    ) -> list[Path]:
        """Iterate parts from FullReportStationPlan and delegate rendering."""
        return list(
            plan.render_all(
                temp_dir,
                renderer=self.renderer,
                census_builder=self.census_builder,
            )
        )
