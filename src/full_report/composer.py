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
import fnmatch
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
    chunk_paths: tuple[Path, ...] = ()
    is_multipart: bool = False


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
        """Render planned parts and compile deliverable into Word document(s).

        For VCB/GIS archetypes, produces multi-part chunked output documents.
        For RMU and other archetypes, produces a single master document.
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
            # Single-pass rendering: produce all indexed intermediate docx files
            all_rendered_parts = self._render_parts(plan, active_temp_dir)

            chunks = plan.chunks
            is_multipart = plan.is_multipart

            if is_multipart:
                # Pre-purge: delete existing part files matching exact stem
                stem = plan.output_filename.removesuffix(".docx")
                self._purge_existing_parts(dest_path.parent, stem)

                # Partition rendered files by chunk boundaries
                assert sum(len(c.parts) for c in chunks) == len(all_rendered_parts), (
                    f"Rendered parts count ({len(all_rendered_parts)}) does not match "
                    f"total chunk parts ({sum(len(c.parts) for c in chunks)})"
                )
                chunk_paths: list[Path] = []
                offset = 0
                for chunk in chunks:
                    chunk_count = len(chunk.parts)
                    chunk_rendered = all_rendered_parts[offset:offset + chunk_count]
                    offset += chunk_count

                    chunk.destination_path.parent.mkdir(parents=True, exist_ok=True)
                    compiled_path = self.compiler.compile(
                        chunk_rendered, chunk.destination_path
                    )
                    chunk_paths.append(compiled_path)

                primary_output = chunk_paths[0] if chunk_paths else dest_path
                return FullReportCompilationResult(
                    station=plan.station,
                    output_path=primary_output,
                    part_count=len(all_rendered_parts),
                    parts=tuple(all_rendered_parts),
                    keep_temp=keep_temp,
                    temp_dir=active_temp_dir,
                    chunk_paths=tuple(chunk_paths),
                    is_multipart=True,
                )
            else:
                # Single document compilation (existing behavior)
                compiled_path = self.compiler.compile(all_rendered_parts, dest_path)
                return FullReportCompilationResult(
                    station=plan.station,
                    output_path=compiled_path,
                    part_count=len(all_rendered_parts),
                    parts=tuple(all_rendered_parts),
                    keep_temp=keep_temp,
                    temp_dir=active_temp_dir,
                )

    @staticmethod
    def _purge_existing_parts(directory: Path, exact_stem: str) -> None:
        """Delete pre-existing part documents matching exact stem pattern."""
        if not directory.exists():
            return
        pattern = f"{exact_stem} - Part *.docx"
        for f in directory.iterdir():
            if f.is_file() and fnmatch.fnmatch(f.name, pattern):
                logger.info("Pre-purging existing part file: %s", f.name)
                f.unlink()

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
