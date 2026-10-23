import zipfile
import openpyxl
from openpyxl.worksheet.table import Table
from pathlib import Path

from src.workflows.diagonal_borders import process_workbook

def test_diagonal_borders_applies_borders_and_clears_tables(tmp_path: Path):
    # Create a test Excel workbook with a table and blank cells
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "PCE Testsheet"
    ws["A1"] = "Header1"
    ws["B1"] = "Header2"
    ws["A2"] = "Val1"
    ws["B2"] = "Val2"
    ws["A3"] = "" # blank cell in A3:Y55 range
    
    tab = Table(displayName="Table1", ref="A1:B2")
    ws.add_table(tab)
    
    input_file = tmp_path / "001.xlsx"
    wb.save(input_file)
    
    # Process workbook
    out_file = Path(process_workbook(input_file))
    assert out_file.exists()
    
    # Verify openpyxl loaded output has diagonal border on A3
    wb_out = openpyxl.load_workbook(out_file)
    ws_out = wb_out["PCE Testsheet"]
    assert ws_out["A3"].border.diagonalUp is True
    
    # Check that zip relationships do not contain absolute Target="/xl/tables/"
    with zipfile.ZipFile(out_file, 'r') as z:
        for name in z.namelist():
            if name.startswith("xl/worksheets/_rels/"):
                rel_xml = z.read(name).decode("utf-8")
                assert 'Target="/xl/tables/' not in rel_xml, f"Found invalid absolute target path in {name}: {rel_xml}"
                assert 'Target="/xl/drawings/' not in rel_xml, f"Found invalid absolute target path in {name}: {rel_xml}"


def test_diagonal_borders_dispatch_pce_vi_and_33kv(tmp_path: Path):
    """Verify process_workbook correctly dispatches based on layout classification."""
    wb = openpyxl.Workbook()
    # Default sheet as PCE VI
    ws_vi = wb.active
    ws_vi.title = "PCE VI"
    ws_vi["C6"] = None  # in VI_SHEET_RANGES_TO_PROCESS

    # Switchgear sheet
    ws_swg = wb.create_sheet("33kV (Main)")
    ws_swg["C15"] = None  # in SWITCHGEAR_33KV_RANGES ("C15:U62")

    # Switchgear sheet with space in voltage token
    ws_swg_sp = wb.create_sheet("33 kV (Main)")
    ws_swg_sp["C15"] = None

    # Transformer sheet
    ws_tx = wb.create_sheet("TX")
    ws_tx["F14"] = None  # in TX_33KV_RANGES ("F14:AD28")

    # Visual Inspection sheet (strictly unslashed)
    ws_vis = wb.create_sheet("Visual Inspection")
    ws_vis["C15"] = None

    # 33 kV VI sheet (strictly unslashed)
    ws_vis_33 = wb.create_sheet("33 kV VI")
    ws_vis_33["C15"] = None

    input_file = tmp_path / "002.xlsx"
    wb.save(input_file)
    wb.close()

    out_file = Path(process_workbook(input_file))
    wb_out = openpyxl.load_workbook(out_file)

    assert wb_out["PCE VI"]["C6"].border.diagonalUp is True
    assert wb_out["33kV (Main)"]["C15"].border.diagonalUp is True
    assert wb_out["33 kV (Main)"]["C15"].border.diagonalUp is True
    assert wb_out["TX"]["F14"].border.diagonalUp is True
    # Visual Inspection must not have diagonal borders applied
    assert wb_out["Visual Inspection"]["C15"].border.diagonalUp in (None, False)
    assert wb_out["33 kV VI"]["C15"].border.diagonalUp in (None, False)
    wb_out.close()


