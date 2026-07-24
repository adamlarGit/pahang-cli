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
