"""Tests for combine_pdfs_with_separator workflow."""

from __future__ import annotations

from pathlib import Path

import pytest
from PyPDF2 import PdfReader, PdfWriter

from src.workflows.combine_pdfs_with_separator import combine_pdfs_with_separator


def create_dummy_pdf(path: Path, page_count: int = 1) -> Path:
    """Create a dummy PDF file with specified page count."""
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    with open(path, "wb") as f:
        writer.write(f)
    return path


def test_combine_pdfs_with_separator_success(tmp_path: Path):
    """Test combining 3 numbered PDFs with a separator sheet between them."""
    target_dir = tmp_path / "testsheets"
    target_dir.mkdir()

    # Create dummy separator (1 page)
    separator_pdf = tmp_path / "separator.pdf"
    create_dummy_pdf(separator_pdf, page_count=1)

    # Create 3 numbered PDFs (1 page each)
    create_dummy_pdf(target_dir / "001_alpha.pdf", page_count=1)
    create_dummy_pdf(target_dir / "02_beta.pdf", page_count=1)
    create_dummy_pdf(target_dir / "003_gamma.pdf", page_count=1)

    summary = combine_pdfs_with_separator(
        target_folder=target_dir,
        separator_path=separator_pdf,
        progress_sink=None,
    )

    assert summary.merged_count == 3
    assert summary.output_pdf_path.exists()
    assert summary.output_pdf_path.parent == target_dir / "combined_pdf"
    assert summary.output_pdf_path.name == "combined.pdf"

    # Verify total page count: 3 input pages + 2 separator pages = 5 pages
    reader = PdfReader(summary.output_pdf_path)
    assert len(reader.pages) == 5


def test_combine_pdfs_with_separator_hard_stop_on_unnumbered_file(tmp_path: Path):
    """Test that a HARD STOP error is raised if a PDF lacks a numerical prefix."""
    target_dir = tmp_path / "testsheets"
    target_dir.mkdir()

    separator_pdf = tmp_path / "separator.pdf"
    create_dummy_pdf(separator_pdf, page_count=1)

    create_dummy_pdf(target_dir / "001_valid.pdf", page_count=1)
    create_dummy_pdf(target_dir / "invalid_no_num.pdf", page_count=1)

    with pytest.raises(ValueError, match="HARD STOP.*invalid_no_num.pdf"):
        combine_pdfs_with_separator(
            target_folder=target_dir,
            separator_path=separator_pdf,
            progress_sink=None,
        )


def test_combine_pdfs_with_separator_empty_folder(tmp_path: Path):
    """Test that a HARD STOP error is raised if no PDF files exist in target directory."""
    target_dir = tmp_path / "empty_dir"
    target_dir.mkdir()

    separator_pdf = tmp_path / "separator.pdf"
    create_dummy_pdf(separator_pdf, page_count=1)

    with pytest.raises(ValueError, match="HARD STOP.*No PDF files found"):
        combine_pdfs_with_separator(
            target_folder=target_dir,
            separator_path=separator_pdf,
            progress_sink=None,
        )


def test_combine_pdfs_with_separator_ten_files_order(tmp_path: Path):
    """Test combining 10+ distinct PDFs with separator sheet ensuring no page replacement occurs."""
    target_dir = tmp_path / "testsheets"
    target_dir.mkdir()

    separator_pdf = tmp_path / "separator.pdf"
    create_dummy_pdf(separator_pdf, page_count=1)

    for i in range(1, 11):
        filename = f"{i:03d}_substation_{i}.pdf"
        create_dummy_pdf(target_dir / filename, page_count=2)

    summary = combine_pdfs_with_separator(
        target_folder=target_dir,
        separator_path=separator_pdf,
        progress_sink=None,
    )

    assert summary.merged_count == 10
    assert summary.output_pdf_path.exists()
    reader = PdfReader(summary.output_pdf_path)
    # 10 PDFs * 2 pages + 9 separators * 1 page = 29 pages
    assert len(reader.pages) == 29

