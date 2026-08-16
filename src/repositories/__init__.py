"""Shared repository interfaces and implementations for Pahang CLI."""
from src.repositories.workspace_storage import (
    WorkspaceStorage,
    LocalWorkspaceStorage,
)
from src.repositories.msms import (
    MsmsRepo,
    MsmsRepository,
    LocalExcelMsmsRepository,
    ConsolidateResult,
    EnrichResult,
)
from src.repositories.total_pe import (
    TotalPeRepo,
    TotalPeRepository,
    LocalExcelTotalPeRepository,
    PropagateResult,
)

__all__ = [
    "WorkspaceStorage",
    "LocalWorkspaceStorage",
    "MsmsRepo",
    "MsmsRepository",
    "LocalExcelMsmsRepository",
    "TotalPeRepo",
    "TotalPeRepository",
    "LocalExcelTotalPeRepository",
    "ConsolidateResult",
    "EnrichResult",
    "PropagateResult",
]
