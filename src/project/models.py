"""Project domain models for Pahang CLI."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

VALID_VOLTAGE_TYPES: tuple[str, ...] = ("11kV", "33kV")


@dataclass(frozen=True)
class ProjectMetadata:
    """Immutable representation of a configured project in Pahang CLI."""
    key: str
    name: str
    po_number: str
    state: str
    voltage_type: str
    year: str
    cycle: str
    technologies: tuple[str, ...]
    base_path: str

    def __post_init__(self) -> None:
        if self.voltage_type and self.voltage_type not in VALID_VOLTAGE_TYPES:
            raise ValueError(
                f"Invalid voltage type '{self.voltage_type}'. Must be one of {VALID_VOLTAGE_TYPES}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize metadata to a dictionary compatible with json storage."""
        return {
            "name": self.name,
            "po_number": self.po_number,
            "state": self.state,
            "type": self.voltage_type,
            "year": self.year,
            "cycle": self.cycle,
            "base_path": self.base_path,
            "technologies": list(self.technologies),
        }

    @classmethod
    def from_dict(cls, key: str, data: dict[str, Any]) -> ProjectMetadata:
        """Create ProjectMetadata from a configuration dictionary."""
        raw_techs = data.get("technologies", ("IR", "US", "TEV"))
        if isinstance(raw_techs, (list, tuple)):
            technologies = tuple(str(t) for t in raw_techs)
        else:
            technologies = ("IR", "US", "TEV")

        voltage_type = str(data.get("type", data.get("voltage_type", "11kV")))
        if voltage_type not in VALID_VOLTAGE_TYPES:
            voltage_type = "11kV"

        return cls(
            key=str(key),
            name=str(data.get("name", "")),
            po_number=str(data.get("po_number", "")),
            state=str(data.get("state", "pahang")),
            voltage_type=voltage_type,
            year=str(data.get("year", "")),
            cycle=str(data.get("cycle", "")),
            technologies=technologies,
            base_path=str(data.get("base_path", "")),
        )


@dataclass
class CameraConfig:
    """Configuration for IR and DG camera photo filename patterns."""
    ir_mode: str = "single"  # "single" or "dual_pair"
    ir_prefix: str = "FLIR"  # e.g., "FLIR" or "IR_"
    dc_prefix: str = "DC_"   # Visual photo prefix when ir_mode is "dual_pair"
    dc_offset: int = 1       # Offset for visual photo pairing (e.g. +1)
    dg_prefix: str = "IMG_"  # e.g., "IMG_", "P1000", "P"

    def to_dict(self) -> dict[str, Any]:
        """Serialize configuration to dictionary."""
        return {
            "ir_mode": self.ir_mode,
            "ir_prefix": self.ir_prefix,
            "dc_prefix": self.dc_prefix,
            "dc_offset": self.dc_offset,
            "dg_prefix": self.dg_prefix,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> CameraConfig:
        """Create CameraConfig instance from dictionary with fallback defaults."""
        if not data or not isinstance(data, dict):
            return cls()
        try:
            offset = int(data.get("dc_offset", 1))
        except (ValueError, TypeError):
            offset = 1
        return cls(
            ir_mode=str(data.get("ir_mode", "single")),
            ir_prefix=str(data.get("ir_prefix", "FLIR")),
            dc_prefix=str(data.get("dc_prefix", "DC_")),
            dc_offset=offset,
            dg_prefix=str(data.get("dg_prefix", "IMG_")),
        )


@dataclass(frozen=True)
class HealthCheckItem:
    """Represents the existence and health status of a workspace folder or file."""
    label: str
    path: str
    exists: bool
    is_critical: bool = True


@dataclass(frozen=True)
class WorkspaceHealth:
    """Aggregated workspace directory structure health evaluation."""
    is_healthy: bool
    items: tuple[HealthCheckItem, ...]

