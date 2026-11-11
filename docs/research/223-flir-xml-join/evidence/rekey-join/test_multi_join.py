import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from xml_join_flir_engine import join_documents_in_xml

# Test joining 3 panels sequentially
template_bytes = Path("templates/FULL REPORT/NORMAL IR US TEV/swg-panel.docx").read_bytes()

print("Joining Panel 1 + Panel 2...")
joined_2 = join_documents_in_xml(template_bytes, template_bytes)

print("Joining (Panel 1 + Panel 2) + Panel 3...")
joined_3 = join_documents_in_xml(joined_2, template_bytes)

out_file = Path(".scratch/joined_3_panels_proof.docx")
out_file.write_bytes(joined_3)
print(f"Successfully joined 3 panels! Output: {out_file} ({len(joined_3)} bytes)")
