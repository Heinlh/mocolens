import json

import pytest

from mocolens.retrieval import metadata_tool

SOURCES_YAML = """
domains:
  vision_zero:
    api_sources:
      - id: crash_incidents
        type: socrata
        title: "Crash Incidents Dataset"
        description: "Test dataset."
        url: "https://example.gov/incidents.json"
        refresh: weekly
    document_sources:
      - id: vision_zero_reports
        type: webpage
        title: "Vision Zero Reports"
        description: "Test reports."
        url: "https://example.gov/reports"
        allowed_domains: [example.gov]
        allowed_extensions: [pdf]
"""


@pytest.fixture
def fixture_env(tmp_path, monkeypatch):
    config_path = tmp_path / "sources.yaml"
    config_path.write_text(SOURCES_YAML, encoding="utf-8")
    monkeypatch.setattr(metadata_tool, "CONFIG_PATH", config_path)
    monkeypatch.setattr(metadata_tool, "DATA_DIR", tmp_path / "data")
    return tmp_path


def test_source_with_no_data_ingested_yet_reports_none_not_fabricated(fixture_env):
    sources = metadata_tool.get_source_metadata("vision_zero")
    by_id = {s["id"]: s for s in sources}

    assert by_id["crash_incidents"]["last_updated"] is None
    assert by_id["crash_incidents"]["record_count"] is None
    assert by_id["vision_zero_reports"]["last_updated"] is None
    assert by_id["vision_zero_reports"]["record_count"] == 0


def test_api_source_freshness_from_latest_snapshot(fixture_env):
    snapshot_dir = fixture_env / "data" / "raw" / "api" / "vision_zero" / "2026-01-15"
    snapshot_dir.mkdir(parents=True)
    (snapshot_dir / "crash_incidents.json").write_text(json.dumps([{"a": 1}, {"a": 2}, {"a": 3}]), encoding="utf-8")

    older_dir = fixture_env / "data" / "raw" / "api" / "vision_zero" / "2025-01-01"
    older_dir.mkdir(parents=True)
    (older_dir / "crash_incidents.json").write_text(json.dumps([{"a": 1}]), encoding="utf-8")

    sources = metadata_tool.get_source_metadata("vision_zero")
    incidents = next(s for s in sources if s["id"] == "crash_incidents")
    assert incidents["last_updated"] == "2026-01-15"  # the later date, not the older one
    assert incidents["record_count"] == 3
    assert incidents["type"] == "dataset"
    assert incidents["title"] == "Crash Incidents Dataset"
    assert incidents["refresh_cadence"] == "weekly"


def test_document_source_freshness_from_manifest(fixture_env):
    doc_dir = fixture_env / "data" / "raw" / "documents" / "vision_zero"
    doc_dir.mkdir(parents=True)
    manifest = doc_dir / "manifest.jsonl"
    manifest.write_text(
        json.dumps({"document_id": "d1", "downloaded_at": "2026-01-01T00:00:00+00:00"}) + "\n" +
        json.dumps({"document_id": "d2", "downloaded_at": "2026-03-01T00:00:00+00:00"}) + "\n",
        encoding="utf-8",
    )

    sources = metadata_tool.get_source_metadata("vision_zero")
    reports = next(s for s in sources if s["id"] == "vision_zero_reports")
    assert reports["record_count"] == 2
    assert reports["last_updated"] == "2026-03-01T00:00:00+00:00"  # the later of the two
    assert reports["type"] == "report_collection"


def test_unknown_domain_raises(fixture_env):
    with pytest.raises(ValueError, match="No source registry entry"):
        metadata_tool.get_source_metadata("nonexistent_domain")


def test_source_missing_optional_metadata_falls_back_to_id(tmp_path, monkeypatch):
    minimal_yaml = tmp_path / "sources.yaml"
    minimal_yaml.write_text(
        "domains:\n  vision_zero:\n    api_sources:\n      - id: bare_source\n        type: socrata\n        url: 'https://x'\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(metadata_tool, "CONFIG_PATH", minimal_yaml)
    monkeypatch.setattr(metadata_tool, "DATA_DIR", tmp_path / "data")

    sources = metadata_tool.get_source_metadata("vision_zero")
    assert sources[0]["title"] == "bare_source"  # fell back to id, didn't crash
    assert sources[0]["description"] == ""


def test_against_real_project_config_and_data():
    """Live check against the real config/sources.yaml and whatever has
    actually been ingested - skipped if the extract layer hasn't been run.
    """
    from pathlib import Path
    if not Path("data/raw/api/vision_zero").exists():
        pytest.skip("extract layer not run - run scripts/ingest.py first")

    sources = metadata_tool.get_source_metadata("vision_zero")
    assert len(sources) == 4  # 3 API + 1 document source, per config/sources.yaml
    by_id = {s["id"]: s for s in sources}
    assert by_id["crash_incidents"]["record_count"] == 124_770  # exact known count of the raw snapshot
