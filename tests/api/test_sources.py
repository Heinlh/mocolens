"""Tests for GET /api/sources and sources_service.

Split in two: the service-level tests build their own tiny registry and
index in tmp_path, so they run in a fresh checkout and can exercise the
production-shaped case where data/raw/ and logs/ are absent. The endpoint
tests run against the real shipped artifacts and are skipped without them.
"""
import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from mocolens.api import sources_service
from mocolens.api.main import app
from mocolens.processing import curate
from mocolens.retrieval import metadata_tool
from mocolens.storage import vector_store

SOURCES_YAML = """
domains:
  test_domain:
    api_sources:
      - id: crash_incidents
        type: socrata
        title: "Crash Incidents Dataset"
        description: "Test dataset."
        url: "https://example.gov/incidents.json"
        refresh: weekly
    document_sources:
      - id: reports
        type: webpage
        title: "Vision Zero Reports"
        description: "Test reports."
        url: "https://example.gov/reports"
        allowed_domains: [example.gov]
        allowed_extensions: [pdf]
"""


def _chunk(document_id: str, index: int, **overrides) -> dict:
    record = {
        "chunk_id": f"{document_id}-{index}",
        "document_id": document_id,
        "title": f"Report {document_id}",
        "source_url": f"https://example.gov/{document_id}.pdf",
        "year": 2025,
        "domain": "test_domain",
        "page_start": index + 1,
        "page_end": index + 2,
        "section": None,
        "text": f"chunk {index}",
    }
    record.update(overrides)
    return record


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """A registry + curated dir in tmp_path, with no raw lake and no logs -
    the shape a deployed container actually has.
    """
    config_path = tmp_path / "sources.yaml"
    config_path.write_text(SOURCES_YAML, encoding="utf-8")
    monkeypatch.setattr(metadata_tool, "CONFIG_PATH", config_path)
    monkeypatch.setattr(metadata_tool, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(curate, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(curate, "LOG_PATH", tmp_path / "logs" / "curation.jsonl")
    monkeypatch.setattr(vector_store, "PERSIST_DIR", tmp_path / "data" / "curated")
    vector_store._index_cache.clear()
    yield tmp_path
    vector_store._index_cache.clear()


def _write_index(tmp_path: Path, records: list[dict]) -> None:
    vector_store.save_index(
        "test_domain", np.zeros((len(records), 384), dtype=np.float32), records
    )


def _write_build_info(tmp_path: Path, **overrides) -> None:
    info = {"domain": "test_domain", "built_at": "2026-08-31T22:00:00+00:00",
            "snapshot_date": "2026-08-30", "row_counts": {"fact_crashes": 10}}
    info.update(overrides)
    path = curate.build_info_path("test_domain")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(info), encoding="utf-8")


# --- service: no data at all ---

def test_no_index_and_no_curated_build_reports_empty_not_fabricated(isolated):
    response = sources_service.get_sources("test_domain")
    assert response.citations == []
    assert response.indexed_chunk_count == 0
    # The registry itself is still real and shown - only the freshness is unknown.
    assert [s.id for s in response.sources] == ["crash_incidents", "reports"]
    assert all(s.last_updated is None for s in response.sources)


# --- service: production shape (no raw lake, shipped artifacts only) ---

def test_freshness_falls_back_to_shipped_artifacts_when_raw_lake_is_absent(isolated):
    _write_build_info(isolated)
    _write_index(isolated, [_chunk("doc-a", 0)])

    response = sources_service.get_sources("test_domain")
    by_id = {s.id: s for s in response.sources}
    # Dataset freshness comes from the curated build's snapshot date...
    assert by_id["crash_incidents"].last_updated == "2026-08-30"
    # ...and report freshness from the index's own built_at stamp.
    assert by_id["reports"].last_updated is not None


def test_raw_lake_freshness_wins_over_the_shipped_fallback(isolated):
    _write_build_info(isolated, snapshot_date="2020-01-01")
    snapshot = isolated / "data" / "raw" / "api" / "test_domain" / "2026-09-01"
    snapshot.mkdir(parents=True)
    (snapshot / "crash_incidents.json").write_text("[]", encoding="utf-8")

    by_id = {s.id: s for s in sources_service.get_sources("test_domain").sources}
    assert by_id["crash_incidents"].last_updated == "2026-09-01"


def test_last_updated_is_a_plain_date_for_every_source_type(isolated):
    manifest = isolated / "data" / "raw" / "documents" / "test_domain" / "manifest.jsonl"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({
        "document_id": "doc-a", "downloaded_at": "2026-08-30T18:39:35.720210+00:00",
    }) + "\n", encoding="utf-8")

    for source in sources_service.get_sources("test_domain").sources:
        if source.last_updated:
            assert len(source.last_updated) == 10, source


