from zipfile import ZipFile
from pathlib import Path
from lxml import etree

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
files = [
    r"C:\Users\ADAM\AppData\Local\Temp\r232\project\FULL REPORT\GEBENG\01. OCTOBER\07-10-2026\01. PPU APMM 3311kV - Part 03 - Panel 1 (33kV - SPARE).docx",
    r"C:\Users\ADAM\AppData\Local\Temp\r232\project\FULL REPORT\GEBENG\01. OCTOBER\07-10-2026\01. PPU APMM 3311kV - Part 32 - TX and Condition.docx"
]
for f in files:
    with ZipFile(f) as z:
        tree = etree.fromstring(z.read("word/document.xml"))
        brs = tree.xpath("//w:br[@w:type='page']", namespaces=NS)
        sects = tree.xpath("//w:sectPr", namespaces=NS)
        print(f"{Path(f).name}: br={len(brs)}, sectPr={len(sects)}")
