"""Tests for GET /api/dashboard/trends and GET /api/dashboard/map.

The label and cell helpers are pure and always run. The service and endpoint
tests need the real curated database and are skipped without it, like the
existing dashboard tests.
"""
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from mocolens.api import dashboard_service as service
from mocolens.api.main import app

requires_curated = pytest.mark.skipif(
    not Path("data/curated/vision_zero/analytics.duckdb").exists(),
    reason="curated tables not built - run scripts/build_curated_tables.py first",
)

client = TestClient(app)


# --- pure helpers ---

@pytest.mark.parametrize("raw, expected", [
    ("GEORGIA AVE", "Georgia Ave"),
    ("ROCKVILLE PIKE (SB/L)", "Rockville Pike"),
    ("COLESVILLE RD (NB)", "Colesville Rd"),
    # The upstream feed concatenates the same road twice on some rows.
    ("GEORGIA AVE GEORGIA AVE", "Georgia Ave"),
    ("RANDOLPH RD RANDOLPH RD (WB/L)", "Randolph Rd"),
    # Route designators must not be title-cased into "Md 97".
    ("MD 97 NB RAMP", "MD 97 NB Ramp"),
    ("US 29", "US 29"),
    ("", None),
    (None, None),
])
def test_road_labels_are_public_readable_without_losing_the_road(raw, expected):
    assert service._clean_road_label(raw) == expected


def test_cell_label_names_the_cross_street_only_when_it_differs():
    assert service._cell_label("GEORGIA AVE", "COLESVILLE RD", 39.0, -77.0) == "Georgia Ave near Colesville Rd"
    # Same road with a direction suffix is not a cross street.
    assert service._cell_label("ROCKVILLE PIKE", "ROCKVILLE PIKE (SB/L)", 39.0, -77.0) == "Rockville Pike"
    assert service._cell_label("GEORGIA AVE", None, 39.0, -77.0) == "Georgia Ave"


def test_cell_with_no_road_name_falls_back_to_coordinates_not_a_blank_label():
    assert service._cell_label(None, None, 39.0123, -77.0456) == "39.012, -77.046"


@pytest.mark.parametrize("raw, expected", [
    ("» Continue to refine the network", "Continue to refine the network"),
    ("•  A bulleted point", "A bulleted point"),
    ("- dash bullet", "dash bullet"),
    ("� symbol-font bullet", "symbol-font bullet"),
    ("  spaced   out   text  ", "spaced out text"),
    ("   ", ""),
])
def test_quoted_report_lines_drop_bullet_glyphs_and_collapse_whitespace(raw, expected):
    assert service._clean_quoted_line(raw) == expected


def test_focus_item_splits_a_chunk_into_a_heading_and_an_excerpt():
    item = service._focus_item({
        "text": "TOP PRIORITIES\n» Refine the High Injury Network\n» Fund the work",
        "document_title": "VZ Assessment",
        "page": "5-6",
        "source_url": "https://example.gov/vz.pdf",
    })
    assert item.title == "TOP PRIORITIES"
    assert item.excerpt == "Refine the High Injury Network Fund the work"
    assert item.page == "5-6"
    assert item.url == "https://example.gov/vz.pdf"


def test_focus_excerpt_is_truncated_on_a_word_boundary():
    long_line = " ".join(["word"] * 200)
    item = service._focus_item({"text": f"HEADING\n{long_line}"})
    assert len(item.excerpt) <= service._FOCUS_EXCERPT_CHARS + 3
    assert item.excerpt.endswith("...")
    assert not item.excerpt.rstrip(".").endswith("wor")


def test_focus_item_with_only_a_heading_uses_it_as_the_excerpt_rather_than_blank():
    item = service._focus_item({"text": "Vision Zero Focus Areas"})
    assert item.title == "Vision Zero Focus Areas"
    assert item.excerpt == "Vision Zero Focus Areas"


