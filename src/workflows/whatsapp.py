"""WhatsApp report workflow orchestrator for Pahang CLI."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
from docxtpl import DocxTemplate

import config
from src.core.normalizers import format_date_cbm, normalize_date_str, normalize_for_report
from src.project.environment import ProjectEnvironment
from src.project.storage import get_next_file_number
from src.whatsapp.models import WhatsAppReportResources
from src.workflows.models import ProgressSink, WhatsAppReportRequest, WhatsAppReportResult

QUALIFYING_DOCX_PATTERN = re.compile(
    r"^(\d+)\.?\s*(.*?)(?:\s*\(([^()]+)\))?\.docx$",
    re.IGNORECASE,
)

DEFECT_SUFFIX_PATTERN = re.compile(
    r"^(?:IR|US|TEV|VI)(?:\s*\+\s*(?:IR|US|TEV|VI))*$",
    re.IGNORECASE,
)

WHATSAPP_ACTIVITY_11KV = "CBM 11kV"
WHATSAPP_ACTIVITY_33KV = "CBM 33KV"

WHATSAPP_PENYELIA_11KV = "AZZAD"
WHATSAPP_PENYELIA_33KV = "ZULHUSNI"

WHATSAPP_LINKS_11KV = {
    "laporan": (
        "https://mytnb-my.sharepoint.com/:f:/r/personal/sbumdiagnostictimur_tnb_com_my/Documents/"
        "SBUM%20DIAGNOSTIC%20EAST/CBM%20SS/ACTIVITY%20CBA%2011kV/PAHANG/REPORT%20CBA%20SUBSTATION?csf=1&web=1&e=SR9cCq"
    ),
    "engr": (
        "https://mytnb-my.sharepoint.com/:f:/r/personal/sbumdiagnostictimur_tnb_com_my/Documents/"
        "SBUM%20DIAGNOSTIC%20EAST/CBM%20SS/ACTIVITY%20CBA%2011kV/PAHANG/ENGR?csf=1&web=1&e=x085wi"
    ),
}

WHATSAPP_LINKS_33KV = {
    "laporan": (
        "https://mytnb-my.sharepoint.com/personal/sbumdiagnostictimur_tnb_com_my/_layouts/15/onedrive.aspx?"
        "id=%2Fpersonal%2Fsbumdiagnostictimur%5Ftnb%5Fcom%5Fmy%2FDocuments%2FSBUM%20DIAGNOSTIC%20EAST%2F"
        "CBM%20SS%2FACTIVITY%20CBA%2033kV%2FPAHANG%2FREPORT%20CBA%20SUBSTATION%2FPMU%2EPPU%2ESSU%2F2026&"
        "viewid=a535b4f0%2D697a%2D40a6%2D9dda%2D6f362e3406c7&ga=1"
    ),
    "engr": (
        "https://mytnb-my.sharepoint.com/personal/sbumdiagnostictimur_tnb_com_my/_layouts/15/onedrive.aspx?"
        "id=%2Fpersonal%2Fsbumdiagnostictimur%5Ftnb%5Fcom%5Fmy%2FDocuments%2FSBUM%20DIAGNOSTIC%20EAST%2F"
        "CBM%20SS%2FACTIVITY%20CBA%2033kV%2FPAHANG%2FENGR&"
        "viewid=a535b4f0%2D697a%2D40a6%2D9dda%2D6f362e3406c7&ga=1"
    ),
}


@dataclass(frozen=True)
class WhatsAppRawTuple:
    """Raw data entities extracted for WhatsApp report workflow."""

    substation_docx_files: list[Path]
    total_pe_df: pd.DataFrame
    resources: WhatsAppReportResources
    station_hints: dict[Path, str] = field(default_factory=dict)
    folder_date: str | None = None


@dataclass(frozen=True)
class WhatsAppTargetEntity:
    """Target substation record parsed and validated for WhatsApp report."""

    substation_number: int
    substation_name: str
    defect: str
    msms: str
    raw_date: Any
    fl_number: str
    station: str = ""


@dataclass(frozen=True)
class WhatsAppReportPlan:
    """Immutable transformation plan for rendering WhatsApp report."""

    template_path: Path
    save_dir: Path
    context: dict[str, Any]
    substations_count: int
    station_name: str
    report_date: str
    voltage_type: str = "11kV"


def _generate_date_patterns(clean_date: str) -> set[str]:
    patterns = {clean_date}
    m_date = re.match(r"^0?(\d+)-0?(\d+)-(\d{4})$", clean_date)
    if m_date:
        d_i, m_i, y_s = int(m_date.group(1)), int(m_date.group(2)), m_date.group(3)
        patterns.add(f"{d_i:02d}-{m_i:02d}-{y_s}")
        patterns.add(f"{d_i}-{m_i}-{y_s}")
        patterns.add(f"{d_i:02d}-{m_i}-{y_s}")
        patterns.add(f"{d_i}-{m_i:02d}-{y_s}")
    return patterns


class WhatsAppReportPreflightGuard:
    """Pre-flight validation stage for WhatsApp report workflow."""

    @staticmethod
    def _normalize_date_str(date_input: str | Path) -> str:
        s = str(date_input).strip()
        s_clean = re.sub(r"\s*([/\\-])\s*", r"\1", s).rstrip("/\\").strip()
        norm = normalize_date_str(s_clean.replace("\\", "/"))
        if norm and re.match(r"^\d{2}-\d{2}-\d{4}$", norm):
            return norm
        p = Path(s_clean)
        norm_name = normalize_date_str(p.name.replace("\\", "/"))
        if norm_name and re.match(r"^\d{2}-\d{2}-\d{4}$", norm_name):
            return norm_name
        for part in reversed(p.parts):
            norm_part = normalize_date_str(part.replace("\\", "/"))
            if norm_part and re.match(r"^\d{2}-\d{2}-\d{4}$", norm_part):
                return norm_part
        return p.name.replace("/", "-")

    def validate(self, env: ProjectEnvironment, request: WhatsAppReportRequest) -> None:
        report_dir = request.report_dir
        if report_dir is None:
            raise ValueError("report_dir cannot be None. It must be provided in the request.")

        report_dir_path = Path(report_dir)
        resources = env.get_whatsapp_report_resources()
        voltage_type = getattr(env, "voltage_type", "11kV") or "11kV"

        if voltage_type == "33kV":
            target_date = self._normalize_date_str(str(report_dir))
            matching_files = self._find_qualifying_33kv(
                resources.quick_report_dir, target_date, report_dir_path
            )
            if not matching_files:
                clean_target_date = target_date.replace("/", "-")
                date_patterns = _generate_date_patterns(clean_target_date)

                date_dir_exists = (
                    (report_dir_path.exists() and report_dir_path.is_dir())
                    or (
                        resources.quick_report_dir.exists()
                        and any(
                            any(p.is_dir() for p in resources.quick_report_dir.rglob(pat))
                            for pat in date_patterns
                        )
                    )
                )
                if not date_dir_exists:
                    raise FileNotFoundError(f"Directory not found: {report_dir}")
                raise ValueError(f"No qualifying PE DOCX files found for date {target_date}")
        else:
            if not report_dir_path.exists() or not report_dir_path.is_dir():
                raise FileNotFoundError(f"Directory not found: {report_dir}")

            has_qualifying = False
            for child in report_dir_path.iterdir():
                if child.is_file() and child.suffix.lower() == ".docx":
                    if QUALIFYING_DOCX_PATTERN.match(child.name):
                        has_qualifying = True
                        break
            if not has_qualifying:
                raise ValueError(f"No qualifying PE DOCX files found in {report_dir_path}")

        if not resources.template_path.exists():
            raise FileNotFoundError(f"Template file not found at {resources.template_path}")

        if not resources.total_pe_path.exists():
            raise FileNotFoundError(f"TOTAL PE workbook not found at {resources.total_pe_path}")

        try:
            with pd.ExcelFile(resources.total_pe_path) as xls:
                if "DataCycle1" not in xls.sheet_names:
                    raise RuntimeError("DataCycle1 sheet not found in TOTAL PE workbook")
        except Exception as e:
            if isinstance(e, RuntimeError):
                raise
            raise RuntimeError("DataCycle1 sheet not found in TOTAL PE workbook") from e

    def _find_qualifying_33kv(
        self, quick_report_dir: Path, target_date: str, provided_dir: Path | None = None
    ) -> list[Path]:
        clean_date = target_date.replace("/", "-")
        date_patterns = _generate_date_patterns(clean_date)

        candidate_dirs: list[Path] = []
        seen_dirs: set[Path] = set()

        if provided_dir:
            p_dir = Path(provided_dir)
            if p_dir.exists() and p_dir.is_dir():
                resolved = p_dir.resolve()
                if resolved not in seen_dirs:
                    seen_dirs.add(resolved)
                    candidate_dirs.append(p_dir)

        if quick_report_dir.exists():
            for pat in date_patterns:
                for d in quick_report_dir.rglob(pat):
                    if d.is_dir():
                        resolved = d.resolve()
                        if resolved not in seen_dirs:
                            seen_dirs.add(resolved)
                            candidate_dirs.append(d)

        qualifying = []
        for d in candidate_dirs:
            for child in d.iterdir():
                if child.is_file() and child.suffix.lower() == ".docx":
                    if QUALIFYING_DOCX_PATTERN.match(child.name):
                        qualifying.append(child)
        return qualifying


class WhatsAppReportExtractor:
    """Pure Read I/O extraction stage for WhatsApp report workflow."""

    def extract(self, env: ProjectEnvironment, request: WhatsAppReportRequest) -> WhatsAppRawTuple:
        resources = env.get_whatsapp_report_resources()
        report_dir_path = Path(request.report_dir)  # type: ignore[arg-type]
        voltage_type = getattr(env, "voltage_type", "11kV") or "11kV"

        if voltage_type == "33kV":
            target_date = WhatsAppReportPreflightGuard._normalize_date_str(str(request.report_dir))
            station_mapping = getattr(resources, "station_mapping", {}) if resources else {}
            substation_docx_files, station_hints = self._scan_qualifying_docx_files_33kv(
                resources.quick_report_dir, target_date, report_dir_path, station_mapping
            )
            folder_date = target_date
        else:
            substation_docx_files = self._scan_qualifying_docx_files(report_dir_path)
            station_hints = {}
            norm_folder = normalize_date_str(report_dir_path.name.replace("\\", "/"))
            folder_date = (
                norm_folder
                if (norm_folder and re.match(r"^\d{2}-\d{2}-\d{4}$", norm_folder))
                else (
                    report_dir_path.name
                    if re.match(r"^\d{1,2}[/-]\d{1,2}[/-]\d{4}$", report_dir_path.name)
                    else None
                )
            )

        total_pe_df = self._load_total_pe_dataframe(resources.total_pe_path)

        return WhatsAppRawTuple(
            substation_docx_files=substation_docx_files,
            total_pe_df=total_pe_df,
            resources=resources,
            station_hints=station_hints,
            folder_date=folder_date,
        )

    def _scan_qualifying_docx_files(self, report_dir_path: Path) -> list[Path]:
        substation_docx_files = []
        for child in report_dir_path.iterdir():
            if child.is_file() and child.suffix.lower() == ".docx":
                if QUALIFYING_DOCX_PATTERN.match(child.name):
                    substation_docx_files.append(child)

        substation_docx_files.sort(
            key=lambda p: int(QUALIFYING_DOCX_PATTERN.match(p.name).group(1))  # type: ignore[union-attr]
        )
        return substation_docx_files

    def _scan_qualifying_docx_files_33kv(
        self,
        quick_report_dir: Path,
        target_date: str,
        provided_dir: Path | None = None,
        station_mapping: dict[str, str] | None = None,
    ) -> tuple[list[Path], dict[Path, str]]:
        clean_date = target_date.replace("/", "-")
        date_patterns = _generate_date_patterns(clean_date)

        candidate_dirs: list[Path] = []
        seen_dirs: set[Path] = set()

        if provided_dir:
            p_dir = Path(provided_dir)
            if p_dir.exists() and p_dir.is_dir():
                resolved = p_dir.resolve()
                if resolved not in seen_dirs:
                    seen_dirs.add(resolved)
                    candidate_dirs.append(p_dir)

        if quick_report_dir.exists():
            for pat in date_patterns:
                for d in quick_report_dir.rglob(pat):
                    if d.is_dir():
                        resolved = d.resolve()
                        if resolved not in seen_dirs:
                            seen_dirs.add(resolved)
                            candidate_dirs.append(d)

        discovered: list[tuple[int, Path, str]] = []
        station_hints: dict[Path, str] = {}
        seen_paths: set[Path] = set()

        known_stations = {v.upper() for v in config.STATION_MAPPING.values()}
        if station_mapping:
            known_stations.update(v.upper() for v in station_mapping.values())
        known_stations.add("LIPIS")

        for d in candidate_dirs:
            station_name = ""
            candidate_parts: list[str] = []
            try:
                if quick_report_dir.exists() and d.resolve().is_relative_to(quick_report_dir.resolve()):
                    rel = d.resolve().relative_to(quick_report_dir.resolve())
                    candidate_parts = list(rel.parts[:-1]) if len(rel.parts) > 1 else list(rel.parts)
            except Exception:
                pass

            if not candidate_parts:
                candidate_parts = list(d.parts[:-1])

            # Search candidate parts for a known station in reverse (nearest ancestor first)
            for part in reversed(candidate_parts):
                p_upper = part.upper().strip()
                if p_upper in known_stations:
                    station_name = p_upper
                    break

            if station_name == "LIPIS":
                station_name = "KUALA LIPIS"

            for child in d.iterdir():
                if child.is_file() and child.suffix.lower() == ".docx":
                    m = QUALIFYING_DOCX_PATTERN.match(child.name)
                    if m and child.resolve() not in seen_paths:
                        seen_paths.add(child.resolve())
                        pe_num = int(m.group(1))
                        discovered.append((pe_num, child, station_name))
                        if station_name:
                            station_hints[child] = station_name

        # Sort aggregated documents by integer PE number
        discovered.sort(key=lambda x: (x[0], str(x[1])))
        files = [item[1] for item in discovered]
        return files, station_hints

    def _load_total_pe_dataframe(self, total_pe_path: Path) -> pd.DataFrame:
        return pd.read_excel(
            total_pe_path,
            sheet_name="DataCycle1",
        )


class WhatsAppReportFilter:
    """Pure validation and predicate logic stage for WhatsApp report workflow."""

    def filter(self, raw: WhatsAppRawTuple) -> list[WhatsAppTargetEntity]:
        targets = []
        station_hints = raw.station_hints or {}
        station_mapping = raw.resources.station_mapping if raw.resources else {}

        for docx_path in raw.substation_docx_files:
            parsed = self._parse_docx_target(docx_path)
            if not parsed:
                continue

            substation_number, stem_name, defect_val = parsed
            sub_name, wo_val, raw_date, fl_num = self._lookup_substation_row(
                raw.total_pe_df, substation_number, stem_name
            )

            # Fallback to folder date if raw_date is unpopulated or cannot be parsed
            if (raw_date is None or format_date_cbm(raw_date) == "-") and raw.folder_date:
                raw_date = raw.folder_date

            # Determine station: prefer authoritative FL number code mapping, then station hints
            station = ""
            if fl_num:
                station_code = fl_num[:4].upper() if len(fl_num) >= 4 else fl_num.upper()
                station = station_mapping.get(station_code) or config.STATION_MAPPING.get(station_code, "")
            if not station:
                station = station_hints.get(docx_path, "")
            if station.upper() == "LIPIS":
                station = "KUALA LIPIS"
            station = station.strip().upper()

            targets.append(
                WhatsAppTargetEntity(
                    substation_number=substation_number,
                    substation_name=sub_name,
                    defect=defect_val,
                    msms=wo_val,
                    raw_date=raw_date,
                    fl_number=fl_num,
                    station=station,
                )
            )

        if not any(t.raw_date is not None for t in targets):
            raise ValueError("No valid inspection dates found in PE reports")

        return targets

    def _parse_docx_target(self, docx_path: Path) -> tuple[int, str, str] | None:
        match = QUALIFYING_DOCX_PATTERN.match(docx_path.name)
        if not match:
            return None

        prefix_str, stem_name, suffix_str = match.groups()
        substation_number = int(prefix_str)
        stem = stem_name.strip() if stem_name else ""

        if suffix_str and suffix_str.strip():
            candidate = suffix_str.strip()
            if DEFECT_SUFFIX_PATTERN.match(candidate):
                defect_val = re.sub(r"\s*\+\s*", "+", candidate.upper())
            else:
                # Suffix inside parentheses is not a defect indicator (e.g. "(SSU CAMEL POWER)", "(OLD)")
                # Retain it as part of the substation name stem
                stem = f"{stem} ({candidate})" if stem else f"({candidate})"
                defect_val = "-"
        else:
            defect_val = "-"

        return substation_number, stem, defect_val

    def _lookup_substation_row(
        self, total_pe_df: pd.DataFrame, substation_number: int, stem_name: str
    ) -> tuple[str, str, Any, str]:
        def _parse_pe_int(val: Any) -> int:
            if pd.isna(val):
                return -1
            try:
                return int(float(str(val).strip()))
            except (ValueError, TypeError):
                return -1

        pe_col = next((c for c in total_pe_df.columns if str(c).strip().upper() in ["PE NO", "PE_NO", "PE NO.", "PE", "NO PE", "NO. PE"]), "PE NO")
        name_col = next((c for c in total_pe_df.columns if str(c).strip().upper() in ["SUBSTATION NAME", "STATION NAME", "NAMA PE", "NAMA STESEN", "SUBSTATION"]), "SUBSTATION NAME")
        wo_col = next((c for c in total_pe_df.columns if str(c).strip().upper() in ["WO", "WONUM", "WORK ORDER", "NO WO"]), "WO")
        date_col = next((c for c in total_pe_df.columns if str(c).strip().upper() in ["DATE", "TARIKH", "TARIKH PEMERIKSAAN", "TARIKH LAWATAN", "INSPECTION DATE", "DATE INSPECTED"]), "DATE")
        fl_col = next((c for c in total_pe_df.columns if str(c).strip().upper() in ["FL NUMBER", "FL_NUMBER", "FL", "FUNCTIONAL LOCATION"]), "FL NUMBER")

        substation_matches = total_pe_df[
            total_pe_df[pe_col].apply(_parse_pe_int) == substation_number
        ] if pe_col in total_pe_df.columns else pd.DataFrame()

        if not substation_matches.empty:
            row = substation_matches.iloc[0]
            sub_name = (
                str(row[name_col])
                if name_col in row and pd.notna(row[name_col]) and str(row[name_col]).strip()
                else stem_name.strip()
            )
            wo_val = normalize_for_report(row[wo_col]) if wo_col in row else "-"
            raw_date_val = row[date_col] if (date_col in row and pd.notna(row[date_col])) else None
            if raw_date_val is not None:
                s_val = str(raw_date_val).strip()
                if not s_val or s_val.upper() in ("-", "NONE", "N/A", "NAT", "NULL"):
                    raw_date = None
                else:
                    raw_date = raw_date_val
            else:
                raw_date = None
            fl_num = str(row[fl_col]).strip() if (fl_col in row and pd.notna(row[fl_col])) else ""
        else:
            sub_name = stem_name.strip() if stem_name and stem_name.strip() else f"PE {substation_number}"
            wo_val = "-"
            raw_date = None
            fl_num = ""

        return sub_name, wo_val, raw_date, fl_num


class WhatsAppReportTransformer:
    """Pure transformation and plan construction stage for WhatsApp report workflow."""

    def transform(
        self, targets: list[WhatsAppTargetEntity], resources: WhatsAppReportResources
    ) -> WhatsAppReportPlan:
        voltage_type = getattr(resources, "voltage_type", "11kV") or "11kV"
        is_33kv = (voltage_type == "33kV")

        # 1. Resolve inspection date
        report_date = None
        for t in targets:
            if report_date is None and t.raw_date is not None:
                formatted_dt = format_date_cbm(t.raw_date)
                if formatted_dt != "-":
                    report_date = formatted_dt

        if report_date is None:
            raise ValueError("No valid inspection dates found in PE reports")

        # 2. Resolve stations for targets
        station_mapping = resources.station_mapping if resources else {}
        target_station_pairs: list[tuple[WhatsAppTargetEntity, str]] = []
        for t in targets:
            st = t.station.strip().upper() if t.station else ""
            if not st and t.fl_number:
                code = t.fl_number[:4].upper() if len(t.fl_number) >= 4 else t.fl_number.upper()
                st = station_mapping.get(code) or config.STATION_MAPPING.get(code, f"UNKNOWN ({code})" if code else "UNKNOWN STATION")
            if not st:
                st = "UNKNOWN STATION"
            if st == "LIPIS":
                st = "KUALA LIPIS"
            target_station_pairs.append((t, st))

        # 3. Distinct stations in order of appearance (ordered by earliest PE number)
        distinct_stations: list[str] = []
        for _, st in target_station_pairs:
            if st not in distinct_stations:
                distinct_stations.append(st)

        is_multi_station = len(distinct_stations) > 1
        if is_multi_station:
            station_header = "/".join(distinct_stations)
        elif len(distinct_stations) == 1:
            station_header = distinct_stations[0]
        else:
            station_header = "UNKNOWN STATION"

        # 4. Programmatic links, activity, penyelia based on voltage_type
        if is_33kv:
            activity = WHATSAPP_ACTIVITY_33KV
            penyelia = WHATSAPP_PENYELIA_33KV
            link_laporan = WHATSAPP_LINKS_33KV["laporan"]
            link_engr = WHATSAPP_LINKS_33KV["engr"]
        else:
            activity = WHATSAPP_ACTIVITY_11KV
            penyelia = WHATSAPP_PENYELIA_11KV
            link_laporan = WHATSAPP_LINKS_11KV["laporan"]
            link_engr = WHATSAPP_LINKS_11KV["engr"]

        # 5. Group items by station with continuous 1-based sequential numbering
        station_groups: list[dict[str, Any]] = []
        items: list[dict[str, Any]] = []
        item_counter = 1

        for st in distinct_stations:
            st_targets = [t for t, t_st in target_station_pairs if t_st == st]
            st_targets.sort(key=lambda t: t.substation_number)

            group_data: dict[str, Any] = {
                "station": st,
                "substations": [],
                "items": [],
            }
            station_groups.append(group_data)

            for i, t in enumerate(st_targets):
                item_data = {
                    "name": t.substation_name,
                    "defect": t.defect,
                    "msms": t.msms,
                    "index": item_counter,
                    "station": st,
                    "station_header": st if (is_multi_station and i == 0) else None,
                }
                items.append(item_data)
                group_data["substations"].append(item_data)
                group_data["items"].append(item_data)
                item_counter += 1

        context = {
            "activity": activity,
            "date": report_date,
            "station": station_header,
            "penyelia": penyelia,
            "supervisor": penyelia,
            "items": items,
            "station_groups": station_groups,
            "show_subheadings": is_multi_station,
            "link_laporan": link_laporan,
            "link_engr": link_engr,
        }

        return WhatsAppReportPlan(
            template_path=resources.template_path,
            save_dir=resources.save_dir,
            context=context,
            substations_count=len(items),
            station_name=station_header,
            report_date=report_date,
            voltage_type=voltage_type,
        )


class WhatsAppReportLoader:
    """Pure docx template rendering and disk write stage for WhatsApp report workflow."""

    def load(self, plan: WhatsAppReportPlan) -> Path:
        doc = DocxTemplate(plan.template_path)
        
        # Prepare render context with XML-safe URLs for docxtpl
        render_context = dict(plan.context)
        for link_key in ("link_laporan", "link_engr"):
            if link_key in render_context and isinstance(render_context[link_key], str):
                val = render_context[link_key]
                val = val.replace("&amp;", "&").replace("&", "&amp;")
                render_context[link_key] = val
        doc.render(render_context)

        # Update underlying hyperlink relationships if present
        try:
            for r in doc.docx.part.rels.values():
                if "hyperlink" in getattr(r, "reltype", ""):
                    target_ref = getattr(r, "target_ref", "")
                    if "REPORT" in target_ref or "laporan" in target_ref.lower():
                        r._target = plan.context.get("link_laporan", target_ref)
                    elif "ENGR" in target_ref or "engr" in target_ref.lower():
                        r._target = plan.context.get("link_engr", target_ref)
        except Exception:
            pass

        plan.save_dir.mkdir(parents=True, exist_ok=True)
        next_num = get_next_file_number(plan.save_dir)
        clean_date = plan.report_date.replace("/", "-")
        if plan.voltage_type == "33kV":
            output_path = plan.save_dir / f"{next_num:02d}. {clean_date}.docx"
        else:
            output_path = plan.save_dir / f"{next_num:02d}. {plan.station_name} {clean_date}.docx"

        doc.save(output_path)
        return output_path


class WhatsAppReportAuditor:
    """Verification and history logging stage for WhatsApp report workflow."""

    def audit(self, plan: WhatsAppReportPlan, output_path: Path) -> WhatsAppReportResult:
        if not output_path.exists():
            raise RuntimeError(f"Output file was not created at {output_path}")
        if output_path.stat().st_size == 0:
            raise RuntimeError(f"Output file at {output_path} is empty (0 bytes)")
            
        return WhatsAppReportResult(
            substations_count=plan.substations_count,
            output_path=output_path,
        )


class WhatsAppReportWorkflow:
    """Orchestrates WhatsApp summary report generation.

    Resilience Policy: atomic
    All-or-nothing execution. Any unhandled stage exception aborts the entire workflow.
    """

    def __init__(
        self,
        preflight_guard: WhatsAppReportPreflightGuard | None = None,
        extractor: WhatsAppReportExtractor | None = None,
        filter_stage: WhatsAppReportFilter | None = None,
        transformer: WhatsAppReportTransformer | None = None,
        loader: WhatsAppReportLoader | None = None,
        auditor: WhatsAppReportAuditor | None = None,
    ) -> None:
        self.preflight_guard = preflight_guard or WhatsAppReportPreflightGuard()
        self.extractor = extractor or WhatsAppReportExtractor()
        self.filter_stage = filter_stage or WhatsAppReportFilter()
        self.transformer = transformer or WhatsAppReportTransformer()
        self.loader = loader or WhatsAppReportLoader()
        self.auditor = auditor or WhatsAppReportAuditor()

    def execute(
        self, env: ProjectEnvironment, request: WhatsAppReportRequest
    ) -> WhatsAppReportResult:
        if request.progress_sink:
            request.progress_sink("Validating environment and inputs for WhatsApp report...")

        self.preflight_guard.validate(env, request)

        if request.progress_sink:
            request.progress_sink("Extracting raw PE report files and data...")

        raw_data = self.extractor.extract(env, request)

        if request.progress_sink:
            request.progress_sink("Filtering substation targets...")

        targets = self.filter_stage.filter(raw_data)

        if request.progress_sink:
            request.progress_sink("Building WhatsApp report plan...")

        plan = self.transformer.transform(targets, raw_data.resources)

        if request.progress_sink:
            request.progress_sink("Rendering and saving WhatsApp report document...")

        load_output = self.loader.load(plan)

        if request.progress_sink:
            request.progress_sink("Auditing created report file...")

        result = self.auditor.audit(plan, load_output)
        return result


def run_generate_whatsapp_report(
    env: ProjectEnvironment,
    report_dir: Path | str,
    progress_sink: ProgressSink | None = None,
) -> WhatsAppReportResult:
    """Execute WhatsApp report generation workflow for a specific date/report folder."""
    workflow = WhatsAppReportWorkflow()
    request = WhatsAppReportRequest(report_dir=Path(report_dir), progress_sink=progress_sink)
    return workflow.execute(env, request)

