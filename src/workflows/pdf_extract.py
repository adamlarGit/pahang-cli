"""Workflow for extracting PE pages from PDF using black-page detection."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from pdf2image import convert_from_path
from PyPDF2 import PdfReader, PdfWriter


@dataclass(frozen=True)
class PdfExtractSummary:
    pdf_path: Path
    total_pages: int
    extracted_sections: int
    cleaned_pdf_path: Path


def is_black_page(image: object, brightness_threshold: float = 100.0) -> bool:
    """Check if a page is a black/empty page based on brightness and variance."""
    gray_image = np.array(image.convert("L"))
    brightness = float(np.mean(gray_image))
    empty_check = bool(np.std(gray_image) < 10.0)
    return brightness < brightness_threshold or empty_check


def extract_pdf_sections_and_clean(pdf_path: str | Path) -> PdfExtractSummary:
    """Extract PDF sections based on black page triggers and clean black pages."""
    path = Path(pdf_path).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"PDF file not found: {path}")

    output_dir = path.parent
    pdf = PdfReader(str(path))
    total_pages = len(pdf.pages)
    print(f"Total pages in PDF: {total_pages}")

    images = convert_from_path(str(path))
    writer = PdfWriter()

    extracted_count = 1
    for i, image in enumerate(images):
        if is_black_page(image):
            print(f"Trigger detected on page {i + 1}")
            if writer.pages:
                output_pdf = output_dir / f"{extracted_count}_Extracted.pdf"
                with open(output_pdf, "wb") as f:
                    writer.write(f)
                print(f"Saved: {output_pdf}")
                writer = PdfWriter()
                extracted_count += 1
        else:
            writer.add_page(pdf.pages[i])

    if writer.pages:
        output_pdf = output_dir / f"{extracted_count}_Extracted.pdf"
        with open(output_pdf, "wb") as f:
            writer.write(f)
        print(f"Saved: {output_pdf}")

    # Remove black pages from original PDF
    cleaned_pdf_path = output_dir / f"Cleaned_{path.name}"
    clean_writer = PdfWriter()

    for i, image in enumerate(images):
        if not is_black_page(image):
            clean_writer.add_page(pdf.pages[i])
        else:
            print(f"Removing black page: {i + 1}")

    with open(cleaned_pdf_path, "wb") as f:
        clean_writer.write(f)

    if cleaned_pdf_path.exists():
        os.remove(path)
        os.rename(cleaned_pdf_path, path)

    print(f"Processed file saved as: {path}")
    return PdfExtractSummary(
        pdf_path=path,
        total_pages=total_pages,
        extracted_sections=extracted_count,
        cleaned_pdf_path=path,
    )


def run_pdf_extract() -> PdfExtractSummary:
    """Interactive entrypoint for PDF section extraction by black pages."""
    pdf_path = input("Enter the full path to the PDF file: ").strip().strip('"')
    if not os.path.exists(pdf_path):
        raise FileNotFoundError("Error: File not found. Please check the path and try again.")

    return extract_pdf_sections_and_clean(pdf_path)


run_extract_pe_pages = run_pdf_extract