def test_ranked_areas_number_hotspots_in_the_order_they_arrive():
    from mocolens.api import schemas

    hotspots = [
        schemas.Hotspot(id="a", area="Georgia Ave", latitude=39.0, longitude=-77.0,
                        crash_count=100, trend=5.0, intensity=1.0),
        schemas.Hotspot(id="b", area="Fenton St", latitude=39.1, longitude=-77.1,
                        crash_count=40, trend=-2.0, intensity=0.4),
    ]
    ranked = service._ranked_areas(hotspots)
    assert [(r.rank, r.name, r.crash_count) for r in ranked] == [
        (1, "Georgia Ave", 100), (2, "Fenton St", 40),
    ]


def test_ranked_areas_of_nothing_is_empty_not_an_error():
    assert service._ranked_areas([]) == []


# --- county focus panel ---

def test_county_focus_drops_passages_below_the_relevance_floor(monkeypatch):
    hits = [
        {"text": "RELEVANT\nabout priorities", "similarity_score": 0.9,
         "document_title": "A", "page": "1", "source_url": "u"},
        {"text": "UNRELATED\nabout parking meters", "similarity_score": 0.10,
         "document_title": "B", "page": "2", "source_url": "u"},
    ]
    monkeypatch.setattr(service, "search_reports", lambda *a, **k: hits)
    service._county_focus.cache_clear()
    try:
        titles = [item.title for item in service._county_focus()]
    finally:
        service._county_focus.cache_clear()
    assert titles == ["RELEVANT"]


def test_county_focus_is_empty_when_no_report_index_is_deployed(monkeypatch):
    def _missing(*args, **kwargs):
        raise FileNotFoundError("reports_index.npz missing")

    monkeypatch.setattr(service, "search_reports", _missing)
    service._county_focus.cache_clear()
    try:
        assert service._county_focus() == ()
    finally:
        service._county_focus.cache_clear()


def test_county_focus_embeds_its_query_once_per_process(monkeypatch):
    calls = []

    def _record(*args, **kwargs):
        calls.append(args)
        return []

    monkeypatch.setattr(service, "search_reports", _record)
    service._county_focus.cache_clear()
    try:
        service._county_focus()
        service._county_focus()
        service._county_focus()
    finally:
        service._county_focus.cache_clear()
    assert len(calls) == 1, "the fixed query must not re-embed on every map request"


# --- service against real data ---

@requires_curated
def test_map_hotspots_are_neighbourhood_cells_not_agency_centroids():
    hotspots = service.get_dashboard_map().hotspots
    assert hotspots, "the real dataset has crash clusters"
    assert len(hotspots) <= service.HOTSPOT_LIMIT
    assert all(h.crash_count >= service.HOTSPOT_MIN_CRASHES for h in hotspots)
    # Montgomery County's bounding box - a centroid outside it means the
    # grouping collapsed to something that is not a place.
    for h in hotspots:
        assert 38.9 <= h.latitude <= 39.4, h
        assert -77.6 <= h.longitude <= -76.9, h
    assert "Police" not in " ".join(h.area for h in hotspots)


@requires_curated
def test_map_hotspots_are_ordered_by_crash_count_with_normalized_intensity():
    hotspots = service.get_dashboard_map().hotspots
    counts = [h.crash_count for h in hotspots]
    assert counts == sorted(counts, reverse=True)
    assert hotspots[0].intensity == 1.0
    assert all(0 < h.intensity <= 1 for h in hotspots)


@requires_curated
def test_map_hotspot_labels_are_distinct_so_a_long_corridor_is_not_ambiguous():
    labels = [h.area for h in service.get_dashboard_map().hotspots]
    assert len(set(labels)) == len(labels)


@requires_curated
def test_map_respects_the_road_user_filter():
    everyone = service.get_dashboard_map(service.Filters())
    pedestrians = service.get_dashboard_map(service.Filters(road_user="Pedestrians"))
    total_all = sum(h.crash_count for h in everyone.hotspots)
    total_ped = sum(h.crash_count for h in pedestrians.hotspots)
    assert total_ped < total_all


@requires_curated
def test_map_over_a_filter_with_too_little_data_returns_nothing_rather_than_noise():
    # Fatal cyclist crashes in one window are far below the hotspot floor.
    response = service.get_dashboard_map(
        service.Filters(time_range="Last 6 months", road_user="Cyclists", severity="Fatal")
    )
    assert response.hotspots == []
    assert response.ranked_areas == []
    # The "most affected location" card cannot exist without a hotspot...
    assert all(card.label != "Most affected location" for card in response.summary_cards)