# --- service: citations derived from the index ---

def test_citations_are_one_per_document_with_real_page_ranges(isolated):
    _write_index(isolated, [_chunk("doc-a", 0), _chunk("doc-a", 3), _chunk("doc-b", 0, year=2024)])

    response = sources_service.get_sources("test_domain")
    assert response.indexed_chunk_count == 3
    assert len(response.citations) == 2

    by_title = {c.title: c for c in response.citations}
    assert by_title["Report doc-a"].page == "1-5"  # spans both of its chunks
    assert by_title["Report doc-b"].page == "1-2"
    assert all(c.source_type == "report" for c in response.citations)


def test_citations_are_ordered_newest_first(isolated):
    _write_index(isolated, [_chunk("old", 0, year=2019), _chunk("new", 0, year=2026)])
    assert [c.published_at for c in sources_service.get_sources("test_domain").citations] == ["2026", "2019"]


def test_unknown_publication_year_is_omitted_not_guessed(isolated):
    _write_index(isolated, [_chunk("doc-a", 0, year=None)])
    assert sources_service.get_sources("test_domain").citations[0].published_at is None


def test_single_page_document_reports_one_page_not_a_range(isolated):
    _write_index(isolated, [_chunk("doc-a", 0, page_start=4, page_end=4)])
    assert sources_service.get_sources("test_domain").citations[0].page == "4"


def test_document_with_no_page_provenance_reports_no_page(isolated):
    _write_index(isolated, [_chunk("doc-a", 0, page_start=None, page_end=None)])
    assert sources_service.get_sources("test_domain").citations[0].page is None


def test_missing_document_title_is_labelled_not_left_blank(isolated):
    _write_index(isolated, [_chunk("doc-a", 0, title=None)])
    assert sources_service.get_sources("test_domain").citations[0].title == "Untitled document"


def test_unknown_domain_is_a_value_error_not_a_silent_empty_response(isolated):
    with pytest.raises(ValueError):
        sources_service.get_sources("no_such_domain")


# --- endpoint ---

pytestmark_reason = "curated artifacts not built - run the pipeline scripts first"
_has_artifacts = Path("data/curated/vision_zero/reports_index.npz").exists()
requires_artifacts = pytest.mark.skipif(not _has_artifacts, reason=pytestmark_reason)

client = TestClient(app)


@requires_artifacts
def test_sources_endpoint_returns_camel_case_contract():
    r = client.get("/api/sources")
    assert r.status_code == 200
    body = r.json()
    for key in ["sources", "citations", "indexedChunkCount"]:
        assert key in body
    assert "indexed_chunk_count" not in body
    assert body["sources"] and body["citations"]
    assert {"id", "title", "sourceType", "refreshCadence", "lastUpdated"} <= set(body["sources"][0])


@requires_artifacts
def test_sources_endpoint_lists_the_real_registry_not_prototype_data():
    ids = [s["id"] for s in client.get("/api/sources").json()["sources"]]
    assert ids == ["crash_incidents", "crash_drivers", "crash_non_motorists", "vision_zero_reports"]


@requires_artifacts
def test_sources_endpoint_citations_all_point_at_real_county_documents():
    for citation in client.get("/api/sources").json()["citations"]:
        assert citation["url"].startswith("https://")
        assert "montgomerycountymd.gov" in citation["url"]


def test_missing_registry_returns_503_not_500(monkeypatch):
    def _raise(domain=sources_service.DOMAIN):
        raise FileNotFoundError("config/sources.yaml missing")

    monkeypatch.setattr(sources_service, "get_sources", _raise)
    assert client.get("/api/sources").status_code == 503
