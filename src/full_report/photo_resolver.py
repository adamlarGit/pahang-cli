"""FLIR IR and Visual Photo Pair Resolver for Full Report generation (Ticket #25 / T2.2)."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import math
from pathlib import Path
import re
from typing import Iterator, Sequence

from src.project.models import CameraConfig

logger = logging.getLogger(__name__)

VALID_IMAGE_EXTENSIONS: tuple[str, ...] = (".jpg", ".jpeg", ".png")


@dataclass(frozen=True)
class PhotoPair:
    """Pair of thermal IR photo and visual inspection photo."""

    ir_photo: str = ""
    visual_photo: str = ""
    photo_number: int | None = None
    ir_path: Path | None = None
    visual_path: Path | None = None

    @property
    def has_ir(self) -> bool:
        """True if thermal IR photo path is present."""
        return bool(self.ir_photo)

    @property
    def has_visual(self) -> bool:
        """True if visual inspection photo path is present."""
        return bool(self.visual_photo)

    @property
    def is_complete(self) -> bool:
        """True if both thermal IR and visual photos are present."""
        return bool(self.ir_photo and self.visual_photo)

    def __iter__(self) -> Iterator[str]:
        """Allow tuple unpacking: (ir_photo, visual_photo) = pair."""
        yield self.ir_photo
        yield self.visual_photo


class RawPhotoResolver:
    """Resolves integer IR photo numbers to thermal and paired visual photo files."""

    def __init__(
        self,
        ir_dir: Path | str,
        camera_config: CameraConfig | None = None,
        warnings: list[str] | None = None,
    ) -> None:
        raw_path = Path(ir_dir)
        self.ir_dir: Path = self._resolve_ir_directory(raw_path)
        self.camera_config: CameraConfig = camera_config or CameraConfig()
        self.warnings: list[str] = warnings if warnings is not None else []
        self._cached_ir: dict[int, Path] = {}
        self._cached_visual: dict[int, Path] = {}
        self._indexed: bool = False

    @staticmethod
    def _resolve_ir_directory(path: Path) -> Path:
        """Resolve directory to RAW DATA/IR if nested under substation root."""
        if (path / "RAW DATA" / "IR").is_dir():
            return path / "RAW DATA" / "IR"
        if (path / "IR").is_dir():
            return path / "IR"
        return path

    def _index_directory(self) -> None:
        """Scan directory and index IR and visual photos by photo number."""
        if self._indexed:
            return
        self._indexed = True

        if not self.ir_dir.exists() or not self.ir_dir.is_dir():
            return

        try:
            entries = [
                p
                for p in self.ir_dir.iterdir()
                if p.is_file() and p.suffix.lower() in VALID_IMAGE_EXTENSIONS
            ]
        except OSError as ex:
            logger.warning("Failed to list files in IR directory %s: %s", self.ir_dir, ex)
            return

        for p in entries:
            # 1. Check for visual photo first
            vis_num = self._extract_visual_photo_number(p.name, self.camera_config)
            if vis_num is not None:
                if (
                    vis_num not in self._cached_visual
                    or len(p.name) < len(self._cached_visual[vis_num].name)
                ):
                    self._cached_visual[vis_num] = p
                continue

            # 2. Check for IR thermal photo
            ir_num = self._extract_ir_photo_number(p.name, self.camera_config.ir_prefix)
            if ir_num is not None:
                if (
                    ir_num not in self._cached_ir
                    or len(p.name) < len(self._cached_ir[ir_num].name)
                ):
                    self._cached_ir[ir_num] = p

    @classmethod
    def _extract_digits_after_prefix(cls, name_upper: str, prefix_upper: str) -> int | None:
        """Extract photo sequence number after prefix, handling YYYYMMDD date-stamped stems."""
        stem = name_upper.rsplit(".", 1)[0] if "." in name_upper else name_upper
        if not stem.startswith(prefix_upper):
            return None
        after = stem[len(prefix_upper):]
        digits = re.findall(r"\d+", after)
        if not digits:
            return None
        if len(digits) > 1 and len(digits[0]) == 8:
            return int(digits[-1])
        return int(digits[0])

    @classmethod
    def _extract_visual_photo_number(
        cls,
        filename: str,
        camera_config: CameraConfig,
    ) -> int | None:
        """Extract photo number from visual photo filename governed by CameraConfig."""
        name_upper = filename.upper()

        # 1. Dual-pair mode: e.g. DC_0291.jpg maps to IR 290
        if camera_config.ir_mode == "dual_pair":
            dc_prefix = camera_config.dc_prefix
            if dc_prefix and name_upper.startswith(dc_prefix.upper()):
                dc_num = cls._extract_digits_after_prefix(name_upper, dc_prefix.upper())
                if dc_num is not None:
                    return dc_num - camera_config.dc_offset
            return None

        # 2. Single mode: e.g. FLIR0290*-photo*.jpg, FLIR0290- photo.jpg, FLIR0290-DC.jpg
        visual_marker = re.search(r"[\s\-_.]*(?:PHOTO|DC)", name_upper)
        if visual_marker:
            before_marker = name_upper[: visual_marker.start()]
            num = cls._extract_digits_after_prefix(before_marker, camera_config.ir_prefix.upper())
            if num is not None:
                return num

        return None

    @classmethod
    def _extract_ir_photo_number(cls, filename: str, ir_prefix: str) -> int | None:
        """Extract photo number from thermal IR photo filename."""
        name_upper = filename.upper()
        # Visual markers indicate visual inspection photos, not thermal images
        if re.search(r"[\s\-_.]*(?:PHOTO|DC)", name_upper):
            return None
        return cls._extract_digits_after_prefix(name_upper, ir_prefix.upper())

    def resolve_ir_photo(
        self,
        photo_number: int | str | None,
        *,
        warn_if_missing: bool = True,
    ) -> str:
        """Resolve integer IR photo number to thermal image file path on disk.

        Returns file path string, or empty string '' if missing on disk.
        """
        num = self._coerce_photo_number(photo_number)
        if num is None:
            return ""

        self._index_directory()

        if num in self._cached_ir:
            return self._cached_ir[num].as_posix()

        if warn_if_missing:
            msg = f"IR photo {self.camera_config.ir_prefix}{num:04d} missing on disk in {self.ir_dir}"
            logger.warning(msg)
            self.warnings.append(msg)

        return ""

    def resolve_visual_photo(
        self,
        photo_number: int | str | None,
        *,
        warn_if_missing: bool = True,
    ) -> str:
        """Discover paired visual inspection photo matching FLIRxxxx*-photo*.jpg.

        Returns file path string, or empty string '' with warning if missing on disk.
        """
        num = self._coerce_photo_number(photo_number)
        if num is None:
            return ""

        self._index_directory()

        if num in self._cached_visual:
            return self._cached_visual[num].as_posix()

        if warn_if_missing:
            msg = f"Paired visual photo for IR photo {self.camera_config.ir_prefix}{num:04d} missing on disk in {self.ir_dir}"
            logger.warning(msg)
            self.warnings.append(msg)

        return ""

    def resolve_pair(
        self,
        photo_number: int | str | None,
        *,
        warn_if_missing: bool = True,
    ) -> PhotoPair:
        """Resolve both thermal IR photo and paired visual inspection photo."""
        num = self._coerce_photo_number(photo_number)
        if num is None:
            return PhotoPair(photo_number=None)

        ir_str = self.resolve_ir_photo(num, warn_if_missing=warn_if_missing)
        vis_str = self.resolve_visual_photo(num, warn_if_missing=warn_if_missing)

        ir_path = Path(ir_str) if ir_str else None
        vis_path = Path(vis_str) if vis_str else None

        return PhotoPair(
            ir_photo=ir_str,
            visual_photo=vis_str,
            photo_number=num,
            ir_path=ir_path,
            visual_path=vis_path,
        )

    def resolve_cable_split_photo(
        self,
        photo_number: int | str | Sequence[int] | None = None,
        *,
        warn_if_missing: bool = False,
    ) -> str:
        """Resolve secondary cable split IR photo per ADR 0004 & D27.

        Safely falls back to empty string '' if missing or unpopulated.
        """
        pair = self.resolve_cable_split_pair(photo_number, warn_if_missing=warn_if_missing)
        return pair.ir_photo

    def resolve_cable_split_pair(
        self,
        photo_number: int | str | Sequence[int] | None = None,
        *,
        warn_if_missing: bool = False,
    ) -> PhotoPair:
        """Resolve secondary cable split photo pair per ADR 0004 & D27.

        If photo_number is a sequence with >= 2 items (e.g. (290, 291)), resolves the secondary photo.
        If photo_number is None or has <= 1 photo, safely falls back to empty PhotoPair('', '').
        """
        target_num: int | None = None
        if isinstance(photo_number, (list, tuple)):
            if len(photo_number) >= 2:
                target_num = self._coerce_photo_number(photo_number[1])
            else:
                return PhotoPair()
        elif photo_number is not None:
            target_num = self._coerce_photo_number(photo_number)

        if target_num is None:
            return PhotoPair()

        return self.resolve_pair(target_num, warn_if_missing=warn_if_missing)

    def resolve_tx_overview_top_photo(
        self,
        photo_number: int | str | None = None,
        *,
        warn_if_missing: bool = False,
    ) -> str:
        """Resolve transformer overview top photo per D48 fallback."""
        num = self._coerce_photo_number(photo_number)
        if num is None:
            return ""
        return self.resolve_ir_photo(num, warn_if_missing=warn_if_missing)

    def resolve_tx_overview_top_pair(
        self,
        photo_number: int | str | None = None,
        *,
        warn_if_missing: bool = False,
    ) -> PhotoPair:
        """Resolve transformer overview top photo pair per D48 fallback."""
        num = self._coerce_photo_number(photo_number)
        if num is None:
            return PhotoPair()
        return self.resolve_pair(num, warn_if_missing=warn_if_missing)

    def resolve_ir_path(self, photo_number: int | str | None) -> Path | None:
        """Resolve integer photo number to Path object, or None if missing."""
        p_str = self.resolve_ir_photo(photo_number)
        return Path(p_str) if p_str else None

    def resolve_visual_path(self, photo_number: int | str | None) -> Path | None:
        """Resolve paired visual photo to Path object, or None if missing."""
        p_str = self.resolve_visual_photo(photo_number)
        return Path(p_str) if p_str else None

    @staticmethod
    def _coerce_photo_number(val: int | str | None) -> int | None:
        """Safely coerce value into positive integer photo number."""
        if val is None:
            return None
        if isinstance(val, int):
            return val if val > 0 else None
        if isinstance(val, float):
            if math.isnan(val) or math.isinf(val):
                return None
            n = int(val)
            return n if n > 0 else None
        if isinstance(val, str):
            val_clean = val.strip()
            if not val_clean:
                return None
            try:
                n = int(val_clean)
                return n if n > 0 else None
            except ValueError:
                return None
        return None