@requires_curated
def test_all_time_window_produces_no_fastest_increase_card_because_there_is_no_prior_period():
    response = service.get_dashboard_map(service.Filters(time_range="All time"))
    assert all(card.label != "Fastest increase" for card in response.summary_cards)


@requires_curated
def test_common_collision_type_excludes_the_other_bucket():
    response = service.get_dashboard_map()
    cards = {card.label: card for card in response.summary_cards}
    crash_type = cards["Most common crash type"]
    assert crash_type.primary_text.lower() != "other"
    assert "%" in crash_type.secondary_text


@requires_curated
def test_common_collision_type_share_is_measured_against_every_crash_in_the_window():
    con = duckdb.connect("data/curated/vision_zero/analytics.duckdb", read_only=True)
    try:
        window = service._resolve_window(service._latest_crash_date(con), "Last 12 months")
        label, share = service._common_collision_type(con, window, service.Filters())
        total = con.execute(
            "SELECT COUNT(*) FROM fact_crashes WHERE crash_date >= ? AND crash_date <= ?",
            [window.start, window.end],
        ).fetchone()[0]
        top = con.execute("""
            SELECT COUNT(*) FROM fact_crashes
            WHERE crash_date >= ? AND crash_date <= ?
              AND collision_type IS NOT NULL AND collision_type <> 'OTHER'
            GROUP BY collision_type ORDER BY 1 DESC LIMIT 1
        """, [window.start, window.end]).fetchone()[0]
    finally:
        con.close()
    assert share == round(top / total * 100, 1)
    assert label


@requires_curated
def test_trends_matches_the_summary_endpoints_series_for_the_same_filters():
    filters = service.Filters(time_range="Last 6 months", road_user="Pedestrians")
    trends = service.get_dashboard_trends(filters)
    summary = service.get_dashboard_summary(filters)
    assert trends.crash_trend == summary.crash_trend
    assert trends.severity_breakdown == summary.severity_breakdown
    assert trends.road_user_breakdown == summary.road_user_breakdown


@requires_curated
def test_trends_time_range_actually_changes_the_series():
    twelve = service.get_dashboard_trends(service.Filters(time_range="Last 12 months"))
    six = service.get_dashboard_trends(service.Filters(time_range="Last 6 months"))
    assert len(twelve.crash_trend) > len(six.crash_trend)


# --- endpoints ---

@requires_curated
def test_trends_endpoint_shape_is_camel_case():
    body = client.get("/api/dashboard/trends").json()
    assert set(body) == {"crashTrend", "severityBreakdown", "roadUserBreakdown", "dataAsOf"}
    assert body["crashTrend"]


@requires_curated
def test_map_endpoint_shape_is_camel_case():
    body = client.get("/api/dashboard/map").json()
    assert set(body) == {"hotspots", "rankedAreas", "summaryCards", "countyFocus", "dataAsOf"}
    assert {"crashCount", "intensity", "latitude", "longitude", "area"} <= set(body["hotspots"][0])
    assert {"rank", "name", "crashCount", "trend"} == set(body["rankedAreas"][0])
    assert {"label", "primaryText", "secondaryText"} == set(body["summaryCards"][0])


@requires_curated
def test_map_endpoint_county_focus_quotes_real_cited_documents():
    for item in client.get("/api/dashboard/map").json()["countyFocus"]:
        assert item["title"] and item["excerpt"]
        assert item["url"].startswith("https://")


@requires_curated
def test_dashboard_endpoints_pass_filters_through_to_sql():
    unfiltered = client.get("/api/dashboard/trends").json()
    filtered = client.get("/api/dashboard/trends?road_user=Cyclists").json()
    assert sum(p["value"] for p in filtered["crashTrend"]) < sum(p["value"] for p in unfiltered["crashTrend"])


@pytest.mark.parametrize("path", ["/api/dashboard/trends", "/api/dashboard/map"])
def test_missing_curated_db_returns_503_not_500(monkeypatch, path):
    def _raise():
        raise FileNotFoundError("curated db missing")

    monkeypatch.setattr(service, "_connect", _raise)
    assert client.get(path).status_code == 503
