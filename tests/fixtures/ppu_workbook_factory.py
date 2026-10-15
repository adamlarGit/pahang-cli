"""Shared PPU 33kV testsheet workbook test fixture factory."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence
import openpyxl


_DEFAULT_SENTINEL = object()


def create_ppu_testsheet_workbook(
    path: Path | str | None = None,
    substation_number: int | None = 1,
    substation_name: str = "PPU APMM 33-11kV",
    fl_number: str = "CGBG-PPU-APMM",
    date_val: str | datetime | date = "2026-10-07",
    time_val: str = "10:30 AM",
    ambient_temp: str = "30.5",
    humidity: str = "65%",
    background_tev: str = "5",
    gps_coordinate: str = "3.8123, 103.3214",
    has_33kv: bool = True,
    has_11kv: bool = True,
    panels_33kv: int | Sequence[Mapping[str, Any]] = 3,
    panels_11kv: int | Sequence[Mapping[str, Any]] = 3,
    extra_panels_33kv: Sequence[Sequence[Mapping[str, Any]]] = (),
    extra_panels_11kv: Sequence[Sequence[Mapping[str, Any]]] = (),
    swg_33kv_details: Mapping[str, Any] | None = None,
    swg_11kv_details: Mapping[str, Any] | None = None,
    overview_rhs_photos_33kv: Sequence[int] = (),
    overview_lhs_photos_33kv: Sequence[int] = (),
    overview_rhs_photos_11kv: Sequence[int] = (),
    overview_lhs_photos_11kv: Sequence[int] = (),
    visual_checklist_items: Sequence[Mapping[str, Any]] | None = None,
    other_findings: Sequence[str] = (),
    raw_photo_bounds: Mapping[str, Any] | None = None,
    v2_substation_num_33kv: Any = _DEFAULT_SENTINEL,
    v2_substation_num_11kv: Any = _DEFAULT_SENTINEL,
    include_tx_sheet: bool = True,
    tx_sheet_name: str = "TX",
    vi_sheet_name: str = "Visual Inspec.",
    transformer_ratings: Sequence[str] = (),
) -> openpyxl.Workbook:
    """Build a synthetic PPU 33kV/11kV openpyxl workbook for testing."""
    wb = openpyxl.Workbook()
    # Remove default sheet once we add real sheets
    default_sheet = wb.active

    def _populate_switchgear_sheet(
        ws: openpyxl.worksheet.worksheet.Worksheet,
        voltage_label: str,
        panels_input: int | Sequence[Mapping[str, Any]],
        swg_details: Mapping[str, Any] | None,
        v2_val: Any,
        overview_rhs: Sequence[int],
        overview_lhs: Sequence[int],
    ) -> None:
        # Cell V2
        if v2_val is not None:
            ws["V2"] = v2_val

        # Metadata Header
        ws["D6"] = substation_name
        ws["D7"] = fl_number
        ws["D8"] = date_val
        ws["D9"] = time_val
        ws["U6"] = ambient_temp
        ws["U7"] = humidity
        ws["U8"] = background_tev

        # Switchgear Details (L6..L11)
        details = swg_details or {}
        ws["L6"] = details.get("manufacturer", "TAMCO")
        ws["L7"] = details.get("manufactured_year", "2020" if voltage_label == "33kV" else "2018")
        ws["L8"] = details.get("model", "GV3" if voltage_label == "33kV" else "VH3")
        ws["L9"] = details.get("serial_no", f"SN-{voltage_label}-001")
        ws["L10"] = details.get("switchgear_type", "GIS" if voltage_label == "33kV" else "VCB")
        ws["L11"] = details.get("rating", "1250A" if voltage_label == "33kV" else "630A")

        # Normalize panels list
        panel_specs: list[Mapping[str, Any]]
        if isinstance(panels_input, int):
            panel_specs = [
                {
                    "feeder_no": f"{'3P' if voltage_label == '33kV' else '1K'}{i + 1}",
                    "name": f"FEEDER {voltage_label} {i + 1}",
                    "status": "CLOSE",
                    "load_amp": f"{100 + i * 20}A",
                    "cable_type": "XLPE 1C 500mm2" if voltage_label == "33kV" else "XLPE 3C 240mm2",
                    "heater_amp": "0.5A",
                    "panel_type": "GIS" if voltage_label == "33kV" else "VCB",
                    "breaker_serial": f"CB-{voltage_label}-{i + 1}",
                    "breaker_photo": 100 + i * 10 + 1,
                    "cable_photo": 100 + i * 10 + 2,
                    "busbar_photo": 100 + i * 10 + 3,
                    "pt_photo": 100 + i * 10 + 4,
                    "cable_entry_photo": 100 + i * 10 + 5,
                    "link_box_photo": 100 + i * 10 + 6,
                }
                for i in range(panels_input)
            ]
        else:
            panel_specs = list(panels_input)

        # Write panels (stride = 6 rows, starting row 15)
        for idx, p in enumerate(panel_specs):
            if idx >= 8:
                break
            r = 15 + idx * 6
            ws[f"B{r}"] = p.get("feeder_no", "")
            ws[f"C{r}"] = p.get("name", "")
            ws[f"D{r}"] = p.get("status", "CLOSE")
            ws[f"F{r}"] = p.get("load_amp", "")
            ws[f"G{r}"] = p.get("cable_type", "")
            ws[f"H{r}"] = p.get("heater_amp", "")
            ws[f"J{r}"] = p.get("panel_type", "")
            ws[f"V{r}"] = p.get("breaker_serial", "")

            # Photos in Col P (Row 1..6)
            if "breaker_photo" in p and p["breaker_photo"] is not None:
                ws[f"P{r}"] = p["breaker_photo"]
            if "cable_photo" in p and p["cable_photo"] is not None:
                ws[f"P{r + 1}"] = p["cable_photo"]
            if "busbar_photo" in p and p["busbar_photo"] is not None:
                ws[f"P{r + 2}"] = p["busbar_photo"]
            if "pt_photo" in p and p["pt_photo"] is not None:
                ws[f"P{r + 3}"] = p["pt_photo"]
            if "cable_entry_photo" in p and p["cable_entry_photo"] is not None:
                ws[f"P{r + 4}"] = p["cable_entry_photo"]
            if "link_box_photo" in p and p["link_box_photo"] is not None:
                ws[f"P{r + 5}"] = p["link_box_photo"]

            # Secondary panel photo in Col Q regex SP: <photo>
            if "secondary_photo" in p and p["secondary_photo"] is not None:
                ws[f"Q{r}"] = f"SP: {p['secondary_photo']}"
            elif "remarks" in p and p["remarks"]:
                ws[f"Q{r}"] = p["remarks"]

            # PT measurement in Row 4
            if p.get("has_pt_measurement"):
                ws[f"K{r + 3}"] = "24.5"

        # Overview Bays (Rows 63-74)
        # RHS Overview (Rows 63-68)
        rhs_labels = ["FRONT", "BACK", "TOP", "CABLE CELLAR", "MBB", "RBB"]
        for o_idx, label in enumerate(rhs_labels):
            row_num = 63 + o_idx
            ws[f"C{row_num}"] = label
            if o_idx < len(overview_rhs):
                ws[f"P{row_num}"] = overview_rhs[o_idx]

        # LHS Overview (Rows 69-74)
        lhs_labels = ["FRONT", "BACK", "TOP", "CABLE CELLAR", "MBB", "RBB"]
        for o_idx, label in enumerate(lhs_labels):
            row_num = 69 + o_idx
            ws[f"C{row_num}"] = label
            if o_idx < len(overview_lhs):
                ws[f"P{row_num}"] = overview_lhs[o_idx]

    # Resolve v2 default values
    v2_33 = substation_number if v2_substation_num_33kv is _DEFAULT_SENTINEL else v2_substation_num_33kv
    v2_11 = substation_number if v2_substation_num_11kv is _DEFAULT_SENTINEL else v2_substation_num_11kv

    # 1. 33kV (Main)
    if has_33kv:
        ws_33 = wb.create_sheet(title="33kV (Main)")
        _populate_switchgear_sheet(
            ws_33,
            voltage_label="33kV",
            panels_input=panels_33kv,
            swg_details=swg_33kv_details,
            v2_val=v2_33,
            overview_rhs=overview_rhs_photos_33kv,
            overview_lhs=overview_lhs_photos_33kv,
        )

        # 33kV (Extra) sheets
        for e_idx, extra_panels in enumerate(extra_panels_33kv):
            sheet_title = "33kV (Extra)" if e_idx == 0 else f"33kV (Extra) ({e_idx + 1})"
            ws_extra = wb.create_sheet(title=sheet_title)
            _populate_switchgear_sheet(
                ws_extra,
                voltage_label="33kV",
                panels_input=extra_panels,
                swg_details=swg_33kv_details,
                v2_val=None,
                overview_rhs=(),
                overview_lhs=(),
            )

    # 2. 11kV (Main)
    if has_11kv:
        ws_11 = wb.create_sheet(title="11kV (Main)")
        _populate_switchgear_sheet(
            ws_11,
            voltage_label="11kV",
            panels_input=panels_11kv,
            swg_details=swg_11kv_details,
            v2_val=v2_11,
            overview_rhs=overview_rhs_photos_11kv,
            overview_lhs=overview_lhs_photos_11kv,
        )

        # 11kV (Extra) sheets
        for e_idx, extra_panels in enumerate(extra_panels_11kv):
            sheet_title = "11kV (Extra)" if e_idx == 0 else f"11kV (Extra) ({e_idx + 1})"
            ws_extra = wb.create_sheet(title=sheet_title)
            _populate_switchgear_sheet(
                ws_extra,
                voltage_label="11kV",
                panels_input=extra_panels,
                swg_details=swg_11kv_details,
                v2_val=None,
                overview_rhs=(),
                overview_lhs=(),
            )

    # 3. Visual Inspection sheet
    ws_vi = wb.create_sheet(title=vi_sheet_name)
    ws_vi["D3"] = gps_coordinate

    # Default checklist items if none provided
    if visual_checklist_items is None:
        items = [
            {"category": "1. CIVIL", "item_no": "1.1", "description": "Fence & gate condition", "status": "YES", "remarks": ""},
            {"category": "1. CIVIL", "item_no": "1.2", "description": "Trench cover missing/broken", "status": "NO", "remarks": "Broken trench slab"},
            {"category": "2. SWITCHGEAR", "item_no": "2.1", "description": "Earthing connection intact", "status": "YES", "remarks": "Re-tightened earthing bar"},
            {"category": "2. SWITCHGEAR", "item_no": "2.2", "description": "Gas pressure gauge normal", "status": "YES", "remarks": ""},
        ]
    else:
        items = list(visual_checklist_items)

    curr_row = 8
    last_cat = ""
    for item in items:
        cat = item.get("category", "")
        if cat and cat != last_cat:
            ws_vi[f"B{curr_row}"] = cat
            curr_row += 1
            last_cat = cat

        ws_vi[f"B{curr_row}"] = item.get("item_no", "")
        ws_vi[f"C{curr_row}"] = item.get("description", "")
        status = item.get("status", "YES")
        if status == "NO":
            ws_vi[f"D{curr_row}"] = ""
            ws_vi[f"E{curr_row}"] = "X"
        else:
            ws_vi[f"D{curr_row}"] = "X"
            ws_vi[f"E{curr_row}"] = ""
        ws_vi[f"F{curr_row}"] = item.get("remarks", "")
        curr_row += 1

    # Category 8 "Other Findings" (Rows 78-80)
    for o_idx, remark in enumerate(other_findings):
        r_num = 78 + o_idx
        if r_num <= 80:
            ws_vi[f"B{r_num}"] = f"8.{o_idx + 1}"
            ws_vi[f"C{r_num}"] = remark
            ws_vi[f"F{r_num}"] = remark

    # 4. RAW DATA sheet
    bounds = raw_photo_bounds if raw_photo_bounds is not None else {"ir_start": 1, "ir_end": 50, "dg_start": 51, "dg_end": 90}
    ws_raw = wb.create_sheet(title="RAW DATA")
    ws_raw.append(["", "START", "END"])
    ws_raw.append(["IR", bounds.get("ir_start", 1), bounds.get("ir_end", 50)])
    ws_raw.append(["DG", bounds.get("dg_start", 51), bounds.get("dg_end", 90)])

    # 5. TX sheet
    if include_tx_sheet:
        ws_tx = wb.create_sheet(title=tx_sheet_name)
        tx_cols = ["G", "K", "N", "Q"]
        for t_idx, rating in enumerate(transformer_ratings):
            col = tx_cols[t_idx % len(tx_cols)]
            ws_tx[f"{col}8"] = rating
            ws_tx[f"F{14 + t_idx * 3}"] = "100A"

    # Remove the initial blank sheet
    if default_sheet in wb.worksheets:
        wb.remove(default_sheet)

    if path is not None:
        save_path = Path(path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(save_path)

    return wb
