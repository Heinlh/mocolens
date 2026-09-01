from unittest.mock import patch

from mocolens.retrieval.report_tool import _build_where, _format_page, search_reports


def test_format_page_single():
    assert _format_page(18, 18) == "18"


def test_format_page_none():
    assert _format_page(18, None) == "18"


def test_format_page_range():
    assert _format_page(14, 15) == "14-15"


def test_format_page_missing():
    assert _format_page(None, None) is None


def test_build_where_none_filters():
    assert _build_where(None) is None
    assert _build_where({}) is None


def test_build_where_single_allowed_field():
    assert _build_where({"year": 2025}) == {"year": 2025}


def test_build_where_operator_value_passed_through():
    assert _build_where({"year": {"$gte": 2023}}) == {"year": {"$gte": 2023}}


def test_build_where_multiple_fields_wrapped_in_and():
    where = _build_where({"year": 2025, "domain": "vision_zero"})
    assert where == {"$and": [{"year": 2025}, {"domain": "vision_zero"}]}


def test_build_where_drops_unknown_fields():
    # an unindexed filter field would make Chroma raise - drop it instead
    assert _build_where({"not_a_real_field": "x"}) is None
    assert _build_where({"year": 2025, "not_a_real_field": "x"}) == {"year": 2025}


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
    mock_search.assert_called_once_with("vision_zero", "pedestrian safety", top_k=1, where=None)


@patch("mocolens.retrieval.report_tool.vector_store.search")
def test_search_reports_passes_filters_and_domain_through(mock_search):
    mock_search.return_value = []
    search_reports("query", filters={"year": {"$gte": 2023}}, top_k=3, domain="vision_zero")
    mock_search.assert_called_once_with("vision_zero", "query", top_k=3, where={"year": {"$gte": 2023}})


@patch("mocolens.retrieval.report_tool.vector_store.search")
def test_search_reports_empty_results(mock_search):
    mock_search.return_value = []
    assert search_reports("nothing matches this") == []


def test_search_reports_against_real_index():
    """Live check against the actual Chroma index built earlier in the project,
    if it exists - skipped otherwise so this suite doesn't depend on pipeline
    state to pass in a fresh checkout.
    """
    from pathlib import Path
    if not Path("data/curated/vision_zero/chroma").exists():
        import pytest
        pytest.skip("vector index not built - run scripts/rebuild_vector_index.py first")

    results = search_reports("pedestrian safety improvements", top_k=3)
    assert len(results) == 3
    for r in results:
        assert r["text"]
        assert 0.0 <= r["similarity_score"] <= 1.0
        assert r["source_url"]
