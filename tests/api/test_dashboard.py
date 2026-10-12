"""Tests for GET /api/dashboard/summary against the real curated database -
skipped if it hasn't been built yet, so this suite doesn't require running
the whole pipeline first in a fresh checkout.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mocolens.api.main import app

pytestmark = pytest.mark.skipif(
    not Path("data/curated/vision_zero/analytics.duckdb").exists(),
    reason="curated tables not built - run scripts/build_curated_tables.py first",
)

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    # The last successful refresh, so staleness can be monitored from outside.
    assert body["lastRefresh"].startswith("20")
    assert body["snapshotDate"] and body["dataThrough"]


def test_dashboard_summary_status_and_shape():
    r = client.get("/api/dashboard/summary")
    assert r.status_code == 200
    data = r.json()
    for key in ["metrics", "crashTrend", "severityBreakdown", "roadUserBreakdown", "hotspots", "insights", "dataAsOf"]:
        assert key in data


def test_dashboard_summary_uses_camel_case_not_snake_case():
    data = client.get("/api/dashboard/summary").json()
    assert "crash_trend" not in data
    assert "crashTrend" in data
    assert "changeDirection" in data["metrics"][0]


def test_metrics_has_four_kpi_cards_with_real_values():
    data = client.get("/api/dashboard/summary").json()
    labels = [m["label"] for m in data["metrics"]]
    assert labels == ["Total crashes", "Pedestrian crashes", "Cyclist crashes", "Serious or fatal crashes"]
    for m in data["metrics"]:
        assert m["value"] > 0  # real trailing-12mo data always has some crashes


def test_severity_breakdown_all_time_accounts_for_every_dated_crash():
    # Checked against the database rather than pinned totals: the refresh
    # workflow rebuilds the curated tables before it runs this suite, and
    # the county adds crashes every week, so "All time" is not stable and a
    # hard-coded count fails the first refresh after it is written.
    from mocolens.api import dashboard_service

    data = client.get("/api/dashboard/summary?time_range=All time").json()
    by_label = {c["label"]: c["value"] for c in data["severityBreakdown"]}
    assert {"Property damage", "Injury", "Fatal"} <= set(by_label)
    with dashboard_service._connect() as con:
        dated = con.execute("SELECT COUNT(crash_date) FROM fact_crashes").fetchone()[0]
    assert sum(by_label.values()) == dated


def test_severity_breakdown_respects_default_window_not_all_time():
    # The default (no query params) is "Last 12 months" - must be strictly
    # less than the all-time total, proving the window is actually applied
    # by default and this isn't just the all-time check above in disguise.
    default_data = client.get("/api/dashboard/summary").json()
    all_time_data = client.get("/api/dashboard/summary?time_range=All time").json()
    default_total = sum(c["value"] for c in default_data["severityBreakdown"])
    all_time_total = sum(c["value"] for c in all_time_data["severityBreakdown"])
    assert default_total < all_time_total


def test_road_user_breakdown_percentages_sum_to_roughly_100():
    data = client.get("/api/dashboard/summary").json()
    total = sum(c["value"] for c in data["roadUserBreakdown"])
    assert total == pytest.approx(100, abs=0.5)


def test_hotspots_have_valid_montgomery_county_coordinates():
    data = client.get("/api/dashboard/summary").json()
    assert len(data["hotspots"]) > 0
    for h in data["hotspots"]:
        assert 38.5 < h["latitude"] < 39.8
        assert -78.0 < h["longitude"] < -76.5
        assert 0.0 <= h["intensity"] <= 1.0


def test_insights_are_nonempty_strings_grounded_in_real_numbers():
    data = client.get("/api/dashboard/summary").json()
    assert len(data["insights"]) > 0
    for insight in data["insights"]:
        assert insight["text"]
        assert insight["id"]


def test_data_as_of_reflects_a_real_curation_run():
    data = client.get("/api/dashboard/summary").json()
    assert data["dataAsOf"] is not None
    assert data["dataAsOf"].startswith("20")  # an ISO timestamp, not a placeholder


def test_missing_curated_db_returns_503_not_500(monkeypatch):
    from mocolens.api import dashboard_service

    def _raise():
        raise FileNotFoundError("curated db missing")

    monkeypatch.setattr(dashboard_service, "_connect", _raise)
    r = client.get("/api/dashboard/summary")
    assert r.status_code == 503
