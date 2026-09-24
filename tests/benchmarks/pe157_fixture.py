"""Synthetic benchmark fixture for PE 157 PERPUSTAKAAN AWAM (Ticket #58).

Provides a self-contained, lightweight synthetic fixture matching canonical
PE 157 VCB topology:
- 5-panel TAMCO VCB 11kV lineup:
  - Panel 1: SSU IBU PEJABAT MPK CB5 (Breaker, Cable, Busbar, Secondary)
  - Panel 2: SSU IBU PEJABAT MPK CB8 (Breaker, Cable, Busbar, Secondary + Inline CBM Defect)
  - Panel 3: TRANSITION PANEL (Transition bay: Front, Rear, Busbar, Secondary)
  - Panel 4: MSB (PT chamber on panel 4 with pt_photo and has_pt_measurement=True)
  - Panel 5: TX 300KVA (Breaker, Cable, Busbar, Secondary)
- Switchgear overviews: Front (485), Rear (488), Top (491)
- 1 Transformer: Tx 1 (1000kVA, EWT)
- 1 Feeder Pillar: FP 1 (800A, TAMCO)
- 1 Inline CBM defect page: swg1_p02_CKN03901_CABLE_COMPARTMENT_01.docx
- Minimal testsheet Excel workbook
- Stub thermal/visual photos
- Pre-sliced Quick Report sections
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import zipfile
import docx
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls
import openpyxl

from src.full_report.slicer import SlicedSections
from src.project.environment import ProjectEnvironment
from src.project.models import ProjectMetadata
from src.project.storage import LocalWorkspaceStorage
from src.testsheet.models import (
    BatteryBankSpec,
    FireExtinguisherSpec,
    LVDBSpec,
    SubstationEquipmentPackage,
    SwitchgearPanelSpec,
    SwitchgearSpec,
    TransformerSpec,
)

MINIMAL_JPEG_BYTES = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00"
    b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
    b"\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a"
    b"\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342"
    b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00"
    b"\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00"
    b"\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b"
    b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9"
)

MINIMAL_PDF_BYTES = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
    b"3 0 obj<</Type/Page/MediaBox[0 0 595 842]/Parent 2 0 R/Resources<<>>>>endobj\n"
    b"xref\n0 4\n0000000000 65535 f \n0000000010 00000 n \n0000000053 00000 n \n0000000102 00000 n \n"
    b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n178\n%%EOF\n"
    + (b"% PADDING " + b"X" * 1000 + b"\n")
)


def get_pe157_equipment_package() -> SubstationEquipmentPackage:
    """Return strongly typed SubstationEquipmentPackage for PE 157 PERPUSTAKAAN AWAM."""
    swg = SwitchgearSpec(
        switchgear_type="VCB 11kV",
        manufacturer="TAMCO",
        model="GV3",
        rating="11kV 630A",
        photo_numbers=(485, 488, 491),
        panels=(
            SwitchgearPanelSpec(
                panel_no=1,
                panel_feeder_no="CKN03900",
                name="SSU IBU PEJABAT MPK CB5",
                cable_photo=498,
                breaker_photo=493,
                secondary_photo=520,
                busbar_photo=503,
            ),
            SwitchgearPanelSpec(
                panel_no=2,
                panel_feeder_no="CKN03901",
                name="SSU IBU PEJABAT MPK CB8",
                cable_photo=499,
                breaker_photo=494,
                secondary_photo=521,
                busbar_photo=504,
            ),
            SwitchgearPanelSpec(
                panel_no=3,
                panel_feeder_no="CKN03902",
                name="TRANSITION PANEL",
                cable_photo=500,
                breaker_photo=495,
                secondary_photo=522,
                busbar_photo=505,
            ),
            SwitchgearPanelSpec(
                panel_no=4,
                panel_feeder_no="CKN03903",
                name="MSB",
                cable_photo=501,
                breaker_photo=496,
                secondary_photo=523,
                busbar_photo=506,
                pt_photo=526,
                has_pt_measurement=True,
            ),
            SwitchgearPanelSpec(
                panel_no=5,
                panel_feeder_no="CKN03904",
                name="TX 300KVA",
                cable_photo=502,
                breaker_photo=497,
                secondary_photo=524,
                busbar_photo=507,
            ),
        ),
    )
    tx = TransformerSpec(tx_id="Tx 1", rating_kva="1000", manufacturer="EWT")
    fp = LVDBSpec(name="FP 1", label="FP", source="TX1", rating="800A", manufacturer="TAMCO")
    bb1 = BatteryBankSpec(name="BATTERY 1")
    bb2 = BatteryBankSpec(name="BATTERY 2")

    return SubstationEquipmentPackage(
        switchgears=(swg,),
        transformers=(tx,),
        lvdb_specs=(fp,),
        battery_banks=(bb1, bb2),
        fire_extinguisher=FireExtinguisherSpec(is_valid=True, expiry_date="31/12/2026"),
    )


def create_pe157_testsheet_workbook(target_path: Path) -> Path:
    """Create minimal openpyxl testsheet workbook for PE 157 PERPUSTAKAAN AWAM."""
    target_path = Path(target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    wb = openpyxl.Workbook()

    # Sheet 1: PCE Testsheet (Panels 1-4)
    ws_pce1 = wb.active
    ws_pce1.title = "PCE Testsheet"
    ws_pce1["C5"] = "PERPUSTAKAAN AWAM"
    ws_pce1["P4"] = "2026-08-25"
    ws_pce1["W5"] = "CKTN039"

    # Overviews
    ws_pce1["O27"] = 485  # Front
    ws_pce1["O26"] = 488  # Rear
    ws_pce1["O28"] = 491  # Top

    # Panel 1 (row 10)
    ws_pce1["B10"] = "CKN03900"
    ws_pce1["C10"] = "SSU IBU PEJABAT MPK CB5"
    ws_pce1["D10"] = "CLOSE"
    ws_pce1["F10"] = "17A"
    ws_pce1["G10"] = "XLPE 3C 240mm2"
    ws_pce1["H10"] = "0.5A"
    ws_pce1["I10"] = "SN-P01"
    ws_pce1["J10"] = "VCB"
    ws_pce1["O10"] = 498
    ws_pce1["O11"] = 493
    ws_pce1["P11"] = "S.PANEL IR 520"
    ws_pce1["O12"] = 503

    # Panel 2 (row 14)
    ws_pce1["B14"] = "CKN03901"
    ws_pce1["C14"] = "SSU IBU PEJABAT MPK CB8"
    ws_pce1["D14"] = "CLOSE"
    ws_pce1["F14"] = "17A"
    ws_pce1["G14"] = "XLPE 3C 240mm2"
    ws_pce1["H14"] = "0.5A"
    ws_pce1["I14"] = "SN-P02"
    ws_pce1["J14"] = "VCB"
    ws_pce1["O14"] = 499
    ws_pce1["O15"] = 494
    ws_pce1["P15"] = "S.PANEL IR 521"
    ws_pce1["O16"] = 504

    # Panel 3 (row 18) - Transition panel
    ws_pce1["B18"] = "CKN03902"
    ws_pce1["C18"] = "TRANSITION PANEL"
    ws_pce1["D18"] = "CLOSE"
    ws_pce1["F18"] = "-"
    ws_pce1["G18"] = "-"
    ws_pce1["H18"] = "-"
    ws_pce1["I18"] = "SN-P03"
    ws_pce1["J18"] = "VCB"
    ws_pce1["O18"] = 500
    ws_pce1["O19"] = 495
    ws_pce1["P19"] = "S.PANEL IR 522"
    ws_pce1["O20"] = 505

    # Panel 4 (row 22) - PT
    ws_pce1["B22"] = "CKN03903"
    ws_pce1["C22"] = "MSB"
    ws_pce1["D22"] = "CLOSE"
    ws_pce1["F22"] = "50A"
    ws_pce1["G22"] = "XLPE 3C 240mm2"
    ws_pce1["H22"] = "0.5A"
    ws_pce1["I22"] = "SN-P04"
    ws_pce1["J22"] = "VCB"
    ws_pce1["O22"] = 501
    ws_pce1["O23"] = 496
    ws_pce1["P23"] = "S.PANEL IR 523"
    ws_pce1["O24"] = 506
    ws_pce1["O25"] = 526
    ws_pce1["K25"] = "10"

    # Transformer cable thermals (Rows 33-35)
    ws_pce1["C33"] = "XLPE 3C 240mm2"
    ws_pce1["C35"] = "XLPE 4C 300mm2"
    ws_pce1["F33"] = 40.0
    ws_pce1["G33"] = 41.0
    ws_pce1["H33"] = 39.0
    ws_pce1["I33"] = 38.0

    # LVDB / Feeder Pillar (rows 44-51)
    ws_pce1["R48"] = "FP"
    ws_pce1["T48"] = "TX1"
    ws_pce1["S49"] = 510
    ws_pce1["U49"] = "TAMCO"
    ws_pce1["U51"] = "800A"
    ws_pce1["C44"] = "IN1"
    ws_pce1["C45"] = "XLPE 4C 300mm2"
    ws_pce1["D44"] = "OT1"
    ws_pce1["D45"] = "XLPE 4C 185mm2"

    # Battery
    ws_pce1["B59"] = "BATTERY 1"
    ws_pce1["H59"] = 530
    ws_pce1["J59"] = "CHLORIDE"

    # Sheet 2: PCE Testsheet (2) (Panel 5)
    ws_pce2 = wb.create_sheet(title="PCE Testsheet (2)")
    ws_pce2["B10"] = "CKN03904"
    ws_pce2["C10"] = "TX 300KVA"
    ws_pce2["D10"] = "CLOSE"
    ws_pce2["F10"] = "20A"
    ws_pce2["G10"] = "XLPE 3C 240mm2"
    ws_pce2["H10"] = "0.5A"
    ws_pce2["I10"] = "SN-P05"
    ws_pce2["J10"] = "VCB"
    ws_pce2["O10"] = 502
    ws_pce2["O11"] = 497
    ws_pce2["P11"] = "S.PANEL IR 524"
    ws_pce2["O12"] = 507

    # Sheet 3: PCE VI
    ws_vi = wb.create_sheet(title="PCE VI")
    ws_vi["C7"] = "PE 157 PERPUSTAKAAN AWAM"
    ws_vi["N1"] = "PE"
    ws_vi["C9"] = "INDOOR"
    ws_vi["D9"] = "/"

    # Switchgear 1
    ws_vi["J11"] = "/"  # VCB
    ws_vi["C12"] = "TAMCO"
    ws_vi["G12"] = "GV3"
    ws_vi["C13"] = "2015"
    ws_vi["J13"] = "11kV 630A"
    ws_vi["O13"] = "SG-2015-0157"

    # Transformer
    ws_vi["C17"] = 1
    ws_vi["D18"] = "HERMETICALLY SEALED"
    ws_vi["F18"] = "1000kVA"
    ws_vi["L18"] = "EWT"
    ws_vi["O18"] = "TX-157-01"

    # Auxiliaries & Fire Extinguisher
    ws_vi["E25"] = "/"
    ws_vi["E29"] = "/"
    ws_vi["D42"] = "/"
    ws_vi["J42"] = "31/12/2026"

    # Sheet 4: RAW DATA
    ws_raw = wb.create_sheet(title="RAW DATA")
    all_photos = [
        485, 488, 491,
        493, 494, 495, 496, 497,
        498, 499, 500, 501, 502,
        503, 504, 505, 506, 507,
        510, 520, 521, 522, 523, 524, 526, 530,
    ]
    for row_idx, photo in enumerate(all_photos, start=2):
        ws_raw.cell(row_idx, 1, "IR")
        ws_raw.cell(row_idx, 2, photo)
        ws_raw.cell(row_idx, 3, photo)

    wb.save(target_path)
    wb.close()
    return target_path


def create_pe157_stub_photos(photo_dir: Path) -> list[Path]:
    """Create stub JPEG photos for all PE 157 inspection images in IR and DG subdirectories."""
    photo_dir = Path(photo_dir)
    ir_dir = photo_dir / "IR"
    dg_dir = photo_dir / "DG"
    ir_dir.mkdir(parents=True, exist_ok=True)
    dg_dir.mkdir(parents=True, exist_ok=True)

    photo_nums = [
        485, 488, 491,
        493, 494, 495, 496, 497,
        498, 499, 500, 501, 502,
        503, 504, 505, 506, 507,
        510, 520, 521, 522, 523, 524, 526, 530,
    ]

    created: list[Path] = []
    for num in photo_nums:
        for prefix, directory in (("IR", ir_dir), ("DG", dg_dir)):
            p = directory / f"{prefix}_{num:04d}.jpg"
            p.write_bytes(MINIMAL_JPEG_BYTES)
            created.append(p)
    return created


def create_pe157_sliced_sections(slice_dir: Path, station: str = "PERPUSTAKAAN AWAM") -> SlicedSections:
    """Create valid pre-sliced docx sections for PE 157 in slice_dir."""
    slice_dir = Path(slice_dir)
    slice_dir.mkdir(parents=True, exist_ok=True)

    # 1. Front page
    front_path = slice_dir / "front_page.docx"
    doc_front = docx.Document()
    doc_front.add_table(rows=1, cols=3)
    t_front = doc_front.add_table(rows=4, cols=3)
    t_front.rows[2].cells[0].text = "SUBSTATION NAME (ERMS)"
    t_front.rows[2].cells[2].text = station
    t_front.rows[3].cells[0].text = "SUBSTATION NAME (SITE)"
    t_front.rows[3].cells[2].text = station
    doc_front.save(front_path)

    # 2. Condition pages
    cond_path = slice_dir / "condition_pages.docx"
    doc_cond = docx.Document()
    t_cond = doc_cond.add_table(rows=1, cols=1)
    p_cond = doc_cond.add_paragraph()
    r_cond = p_cond.add_run()
    r_cond._r.append(
        parse_xml(
            r'<w:drawing %s><w:inline><a:graphic %s><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic %s><pic:blipFill><a:blip r:embed="rId1"/></pic:blipFill></pic:pic></a:graphicData></a:graphic></w:inline></w:drawing>'
            % (nsdecls("w"), nsdecls("a"), nsdecls("pic", "r"))
        )
    )
    doc_cond.save(cond_path)

    # 3. Sticker page
    sticker_path = slice_dir / "sticker_page.docx"
    doc_stk = docx.Document()
    doc_stk.add_paragraph("NORMAL STICKER")
    doc_stk.save(sticker_path)

    # 4. VI summary
    vi_sum_path = slice_dir / "vi_summary.docx"
    doc_vi = docx.Document()
    t_vi = doc_vi.add_table(rows=2, cols=4)
    t_vi.rows[0].cells[0].text = "NO"
    t_vi.rows[0].cells[1].text = "EQUIPMENT"
    t_vi.rows[0].cells[2].text = "DEFECT DESCRIPTION"
    t_vi.rows[0].cells[3].text = "REMARKS"
    t_vi.rows[1].cells[0].text = "1"
    t_vi.rows[1].cells[1].text = "SWITCHGEAR"
    t_vi.rows[1].cells[2].text = "EARTHING CONDUCTOR LOOSE"
    t_vi.rows[1].cells[3].text = "REPAIR NEEDED"
    doc_vi.save(vi_sum_path)

    # 5. VI defects
    vi_def_path = slice_dir / "vi_defect_pages.docx"
    doc_vd = docx.Document()
    doc_vd.add_paragraph("VI DEFECT DETAIL")
    doc_vd.save(vi_def_path)

    # 6. Inline CBM defect page for Panel 2
    cbm_dir = slice_dir / "cbm_defects"
    cbm_dir.mkdir(parents=True, exist_ok=True)
    cbm_defect_path = cbm_dir / "swg1_p02_CKN03901_CABLE_COMPARTMENT_01.docx"
    doc_cbm = docx.Document()
    t_cbm = doc_cbm.add_table(rows=3, cols=4)
    t_cbm.rows[0].cells[0].text = "Substation:"
    t_cbm.rows[0].cells[1].text = f"PE 157 {station}"
    t_cbm.rows[0].cells[2].text = "Date: 25/08/2026"
    t_cbm.rows[1].cells[0].text = "Equipment:"
    t_cbm.rows[1].cells[1].text = "VCB"
    t_cbm.rows[1].cells[2].text = "Panel No. 2"
    t_cbm.rows[2].cells[0].text = "Area:"
    t_cbm.rows[2].cells[1].text = "CABLE COMPARTMENT"
    t_cbm.rows[2].cells[2].text = "Feeder No. CKN03901"
    doc_cbm.save(cbm_defect_path)

    return SlicedSections(
        station=station,
        front_page=front_path,
        condition_pages=cond_path,
        sticker_page=sticker_path,
        vi_summary=vi_sum_path,
        vi_defect_pages=vi_def_path,
        cbm_defect_pages=(cbm_defect_path,),
    )


def create_pe157_quick_report_docx(target_path: Path) -> Path:
    """Create a mock finalized Quick Report docx meeting pre-flight validation standards."""
    target_path = Path(target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(target_path, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("[Content_Types].xml", b"<Types/>")
        zf.writestr("word/_rels/document.xml.rels", b"<Relationships/>")

        # Add >= 8 media files
        for i in range(10):
            zf.writestr(f"word/media/image{i + 1}.jpg", MINIMAL_JPEG_BYTES)

        # Pad word/document.xml so total file size >= 1.05 MB
        current_size = sum(info.file_size for info in zf.filelist)
        padding = max(0, 1_100_000 - current_size)
        zf.writestr("word/document.xml", b"<w:document>" + b"a" * padding + b"</w:document>")

    return target_path


def create_pe157_testsheet_pdf(target_path: Path) -> Path:
    """Create a signed testsheet PDF deliverable for post-processing merge."""
    target_path = Path(target_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(MINIMAL_PDF_BYTES)
    return target_path


def setup_pe157_benchmark_environment(root_dir: Path) -> tuple[ProjectEnvironment, dict[str, Path]]:
    """Assemble a complete ProjectEnvironment containing PE 157 PERPUSTAKAAN AWAM benchmark files."""
    root_dir = Path(root_dir)
    station = "KUANTAN"
    month = "01. AUGUST"
    date_str = "25-08-2026"
    sub_num = 157
    stem = "157. PERPUSTAKAAN AWAM (IR+VI)"

    # Paths
    ts_dir = root_dir / "TESTSHEET" / station / month / date_str
    raw_dir = root_dir / "RAW MATERIAL" / station / month / date_str / f"{sub_num:03d}" / "RAW DATA"
    qr_dir = root_dir / "QUICK REPORT" / station / month / date_str
    pdf_dir = ts_dir / "processed_testsheet" / "pdf"
    slices_dir = root_dir / ".temp" / "full_report" / "slices" / "PERPUSTAKAAN_AWAM"

    # Create files
    ts_path = create_pe157_testsheet_workbook(ts_dir / f"{sub_num:03d}. PERPUSTAKAAN AWAM(VCB).xlsx")
    create_pe157_stub_photos(raw_dir)
    qr_path = create_pe157_quick_report_docx(qr_dir / f"{stem}.docx")
    pdf_path = create_pe157_testsheet_pdf(pdf_dir / f"{stem}.pdf")
    slices = create_pe157_sliced_sections(slices_dir)

    # Project metadata & environment
    meta = ProjectMetadata(
        key="pahang_benchmark",
        name="Pahang Benchmark Test",
        po_number="42360565",
        state="PAHANG",
        voltage_type="11kV",
        year="2026",
        cycle="CYCLE3",
        technologies=("IR", "DG", "US", "TEV", "VI"),
        base_path=str(root_dir),
    )
    storage = LocalWorkspaceStorage(root_dir)
    env = ProjectEnvironment(metadata=meta, storage=storage)

    file_map = {
        "testsheet": ts_path,
        "quick_report": qr_path,
        "testsheet_pdf": pdf_path,
        "slices_dir": slices_dir,
    }
    return env, file_map


def materialize_pe157_benchmark_fixture(target_dir: Path | None = None) -> Path:
    """Materialize persistent benchmark fixture files for PE 157 on disk."""
    if target_dir is None:
        target_dir = Path(__file__).parent / "pe157_perpustakaan_awam"
    target_dir = Path(target_dir)

    ts_path = target_dir / "157. PERPUSTAKAAN AWAM(VCB).xlsx"
    create_pe157_testsheet_workbook(ts_path)

    photo_dir = target_dir / "photos"
    create_pe157_stub_photos(photo_dir)

    slices_dir = target_dir / "slices"
    create_pe157_sliced_sections(slices_dir)

    ts_pdf_path = target_dir / "processed_testsheet" / "pdf" / "157. PERPUSTAKAAN AWAM (IR+VI).pdf"
    create_pe157_testsheet_pdf(ts_pdf_path)

    return target_dir
