"""Fast, isolated tests for the dashboard filter engine (time window
resolution + area/road_user/severity SQL). Imports only dashboard_service,
not mocolens.api.main - main.py's import chain pulls in the agent
(langchain_openai/langgraph), which is what makes tests/api/test_dashboard.py
slow. These run against a tiny in-memory fixture instead of the real
curated database, so every expected number below is hand-computed, not
just "whatever the real data happens to say today."

Fixture, anchored on latest = 2026-08-20 (C1's date):
  C1  2026-08-20  Rockville Police             property_damage  (no ped/cyclist)
  C2  2026-02-10  Montgomery County Police     injury           pedestrian_involved
  C3  2025-09-15  Gaithersburg Police          fatal            cyclist_involved
  C4  2024-12-01  Rockville Police             property_damage  (falls in the PRIOR
                                                                  12-month window, not current)
  C5  2020-01-01  Takoma Park Police           injury           pedestrian_involved

Participants: P1 driver/no_apparent_injury on C1, P2 pedestrian/possible_injury
on C2, P3 cyclist/fatal_injury on C3, P4 driver/suspected_serious_injury on C4
(tests that "Serious injury" matches via the participant signal even though
C4's own crash-level severity says property_damage - the same real-world
signal mismatch already documented in transforms/vision_zero.py), P5
pedestrian/no_apparent_injury on C5.
"""
import duckdb
import pytest

from mocolens.api import dashboard_service as svc


@pytest.fixture
def con(monkeypatch):
    c = duckdb.connect(":memory:")
    c.execute("""
        CREATE TABLE fact_crashes AS SELECT * FROM (VALUES
            ('C1', DATE '2026-08-20', 39.0, -77.0, 'Rockville Police', 'property_damage', false, false),
            ('C2', DATE '2026-02-10', 39.0, -77.0, 'Montgomery County Police', 'injury', true, false),
            ('C3', DATE '2025-09-15', 39.0, -77.0, 'Gaithersburg Police', 'fatal', false, true),
            ('C4', DATE '2024-12-01', 39.0, -77.0, 'Rockville Police', 'property_damage', false, false),
            ('C5', DATE '2020-01-01', 39.0, -77.0, 'Takoma Park Police', 'injury', true, false)
        ) AS t(crash_id, crash_date, latitude, longitude, agency_name, severity,
               pedestrian_involved, cyclist_involved)
    """)
    c.execute("""
        CREATE TABLE fact_participants AS SELECT * FROM (VALUES
            ('P1', 'C1', 'driver', 'no_apparent_injury'),
            ('P2', 'C2', 'pedestrian', 'possible_injury'),
            ('P3', 'C3', 'cyclist', 'fatal_injury'),
            ('P4', 'C4', 'driver', 'suspected_serious_injury'),
            ('P5', 'C5', 'pedestrian', 'no_apparent_injury')
        ) AS t(participant_id, crash_id, participant_type, injury_severity)
    """)
    monkeypatch.setattr(svc, "_connect", lambda: c)
    yield c
    c.close()


def _total(con, filters=None):
    return svc.get_dashboard_summary(filters or svc.Filters()).metrics[0]


# --- time window resolution ---

def test_default_is_last_12_months(con):
    m = _total(con)
    assert m.value == 3  # C1, C2, C3 (C4 is in 2024, outside [2025-08-20, 2026-08-20])


def test_prior_period_used_for_comparison(con):
    m = _total(con)
    # prior window [2024-08-20, 2025-08-20) holds only C4 -> percent_change(1, 3)
    assert m.change == pytest.approx(200.0)


def test_last_6_months_excludes_february_crash(con):
    m = _total(con, svc.Filters(time_range="Last 6 months"))
    # window start = 2026-02-20; C2 is 2026-02-10, just before it
    assert m.value == 1  # only C1


def test_year_to_date_includes_only_2026_crashes(con):
    m = _total(con, svc.Filters(time_range="Year to date"))
    assert m.value == 2  # C1 and C2; C3/C4/C5 are all before 2026-01-01


def test_all_time_includes_every_crash_and_has_no_comparison(con):
    m = _total(con, svc.Filters(time_range="All time"))
    assert m.value == 5
    assert m.change is None


def test_all_time_crash_trend_groups_by_year_not_month(con):
    r = svc.get_dashboard_summary(svc.Filters(time_range="All time"))
    labels = [p.label for p in r.crash_trend]
    assert labels == ["2020", "2024", "2025", "2026"]


