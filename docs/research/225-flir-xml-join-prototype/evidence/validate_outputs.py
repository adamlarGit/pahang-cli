"""Read-only: run the #225 structural validator on joined outputs that already exist.

Added during the 2026-11-11 conversion to the Ticket Folder layout, so the
structural claims have a captured log without overwriting the joined files
the owner checked in Word.

Usage: python validate_outputs.py <part03 joined docx> <part32 joined docx>
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run_prototype_225 import validate_joined_document

validate_joined_document(Path(sys.argv[1]), expected_viewers=7)
validate_joined_document(Path(sys.argv[2]), expected_viewers=26)
