"""Smoke test for the filename->year heuristic (the one branchy bit that isn't
just a passthrough to Docling/Chroma)."""
from mocolens.processing.chunker import guess_year


def test_guess_year_fy_prefix():
    assert guess_year("FY25_Vision_Zero_Annual_Report.pdf") == 2025
    assert guess_year("vz-progress-fy26.pdf") == 2026


def test_guess_year_plain_year():
    assert guess_year("2024_Automated_Enforcement_Action_Plan.pdf") == 2024


def test_guess_year_none_found():
    assert guess_year("blue_ribbon_panel_final_report.pdf") is None