def test_default_window_crash_trend_groups_by_month(con):
    r = svc.get_dashboard_summary(svc.Filters())
    for point in r.crash_trend:
        assert "'" in point.label  # e.g. "Aug '26" - month-style label, not a bare year


# --- area / road_user / severity filters, real SQL not client-side ---

def test_area_filter_restricts_to_one_agency(con):
    m = _total(con, svc.Filters(area="Rockville Police"))
    # only C1 is Rockville AND inside the current 12mo window (C4 is Rockville
    # too, but it's in the prior period, not counted in "current")
    assert m.value == 1


def test_area_filter_does_not_narrow_hotspots(con):
    # Deliberate exception (see dashboard_service.py's module docstring):
    # hotspots is the "by area" breakdown, and the frontend's Area dropdown
    # is populated from hotspots.map(h => h.area) - if hotspots came back
    # pre-narrowed to the selected area, every other option would vanish
    # from the dropdown the instant one was picked. Area still genuinely
    # filters everything else (KPIs, charts) - just not this one.
    r = svc.get_dashboard_summary(svc.Filters(area="Rockville Police"))
    areas = {h.area for h in r.hotspots}
    assert areas == {"Rockville Police", "Montgomery County Police", "Gaithersburg Police"}
    assert r.metrics[0].value == 1  # but the KPI *is* narrowed to Rockville (just C1)


def test_road_user_pedestrians_filters_crash_level_flag(con):
    r = svc.get_dashboard_summary(svc.Filters(road_user="Pedestrians"))
    assert r.metrics[0].value == 1  # only C2
    assert r.metrics[2].value == 0  # "Cyclist crashes" KPI - none of the pedestrian crashes also involve a cyclist


def test_road_user_drivers_excludes_pedestrian_and_cyclist_crashes(con):
    m = _total(con, svc.Filters(road_user="Drivers"))
    assert m.value == 1  # only C1 (C2 is pedestrian, C3 is cyclist)


def test_severity_fatal_filters_crash_level_severity(con):
    m = _total(con, svc.Filters(severity="Fatal"))
    assert m.value == 1  # only C3


def test_severity_serious_injury_matches_via_participant_signal_not_crash_severity(con):
    # C4's own severity column says 'property_damage', but it has a
    # suspected_serious_injury participant - "Serious injury" must catch it
    # via that signal, same cross-check pattern as the curation layer's own
    # fatal_severity_without_fatality_count check. Use "All time" so C4
    # (in the prior period for the default window) isn't window-excluded.
    m = _total(con, svc.Filters(severity="Serious injury", time_range="All time"))
    assert m.value == 1


def test_filters_compose_with_and(con):
    # Rockville + property_damage matches C1 and C4; windowed to "All time"
    # so both are visible regardless of the current/prior split.
    m = _total(con, svc.Filters(area="Rockville Police", severity="Property damage only", time_range="All time"))
    assert m.value == 2


def test_no_matching_rows_degrades_metrics_to_zero_not_a_crash(con):
    r = svc.get_dashboard_summary(svc.Filters(area="Rockville Police", severity="Fatal"))
    assert r.metrics[0].value == 0
    assert r.severity_breakdown == []


def test_no_matching_rows_degrades_hotspots_to_empty_not_a_crash(con):
    # hotspots ignores the area filter (see above), but still respects
    # road_user/severity - this combo has no match in either dimension.
    r = svc.get_dashboard_summary(svc.Filters(road_user="Cyclists", severity="Fatal", time_range="Last 6 months"))
    assert r.hotspots == []


# --- road_user_breakdown / severity_breakdown reflect the same filters ---

def test_road_user_breakdown_reflects_area_filter(con):
    r = svc.get_dashboard_summary(svc.Filters(area="Gaithersburg Police"))
    labels = {c.label for c in r.road_user_breakdown}
    assert labels == {"Cyclists"}  # only C3's participant (P3, cyclist) is in Gaithersburg


def test_severity_breakdown_reflects_time_range_filter(con):
    r = svc.get_dashboard_summary(svc.Filters(time_range="Last 6 months"))
    # only C1 (property_damage) is in the last 6 months
    assert [c.label for c in r.severity_breakdown] == ["Property damage"]


# --- insights adapt their wording to the window ---

def test_insights_skip_trend_sentence_for_all_time(con):
    r = svc.get_dashboard_summary(svc.Filters(time_range="All time"))
    assert not any(i.id == "trend" for i in r.insights)


def test_insights_include_trend_sentence_with_window_label_for_bounded_windows(con):
    r = svc.get_dashboard_summary(svc.Filters())
    trend = next(i for i in r.insights if i.id == "trend")
    assert "the last 12 months" in trend.text
