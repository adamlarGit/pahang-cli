"""Package and defect extraction stage for Quick Report workflow."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from src.quick_report.defects import MasterQr03DefectRepository
from src.testsheet.repository import SubstationTestsheetRepository
if TYPE_CHECKING:
    from src.project.environment import ProjectEnvironment
    from src.quick_report.defects import CbmDefectRecord, ViDefectRecord
    from src.testsheet.models import SubstationTestsheetPackage
    from src.workflows.models import QuickReportMode, QuickReportRequest


class QuickReportExtractor:
    """Pure Read I/O discovery and per-station defect extraction stage for Quick Report."""

    def __init__(self, repository: SubstationTestsheetRepository | None = None) -> None:
        self.repository = repository or SubstationTestsheetRepository()
        self._defect_repo: MasterQr03DefectRepository | None = None

    def extract(
        self, environment: ProjectEnvironment, request: QuickReportRequest
    ) -> list[SubstationTestsheetPackage]:
        """Discover testsheet packages strictly via read I/O (without domain filtering)."""
        packages: list[SubstationTestsheetPackage] = []

        is_folder_mode = getattr(request.mode, "value", str(request.mode)).lower() == "folder"
        if is_folder_mode:
            for folder_str in request.target_folders:
                candidate = Path(folder_str)
                if candidate.exists():
                    folder_path = candidate
                else:
                    folder_path = environment.get_testsheet_dir() / folder_str
                    if not folder_path.exists():
                        raise FileNotFoundError(
                            f"Requested target folder does not exist: '{folder_str}' "
                            f"(checked: {candidate}, {folder_path})"
                        )
                packages.extend(self.repository.discover_packages(folder_path))
        else:
            packages = self.repository.discover_packages(
                environment.get_testsheet_dir()
            )

        return packages

    def _get_defect_repo(
        self, environment: ProjectEnvironment
    ) -> MasterQr03DefectRepository:
        """Get or initialize cached MasterQr03DefectRepository instance."""
        if self._defect_repo is None:
            self._defect_repo = MasterQr03DefectRepository(environment=environment)
        return self._defect_repo

    def extract_defects(
        self, pkg: SubstationTestsheetPackage, environment: ProjectEnvironment
    ) -> tuple[list[CbmDefectRecord], list[ViDefectRecord]]:
        """Fetch CBM and VI defects for a single substation package.

        Returns (cbm_defects, vi_defects).

        Raises FileNotFoundError if the ENGR directory or workbooks are missing.
        Raises RuntimeError if required sheets are missing or workbooks are unreadable.
        Returns empty lists only when the source is valid but no matching defect rows exist.
        """
        if not pkg.data or not pkg.data.fl_erms:
            return [], []

        defect_repo = self._get_defect_repo(environment)
        cbm_defects = defect_repo.fetch_cbm_defects(pkg.data.fl_erms)
        vi_defects = defect_repo.fetch_vi_defects(pkg.data.fl_erms)
        return cbm_defects, vi_defects
