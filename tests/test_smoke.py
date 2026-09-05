"""Tests for the post-refresh smoke checks (src/mocolens/smoke.py).

Each test builds a tiny but real artifact set in tmp_path - a genuine DuckDB
file, a genuine .npz index - so the checks run against the same file formats
the serving path opens, not against mocks of them.
"""
import json
from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pytest

from mocolens import smoke
from mocolens.processing import curate
from mocolens.storage import vector_store


@pytest.fixture
def artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(smoke, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(curate, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(curate, "LOG_PATH", tmp_path / "logs" / "curation.jsonl")
    monkeypatch.setattr(vector_store, "PERSIST_DIR", tmp_path / "data" / "curated")
    vector_store._index_cache.clear()
    yield tmp_path
    vector_store._index_cache.clear()


def _build_curated(root: Path, *, crashes: int = 100, participants: int = 200,
                   latest: str = "2026-08-26") -> None:
    db_path = root / "data" / "curated" / "d" / "analytics.duckdb"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    con.execute(f"""
        CREATE TABLE fact_crashes AS
        SELECT 'C' || i AS crash_id,
               DATE '{latest}' - INTERVAL (i) DAY AS crash_date
        FROM range({crashes}) t(i)
    """)
    con.execute(f"""
        CREATE TABLE fact_participants AS
        SELECT 'P' || i AS participant_id, 'C' || (i % {crashes}) AS crash_id
        FROM range({participants}) t(i)
    """)
    con.close()


def _write_build_info(root: Path, **overrides) -> None:
    info = {"domain": "d", "built_at": "2026-08-31T22:00:00+00:00",
            "snapshot_date": "2026-08-30", "row_counts": {"fact_crashes": 100}}
    info.update(overrides)
    path = curate.build_info_path("d")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(info), encoding="utf-8")


def _write_index(root: Path, document_ids: list[str]) -> None:
    records = [
        {"chunk_id": f"{doc}:0", "document_id": doc, "title": doc, "text": "vision zero safety",
         "source_url": "u", "year": 2025}
        for doc in document_ids
    ]
    vector_store.save_index("d", np.zeros((len(records), 384), dtype=np.float32), records)


def _write_manifest(root: Path, document_ids: list[str]) -> None:
    path = root / "data" / "raw" / "documents" / "d" / "manifest.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps({"document_id": doc}) + "\n" for doc in document_ids),
                    encoding="utf-8")


def _by_name(results) -> dict:
    return {r.name: r for r in results}


# --- build info ---

def test_missing_build_info_fails_hard(artifacts):
    assert smoke._check_build_info("d") == smoke.SmokeResult(
        name="build_info", severity="hard", passed=False,
        detail=f"{curate.build_info_path('d')} missing or unreadable",
    )


def test_incomplete_build_info_names_the_missing_fields(artifacts):
    _write_build_info(artifacts, snapshot_date=None)
    result = smoke._check_build_info("d")
    assert not result.passed
    assert "snapshot_date" in result.detail


def test_complete_build_info_passes(artifacts):
    _write_build_info(artifacts)
    assert smoke._check_build_info("d").passed


# --- freshness ---

def test_a_stale_snapshot_is_a_soft_failure_not_a_blocking_one(artifacts):
    _write_build_info(artifacts, snapshot_date="2026-01-01")
    result = smoke._check_snapshot_freshness("d", date(2026, 9, 3))
    assert not result.passed
    assert result.severity == "soft"
    assert "245 days old" in result.detail


def test_a_recent_snapshot_passes(artifacts):
    _write_build_info(artifacts, snapshot_date="2026-08-30")
    assert smoke._check_snapshot_freshness("d", date(2026, 9, 3)).passed


def test_an_unparseable_snapshot_date_is_reported_not_raised(artifacts):
    _write_build_info(artifacts, snapshot_date="last tuesday")
    result = smoke._check_snapshot_freshness("d", date(2026, 9, 3))
    assert not result.passed
    assert "unparseable" in result.detail


# --- curated tables ---

def test_missing_curated_database_fails(artifacts):
    results = smoke._check_curated_tables("d", None)
    assert len(results) == 1 and not results[0].passed


def test_populated_curated_tables_pass(artifacts):
    _build_curated(artifacts)
    results = _by_name(smoke._check_curated_tables("d", None))
    assert results["rows_fact_crashes"].passed
    assert results["rows_fact_participants"].passed
    assert results["crash_coverage"].passed
    assert "2026-08-26" in results["crash_coverage"].detail


