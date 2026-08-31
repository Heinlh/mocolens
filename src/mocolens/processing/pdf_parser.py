"""Parses PDFs into Docling's structured document representation.

Docling handles layout, headers/footers, and tables directly (§9's "Clean
headers/footers" requirement) instead of raw PyMuPDF text extraction.
"""
from pathlib import Path

from docling.document_converter import DocumentConverter

# Loads Docling's layout model once per process; expensive to construct per call.
_converter = DocumentConverter()


def parse(pdf_path: Path):
    """Convert a PDF into a Docling document (headings, tables, page provenance intact)."""
    return _converter.convert(str(pdf_path)).document