def test_diagonal_borders_main_switchgear_l63_p74_and_extra_exclusion(tmp_path: Path):
    """Verify L63:P74 is applied strictly to 33kV (Main) and 11kV (Main), excluding Extra sheets and outer columns."""
    wb = openpyxl.Workbook()
    ws_33_main = wb.active
    ws_33_main.title = "33kV (Main)"
    ws_33_main["C15"] = ""  # Feeder grid blank
    ws_33_main["L63"] = ""  # Overview grid blank
    ws_33_main["M63"] = ""
    ws_33_main["O63"] = '=IF(M63="","",((L63+M63)/2))'  # Formula evaluating to blank
    ws_33_main["P63"] = ""
    ws_33_main["L64"] = 28.5  # Populated
    ws_33_main["M64"] = 30.5  # Populated
    ws_33_main["O64"] = '=IF(M64="","",((L64+M64)/2))'  # Formula with populated inputs
    ws_33_main["P64"] = "IMG01"
    # Labels in columns B, C, K
    ws_33_main["B63"] = "A"
    ws_33_main["C63"] = "RHS PANEL (OVERVIEW)"
    ws_33_main["K63"] = "FRONT"
    # Outer columns Q-U
    ws_33_main["Q63"] = ""
    ws_33_main["R63"] = ""

    # 11kV Main sheet (variant casing with internal/external spaces)
    ws_11_main = wb.create_sheet("11 kV ( MAIN )")
    ws_11_main["C15"] = ""
    ws_11_main["L70"] = ""
    ws_11_main["P74"] = ""
    ws_11_main["Q70"] = ""

    # 33kV Main sheet with no space before paren
    ws_33_no_space = wb.create_sheet("33kV(Main)")
    ws_33_no_space["C15"] = ""
    ws_33_no_space["L63"] = ""

    # Sheet with prefix but extra suffix should NOT match main sheet
    ws_backup = wb.create_sheet("33kV (Main) Backup")
    ws_backup["C15"] = ""
    ws_backup["L63"] = ""

    # 33kV Extra sheet
    ws_33_extra = wb.create_sheet("33kV (Extra)")
    ws_33_extra["C15"] = ""
    ws_33_extra["L63"] = ""
    ws_33_extra["P74"] = ""

    # 11kV Extra sheet
    ws_11_extra = wb.create_sheet("11kV (Extra) (2)")
    ws_11_extra["C15"] = ""
    ws_11_extra["L63"] = ""

    input_file = tmp_path / "003_main_extra.xlsx"
    wb.save(input_file)
    wb.close()

    out_file = Path(process_workbook(input_file))
    wb_out = openpyxl.load_workbook(out_file)

    # 1. Check 33kV (Main)
    ws_res_33m = wb_out["33kV (Main)"]
    assert ws_res_33m["C15"].border.diagonalUp is True
    assert ws_res_33m["L63"].border.diagonalUp is True
    assert ws_res_33m["M63"].border.diagonalUp is True
    assert ws_res_33m["O63"].border.diagonalUp is True
    assert ws_res_33m["P63"].border.diagonalUp is True
    # Populated cells must NOT be slashed
    assert ws_res_33m["L64"].border.diagonalUp is not True
    assert ws_res_33m["M64"].border.diagonalUp is not True
    assert ws_res_33m["O64"].border.diagonalUp is not True
    assert ws_res_33m["P64"].border.diagonalUp is not True
    # Labels and outer columns must NOT be slashed
    assert ws_res_33m["B63"].border.diagonalUp is not True
    assert ws_res_33m["C63"].border.diagonalUp is not True
    assert ws_res_33m["K63"].border.diagonalUp is not True
    assert ws_res_33m["Q63"].border.diagonalUp is not True
    assert ws_res_33m["R63"].border.diagonalUp is not True

    # 2. Check 11 kV ( MAIN )
    ws_res_11m = wb_out["11 kV ( MAIN )"]
    assert ws_res_11m["C15"].border.diagonalUp is True
    assert ws_res_11m["L70"].border.diagonalUp is True
    assert ws_res_11m["P74"].border.diagonalUp is True
    assert ws_res_11m["Q70"].border.diagonalUp is not True

    # Check 33kV(Main) (no space before paren)
    ws_res_33_ns = wb_out["33kV(Main)"]
    assert ws_res_33_ns["C15"].border.diagonalUp is True
    assert ws_res_33_ns["L63"].border.diagonalUp is True

    # Check 33kV (Main) Backup - falls back to extra ranges (C15 slashed, L63 unslashed)
    ws_res_bak = wb_out["33kV (Main) Backup"]
    assert ws_res_bak["C15"].border.diagonalUp is True
    assert ws_res_bak["L63"].border.diagonalUp is not True

    # 3. Check 33kV (Extra) - C15 slashed, but L63 and P74 strictly unslashed
    ws_res_33e = wb_out["33kV (Extra)"]
    assert ws_res_33e["C15"].border.diagonalUp is True
    assert ws_res_33e["L63"].border.diagonalUp is not True
    assert ws_res_33e["P74"].border.diagonalUp is not True

    # 4. Check 11kV (Extra) (2) - C15 slashed, L63 strictly unslashed
    ws_res_11e = wb_out["11kV (Extra) (2)"]
    assert ws_res_11e["C15"].border.diagonalUp is True
    assert ws_res_11e["L63"].border.diagonalUp is not True

    wb_out.close()


