"""Tests for remove_desktop_ini_workflow."""

import tempfile
import unittest
from pathlib import Path

from src.remove_desktop_ini_workflow import remove_desktop_ini_files


class TestRemoveDesktopIniWorkflow(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_remove_desktop_ini_recursively(self) -> None:
        sub_dir1 = self.base_path / "folder1"
        sub_dir2 = self.base_path / "folder2" / "nested"
        sub_dir1.mkdir(parents=True, exist_ok=True)
        sub_dir2.mkdir(parents=True, exist_ok=True)

        file1 = sub_dir1 / "desktop.ini"
        file2 = sub_dir2 / "desktop.ini"
        other_file = sub_dir1 / "normal.txt"

        file1.write_text("[ShellClassInfo]", encoding="utf-8")
        file2.write_text("[ShellClassInfo]", encoding="utf-8")
        other_file.write_text("keep me", encoding="utf-8")

        self.assertTrue(file1.exists())
        self.assertTrue(file2.exists())
        self.assertTrue(other_file.exists())

        remove_desktop_ini_files(self.base_path)

        self.assertFalse(file1.exists())
        self.assertFalse(file2.exists())
        self.assertTrue(other_file.exists())


if __name__ == "__main__":
    unittest.main()
