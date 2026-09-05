"""Tests for the scheduled refresh orchestrator (src/mocolens/refresh.py).

Every stage is stubbed: the sequencing and the failure policy are what this
module owns, and each underlying stage has its own tests. What matters here
is that one broken stage does not silently discard the work of the others,
and that a run only reports success when the artifacts it produced pass their
hard checks.
"""
import pytest

from mocolens import refresh, smoke
from mocolens.processing.quality import QualityError


@pytest.fixture
def stubbed(monkeypatch):
    """All four stages succeed, and every smoke check passes."""
    calls = []

    def ingest(domain, **kwargs):
        calls.append(("ingest", kwargs))
        if kwargs.get("api_only"):
            return {"api": {"sources_checked": 3, "records_downloaded": 120000}}
        return {"documents": {"discovered": 5, "new": 0, "changed": 1, "skipped": 4}}

    def curate_domain(domain, **kwargs):
        calls.append(("curate", kwargs))
        return {"snapshot_dir": "data/raw/api/d/2026-09-01",
                "row_counts": {"fact_crashes": 100, "fact_participants": 200}}

    def process_domain(domain, force=False):
        calls.append(("process", {"force": force}))
        return {"documents_processed": 1, "documents_skipped": 4,
                "documents_failed": 0, "chunks_created": 30}

    monkeypatch.setattr(refresh.ingestion_runner, "run", ingest)
    monkeypatch.setattr(refresh.curate, "curate_domain", curate_domain)
    monkeypatch.setattr(refresh.curate, "build_info", lambda domain: {"row_counts": {"fact_crashes": 98}})
    monkeypatch.setattr(refresh.processing_runner, "process_domain", process_domain)
    monkeypatch.setattr(refresh.smoke, "run_smoke_checks",
                        lambda domain, **kwargs: [smoke.SmokeResult("all", "hard", True, "fine")])
    return calls


def _stage(result, name):
    return next(s for s in result.stages if s.name == name)


def test_a_clean_run_reports_success_and_runs_every_stage_in_order(stubbed):
    result = refresh.run_refresh("d")
    assert result.ok
    assert [s.name for s in result.stages] == [
        "ingest_api", "ingest_documents", "curate", "process_documents",
    ]
    assert [name for name, _ in stubbed] == ["ingest", "ingest", "curate", "process"]


def test_api_and_document_ingestion_run_separately(stubbed):
    refresh.run_refresh("d")
    assert [kwargs for name, kwargs in stubbed if name == "ingest"] == [
        {"api_only": True}, {"documents_only": True},
    ]


def test_a_failed_document_crawl_still_refreshes_the_crash_tables(stubbed, monkeypatch):
    """The county's report page being down must not cost the whole refresh."""
    def ingest(domain, **kwargs):
        if kwargs.get("documents_only"):
            raise ConnectionError("montgomerycountymd.gov unreachable")
        return {"api": {"records_downloaded": 120000}}

    monkeypatch.setattr(refresh.ingestion_runner, "run", ingest)
    result = refresh.run_refresh("d")

    assert not _stage(result, "ingest_documents").ok
    assert "ConnectionError" in _stage(result, "ingest_documents").detail
    assert _stage(result, "ingest_api").ok
    assert _stage(result, "curate").ok, "curation must still run over the new API snapshot"
    assert not result.ok, "the run still reports the failure"


def test_a_quality_failure_is_reported_in_its_own_terms(stubbed, monkeypatch):
    monkeypatch.setattr(refresh.curate, "curate_domain",
                        lambda *a, **k: (_ for _ in ()).throw(QualityError("fact_crashes has zero rows")))
    result = refresh.run_refresh("d")
    assert not _stage(result, "curate").ok
    assert "quality check failed" in _stage(result, "curate").detail
    assert _stage(result, "process_documents").ok, "documents are independent of the crash tables"


def test_one_unparseable_pdf_fails_the_run_without_stopping_it(stubbed, monkeypatch):
    monkeypatch.setattr(refresh.processing_runner, "process_domain",
                        lambda domain, force=False: {"documents_processed": 4, "documents_skipped": 0,
                                                     "documents_failed": 1, "chunks_created": 90})
    result = refresh.run_refresh("d")
    assert not _stage(result, "process_documents").ok
    assert "1 failed" in _stage(result, "process_documents").detail
    assert not result.ok


def test_a_hard_smoke_failure_fails_the_run_even_when_every_stage_succeeded(stubbed, monkeypatch):
    monkeypatch.setattr(refresh.smoke, "run_smoke_checks",
                        lambda domain, **kwargs: [smoke.SmokeResult("rows_fact_crashes", "hard", False, "empty")])
    result = refresh.run_refresh("d")
    assert all(s.ok for s in result.stages)
    assert not result.ok


def test_a_soft_smoke_failure_is_reported_without_failing_the_run(stubbed, monkeypatch):
    monkeypatch.setattr(refresh.smoke, "run_smoke_checks",
                        lambda domain, **kwargs: [smoke.SmokeResult("snapshot_freshness", "soft", False, "stale")])
    result = refresh.run_refresh("d")
    assert result.ok
    assert smoke.failures(result.checks, severity="soft")


def test_row_counts_are_compared_against_the_build_this_run_replaces(stubbed, monkeypatch):
    """Captured before curation overwrites build_info.json, or the check would
    compare the new build against itself and never fire.
    """
    seen = {}
    monkeypatch.setattr(refresh.smoke, "run_smoke_checks",
                        lambda domain, previous_counts=None: seen.setdefault("previous", previous_counts) or [])
    refresh.run_refresh("d")
    assert seen["previous"] == {"fact_crashes": 98}


def test_skip_ingest_re_derives_artifacts_without_touching_the_county(stubbed):
    result = refresh.run_refresh("d", skip_ingest=True)
    assert [name for name, _ in stubbed] == ["curate", "process"]
    assert [s.name for s in result.stages] == ["curate", "process_documents"]


def test_force_documents_is_passed_through_to_processing(stubbed):
    refresh.run_refresh("d", force_documents=True)
    assert ("process", {"force": True}) in stubbed


def test_the_result_serializes_for_the_workflows_run_report(stubbed):
    payload = refresh.run_refresh("d").to_dict()
    assert payload["domain"] == "d"
    assert payload["ok"] is True
    assert {s["name"] for s in payload["stages"]} == {
        "ingest_api", "ingest_documents", "curate", "process_documents",
    }
    assert payload["checks"][0]["name"] == "all"
