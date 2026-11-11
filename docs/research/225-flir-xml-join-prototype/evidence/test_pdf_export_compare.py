"""Export Part 03 COM-compiled vs XML-joined to PDF and compare page counts and embedded images."""

from pathlib import Path
import fitz  # PyMuPDF
import pythoncom
import win32com.client

def export_doc_to_pdf(docx_path: Path, pdf_path: Path):
    pythoncom.CoInitialize()
    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        doc = word.Documents.Open(str(docx_path), False, True)
        doc.ExportAsFixedFormat(
            OutputFileName=str(pdf_path),
            ExportFormat=17,  # wdExportFormatPDF
            OpenAfterExport=False,
            OptimizeFor=0,     # wdExportOptimizeForPrint
        )
        doc.Close(False)
    finally:
        word.Quit()
        pythoncom.CoUninitialize()

def analyze_pdf(pdf_path: Path):
    doc = fitz.open(str(pdf_path))
    num_pages = len(doc)
    images_count = sum(len(page.get_images()) for page in doc)
    doc.close()
    return num_pages, images_count

def main():
    p3_com = Path(r"C:\Users\ADAM\AppData\Local\Temp\r232\project\FULL REPORT\GEBENG\01. OCTOBER\07-10-2026\01. PPU APMM 3311kV - Part 03 - Panel 1 (33kV - SPARE).docx")
    p3_xml = Path(r"C:\Users\ADAM\Desktop\pahang-cli-33kv\scratch\prototype-flir-xml-join-225\worktree\scratch\output\01. PPU APMM 3311kV - Part 03 - Panel 1 (33kV - SPARE) [XML-JOINED].docx")

    out_dir = Path(r"C:\Users\ADAM\Desktop\pahang-cli-33kv\scratch\prototype-flir-xml-join-225\worktree\scratch\output")
    pdf_com = out_dir / "part03_com.pdf"
    pdf_xml = out_dir / "part03_xml.pdf"

    print("Exporting Part 03 COM to PDF...")
    export_doc_to_pdf(p3_com, pdf_com)

    print("Exporting Part 03 XML to PDF...")
    export_doc_to_pdf(p3_xml, pdf_xml)

    pg_com, img_com = analyze_pdf(pdf_com)
    pg_xml, img_xml = analyze_pdf(pdf_xml)

    print(f"\nPDF Comparison for Part 03:")
    print(f"  COM Export: {pg_com} pages, {img_com} embedded images, {pdf_com.stat().st_size:,} bytes")
    print(f"  XML Export: {pg_xml} pages, {img_xml} embedded images, {pdf_xml.stat().st_size:,} bytes")

    assert pg_com == pg_xml, f"Page count mismatch: {pg_com} != {pg_xml}"
    assert img_com == img_xml, f"Images count mismatch: {img_com} != {img_xml}"
    print("\n>>> PASS CONDITION 4 MET: Stage 2 PDF export matches COM-compiled file! <<<")

if __name__ == "__main__":
    main()
