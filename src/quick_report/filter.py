"""Validation and predicate filtering stage for Quick Report workflow."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.quick_report.utils import normalize_functional_location_input

if TYPE_CHECKING:
    from src.testsheet.models import SubstationTestsheetPackage
    from src.workflows.models import QuickReportRequest


class QuickReportFilter:
    """Pure in-memory validation and predicate filtering stage for Quick Report."""

    def filter(
        self,
        packages: list[SubstationTestsheetPackage],
        request: QuickReportRequest,
    ) -> list[SubstationTestsheetPackage]:
        """Filter target substation packages, ensuring valid data state and matching predicates."""
        valid_packages = [pkg for pkg in packages if pkg.data is not None]

        is_fl_mode = getattr(request.mode, "value", str(request.mode)).lower() == "fl"
        if is_fl_mode and request.target_package_names:
            target_fls = {
                normalize_functional_location_input(fl)
                for fl in request.target_package_names
            }
            valid_packages = [
                pkg
                for pkg in valid_packages
                if normalize_functional_location_input(pkg.data.fl_erms) in target_fls
            ]

        return valid_packages
