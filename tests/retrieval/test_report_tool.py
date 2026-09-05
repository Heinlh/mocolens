from unittest.mock import patch

import pytest

from mocolens.retrieval.report_tool import _format_page, search_reports


def test_format_page_single():
    assert _format_page(18, 18) == "18"


def test_format_page_none():
    assert _format_page(18, None) == "18"


def test_format_page_range():
    assert _format_page(14, 15) == "14-15"


def test_format_page_missing():
    assert _format_page(None, None) is None


@patch("mocolens.retrieval.report_tool.vector_store.search")
def test_search_reports_reshapes_vector_store_output(mock_search):
    mock_search.return_value = [
        {
            "chunk_id": "abc", "text": "Pedestrian safety improved.",
            "title": "FY25 Vision Zero Annual Report", "page_start": 18, "page_end": 19,
            "year": 2025, "domain": "vision_zero", "source_url": "https://example.gov/report.pdf",
            "section": "Pedestrian Safety", "similarity": 0.87234,
        }
    ]
    results = search_reports("pedestrian safety", top_k=1)
    assert results == [{
        "text": "Pedestrian safety improved.",
        "document_title": "FY25 Vision Zero Annual Report",
        "page": "18-19",
        "publication_year": 2025,
        "source_url": "https://example.gov/report.pdf",
        "similarity_score": 0.8723,
        "section": "Pedestrian Safety",
    }]
    mock_search.assert_called_once_with(
        "vision_zero", "pedestrian safety", top_k=1, year_at_least=None
    )


@patch("mocolens.retrieval.report_tool.vector_store.search")
def test_search_reports_passes_year_filter_and_domain_through(mock_search):
    mock_search.return_value = []
    search_reports("query", top_k=3, year_at_least=2023, domain="vision_zero")
    mock_search.assert_called_once_with("vision_zero", "query", top_k=3, year_at_least=2023)


@patch("mocolens.retrieval.report_tool.vector_store.search")
def test_search_reports_empty_results(mock_search):
    mock_search.return_value = []
    assert search_reports("nothing matches this") == []


def _index_built() -> bool:
    from mocolens.storage import vector_store
    return vector_store.index_path("vision_zero").exists()


@pytest.mark.skipif(
    not _index_built(), reason="run scripts/rebuild_vector_index.py --domain vision_zero first"
)
def test_search_reports_against_real_index():
    """Live check against the actual index, if it exists - skipped otherwise
    so this suite doesn't depend on pipeline state to pass in a fresh checkout.
    """
    results = search_reports("pedestrian safety improvements", top_k=3)
    assert len(results) == 3
    for r in results:
        assert r["text"]
        assert 0.0 <= r["similarity_score"] <= 1.0
        assert r["source_url"]
    # Exact search, so results must come back strictly ranked.
    scores = [r["similarity_score"] for r in results]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.skipif(
    not _index_built(), reason="run scripts/rebuild_vector_index.py --domain vision_zero first"
)
def test_year_filter_excludes_older_reports():
    results = search_reports("vision zero", top_k=5, year_at_least=2025)
    assert results
    assert all(r["publication_year"] >= 2025 for r in results)
    assert search_reports("vision zero", top_k=5, year_at_least=2099) == []