def test_an_empty_fact_table_fails(artifacts):
    _build_curated(artifacts, crashes=0, participants=0)
    results = _by_name(smoke._check_curated_tables("d", None))
    assert not results["rows_fact_crashes"].passed
    assert "empty" in results["rows_fact_crashes"].detail


def test_a_partial_extract_that_loses_most_rows_fails(artifacts):
    """A truncated Socrata response still builds a valid table - only the
    comparison against the previous build reveals it.
    """
    _build_curated(artifacts, crashes=50, participants=100)
    results = _by_name(smoke._check_curated_tables("d", {"fact_crashes": 124769}))
    assert not results["rows_fact_crashes"].passed
    assert "124,769" in results["rows_fact_crashes"].detail


def test_normal_week_to_week_growth_passes_the_row_comparison(artifacts):
    _build_curated(artifacts, crashes=100)
    results = _by_name(smoke._check_curated_tables("d", {"fact_crashes": 98}))
    assert results["rows_fact_crashes"].passed


def test_a_small_expected_correction_is_not_treated_as_a_partial_extract(artifacts):
    # 5% fewer rows after an upstream dedupe - under the 10% tolerance.
    _build_curated(artifacts, crashes=95)
    assert _by_name(smoke._check_curated_tables("d", {"fact_crashes": 100}))["rows_fact_crashes"].passed


# --- report index ---

def test_missing_index_fails(artifacts):
    results = smoke._check_report_index("d")
    assert len(results) == 1 and not results[0].passed


def test_index_and_manifest_agreeing_passes(artifacts):
    _write_index(artifacts, ["doc-a", "doc-b"])
    _write_manifest(artifacts, ["doc-a", "doc-b"])
    results = _by_name(smoke._check_report_index("d"))
    assert results["report_index"].passed
    assert results["index_matches_manifest"].passed


def test_an_indexed_document_missing_from_the_manifest_fails(artifacts):
    """Chunks the agent could cite with no source record behind them."""
    _write_index(artifacts, ["doc-a", "orphan"])
    _write_manifest(artifacts, ["doc-a"])
    results = _by_name(smoke._check_report_index("d"))
    assert not results["index_matches_manifest"].passed
    assert "1 indexed document(s)" in results["index_matches_manifest"].detail


def test_manifest_comparison_is_skipped_where_no_raw_lake_is_deployed(artifacts):
    # The container image ships the index but not data/raw - the check has
    # nothing to compare against and must not invent a failure.
    _write_index(artifacts, ["doc-a"])
    assert "index_matches_manifest" not in _by_name(smoke._check_report_index("d"))


def test_an_empty_index_fails(artifacts):
    _write_index(artifacts, [])
    results = smoke._check_report_index("d")
    assert not results[0].passed
    assert "no chunks" in results[0].detail


# --- retrieval and API, end to end ---

def test_report_search_failure_is_reported_not_raised(artifacts, monkeypatch):
    monkeypatch.setattr("mocolens.retrieval.report_tool.search_reports",
                        lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("index missing")))
    result = smoke._check_report_search("d")
    assert not result.passed
    assert "index missing" in result.detail


def test_report_search_returning_nothing_for_an_on_topic_query_fails(artifacts, monkeypatch):
    monkeypatch.setattr("mocolens.retrieval.report_tool.search_reports", lambda *a, **k: [])
    assert not smoke._check_report_search("d").passed


def test_a_dashboard_that_cannot_build_fails_the_refresh(artifacts, monkeypatch):
    monkeypatch.setattr("mocolens.api.dashboard_service.get_dashboard_summary",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no such table")))
    result = smoke._check_dashboard_builds("d")
    assert not result.passed
    assert "RuntimeError: no such table" in result.detail


# --- aggregation ---

def test_failures_filters_by_severity():
    results = [
        smoke.SmokeResult("a", "hard", False, ""),
        smoke.SmokeResult("b", "soft", False, ""),
        smoke.SmokeResult("c", "hard", True, ""),
    ]
    assert [r.name for r in smoke.failures(results)] == ["a"]
    assert [r.name for r in smoke.failures(results, severity="soft")] == ["b"]


def test_summarize_counts_passes():
    results = [smoke.SmokeResult("a", "hard", True, ""), smoke.SmokeResult("b", "hard", False, "")]
    assert smoke.summarize(results) == "1/2 smoke checks passed"


@pytest.mark.skipif(
    not Path("data/curated/vision_zero/analytics.duckdb").exists(),
    reason="curated tables not built - run the pipeline scripts first",
)
def test_the_real_shipped_artifacts_pass_every_hard_check():
    results = smoke.run_smoke_checks("vision_zero")
    assert smoke.failures(results) == [], [str(r) for r in results]
