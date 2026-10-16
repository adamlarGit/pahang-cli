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

