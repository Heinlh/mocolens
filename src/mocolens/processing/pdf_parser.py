"""Parses PDFs into Docling's structured document representation.

Docling handles layout, headers/footers, and tables directly (§9's "Clean
headers/footers" requirement) instead of raw PyMuPDF text extraction.
"""
from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

# County reports are born-digital (real text layer), not scans - OCR finds
# nothing on them but still reloads RapidOCR's ONNX models and runs full-page
# detection on every single page. That's what was exhausting memory over a
# multi-document run. Table structure detection stays on; it's cheap and
# these reports have real tables worth preserving.
_PIPELINE_OPTIONS = PdfPipelineOptions(do_ocr=False, do_table_structure=True)

# Loads Docling's layout model once per process; expensive to construct per call.
_converter = DocumentConverter(
    format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=_PIPELINE_OPTIONS)}
)


def parse(pdf_path: Path):
    """Convert a PDF into a Docling document (headings, tables, page provenance intact)."""
    return _converter.convert(str(pdf_path)).document
