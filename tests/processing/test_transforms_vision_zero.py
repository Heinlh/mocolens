"""Exercises the vision_zero transform against a small synthetic snapshot
built to reproduce every real-data quirk found in the actual Montgomery
County Socrata download (see transforms/vision_zero.py's module docstring):
mixed-case enums, an exact duplicate crash row, a null injury_severity, an
out-of-bounds coordinate, an orphaned participant, an unparseable date, and
an unrecognized severity string.
"""
import json

import duckdb
import pytest

from mocolens.processing.transforms import vision_zero

INCIDENTS = [
    {
        "report_number": "C1", "crash_date_time": "2023-05-01T10:00:00.000",
        "latitude": "39.05", "longitude": "-77.10",
        "acrs_report_type": "Injury Crash", "collision_type": "Angle",
        "weather": "Clear", "light": "Daylight", "surface_condition": "Dry",
        "hit_run": "No", "cross_street_name": "MAIN ST",
        "agency_name": "ROCKVILLE", "route_type": "County Route",
    },
    {
        # exact duplicate of C1 - tests dedup + the duplicate-detection check
        "report_number": "C1", "crash_date_time": "2023-05-01T10:00:00.000",
        "latitude": "39.05", "longitude": "-77.10",
        "acrs_report_type": "Injury Crash", "collision_type": "Angle",
        "weather": "Clear", "light": "Daylight", "surface_condition": "Dry",
        "hit_run": "No", "cross_street_name": "MAIN ST",
        "agency_name": "ROCKVILLE", "route_type": "County Route",
    },
    {
        # out-of-bounds latitude (not a real MoCo coordinate), lowercase severity
        "report_number": "C2", "crash_date_time": "2023-06-01T10:00:00.000",
        "latitude": "90.0", "longitude": "-77.10",
        "acrs_report_type": "fatal crash", "collision_type": "Head On",
        "weather": "Rain", "light": "Dark - Lighted", "surface_condition": "Wet",
        "hit_run": "Yes", "cross_street_name": "OAK AVE",
        "agency_name": "MONTGOMERY", "route_type": "Maryland (State)",
    },
    {
        # every optional field null - must pass through cleanly, not crash
        "report_number": "C3", "crash_date_time": "2023-07-01T10:00:00.000",
        "latitude": "39.10", "longitude": "-77.20",
        "acrs_report_type": "PROPERTY DAMAGE CRASH", "collision_type": None,
        "weather": None, "light": None, "surface_condition": None,
        "hit_run": "No", "cross_street_name": None,
        "agency_name": "GAITHERSBURG", "route_type": None,
    },
    {
        # classified fatal by police but will end up with zero fatal participants.
        # Also uses the truncated title-case form of the SAME agency as C1's
        # "ROCKVILLE" - both must normalize to one canonical name.
        "report_number": "C4", "crash_date_time": "2023-08-01T10:00:00.000",
        "latitude": "39.02", "longitude": "-77.05",
        "acrs_report_type": "Fatal Crash", "collision_type": "Rear End",
        "weather": "Clear", "light": "Daylight", "surface_condition": "Dry",
        "hit_run": "No", "cross_street_name": "ELM ST",
        "agency_name": "Rockville Police Departme", "route_type": "County Route",
    },
    {
        # unparseable date, unrecognized severity string, AND an unrecognized
        # agency name (tests the passthrough + its quality check together)
        "report_number": "C5", "crash_date_time": "not-a-date",
        "latitude": "39.00", "longitude": "-77.00",
        "acrs_report_type": "Unknown Type", "collision_type": "Angle",
        "weather": "Clear", "light": "Daylight", "surface_condition": "Dry",
        "hit_run": "No", "cross_street_name": "PINE ST",
        "agency_name": "Some New PD", "route_type": "County Route",
    },
]

DRIVERS = [
    {"person_id": "D1", "report_number": "C1", "injury_severity": "No Apparent Injury", "driver_at_fault": "Yes"},
    {"person_id": "D2", "report_number": "C2", "injury_severity": "FATAL INJURY", "driver_at_fault": "No"},
    {"person_id": None, "report_number": "C3", "injury_severity": "Possible Injury", "driver_at_fault": "No"},
    {"person_id": "D_orphan", "report_number": "C_NOT_IN_INCIDENTS", "injury_severity": "Possible Injury", "driver_at_fault": "No"},
]

NON_MOTORISTS = [
    {"person_id": "N1", "report_number": "C1", "pedestrian_type": "PEDESTRIAN", "injury_severity": "Suspected Minor Injury", "at_fault": "No"},
    {"person_id": "N2", "report_number": "C1", "pedestrian_type": "Cyclist (Electric)", "injury_severity": None, "at_fault": "Unknown"},
    {"person_id": "N3", "report_number": "C2", "pedestrian_type": "Scooter (electric)", "injury_severity": "Possible Injury", "at_fault": "Yes"},
]


@pytest.fixture
def built(tmp_path):
    (tmp_path / "crash_incidents.json").write_text(json.dumps(INCIDENTS), encoding="utf-8")
    (tmp_path / "crash_drivers.json").write_text(json.dumps(DRIVERS), encoding="utf-8")
    (tmp_path / "crash_non_motorists.json").write_text(json.dumps(NON_MOTORISTS), encoding="utf-8")

    con = duckdb.connect(":memory:")
    report = vision_zero.build(con, tmp_path)
    yield con, report
    con.close()


def _row(con, crash_id):
    cols = [d[0] for d in con.execute("SELECT * FROM fact_crashes WHERE crash_id = ?", [crash_id]).description]
    row = con.execute("SELECT * FROM fact_crashes WHERE crash_id = ?", [crash_id]).fetchone()
    return dict(zip(cols, row))


def test_missing_snapshot_raises_clear_error(tmp_path):
    con = duckdb.connect(":memory:")
    with pytest.raises(FileNotFoundError):
        vision_zero.build(con, tmp_path)  # empty dir, no JSON files
    con.close()


def test_empty_json_array_raises_clear_error_not_a_binder_exception(tmp_path):
    # A `[]` extract gives DuckDB's read_json_auto nothing to infer a schema
    # from - it silently becomes one untyped "json" column instead of the
    # real fields, and every downstream column reference would otherwise
    # blow up with a cryptic BinderException instead of a clear message.
    (tmp_path / "crash_incidents.json").write_text("[]", encoding="utf-8")
    (tmp_path / "crash_drivers.json").write_text("[]", encoding="utf-8")
    (tmp_path / "crash_non_motorists.json").write_text("[]", encoding="utf-8")

    con = duckdb.connect(":memory:")
    with pytest.raises(ValueError, match="zero records"):
        vision_zero.build(con, tmp_path)
    con.close()


def test_row_count_after_dedup(built):
    con, _ = built
    # 6 incident rows in, one exact duplicate -> 5 distinct crashes
    assert con.execute("SELECT COUNT(*) FROM fact_crashes").fetchone()[0] == 5


def test_crash_id_is_unique_and_not_null(built):
    con, _ = built
    dupes = con.execute(
        "SELECT COUNT(*) FROM (SELECT crash_id FROM fact_crashes GROUP BY crash_id HAVING COUNT(*) > 1)"
    ).fetchone()[0]
    nulls = con.execute("SELECT COUNT(*) FROM fact_crashes WHERE crash_id IS NULL").fetchone()[0]
    assert dupes == 0
    assert nulls == 0


def test_severity_case_normalization(built):
    con, _ = built
    assert _row(con, "C1")["severity"] == "injury"
    assert _row(con, "C2")["severity"] == "fatal"  # from lowercase "fatal crash"
    assert _row(con, "C3")["severity"] == "property_damage"
    assert _row(con, "C5")["severity"] == "unknown"  # unrecognized string, not dropped


def test_agency_name_normalized_across_variant_forms(built):
    # C1 uses "ROCKVILLE", C4 uses the truncated "Rockville Police Departme" -
    # same real agency, must collapse to one canonical name.
    con, _ = built
    assert _row(con, "C1")["agency_name"] == "Rockville Police"
    assert _row(con, "C4")["agency_name"] == "Rockville Police"


def test_unrecognized_agency_name_passed_through_not_dropped(built):
    con, _ = built
    assert _row(con, "C5")["agency_name"] == "Some New PD"


def test_null_optional_fields_pass_through(built):
    con, _ = built
    c3 = _row(con, "C3")
    assert c3["collision_type"] is None
    assert c3["road_name"] is None
    assert c3["weather"] is None


def test_out_of_bounds_coordinates_nulled_but_row_kept(built):
    con, _ = built
    c2 = _row(con, "C2")
    assert c2["latitude"] is None
    assert c2["longitude"] is None
    # in-bounds crash keeps its real coordinates
    c1 = _row(con, "C1")
    assert c1["latitude"] == pytest.approx(39.05)


def test_unparseable_date_becomes_null_not_a_crash(built):
    con, _ = built
    c5 = _row(con, "C5")
    assert c5["crash_date"] is None


def test_pedestrian_and_cyclist_involvement_from_participants(built):
    con, _ = built
    c1 = _row(con, "C1")
    assert c1["pedestrian_involved"] is True   # N1 = PEDESTRIAN
    assert c1["cyclist_involved"] is True      # N2 = Cyclist (Electric)

    c2 = _row(con, "C2")
    assert c2["pedestrian_involved"] is False  # N3 = Scooter, not ped/cyclist
    assert c2["cyclist_involved"] is False


def test_injury_and_fatality_counts_derived_from_participants(built):
    con, _ = built
    c1 = _row(con, "C1")
    # D1=no_apparent_injury (not counted), N1=suspected_minor_injury (counted),
    # N2=null->unknown (not counted) -> injury_count == 1
    assert c1["injury_count"] == 1
    assert c1["fatality_count"] == 0

    c2 = _row(con, "C2")
    # D2=fatal_injury (counted in both fatality and injury), N3=possible_injury (counted)
    assert c2["fatality_count"] == 1
    assert c2["injury_count"] == 2

    c4 = _row(con, "C4")
    assert c4["fatality_count"] == 0  # no participants at all for C4


def test_null_injury_severity_maps_to_unknown_not_dropped(built):
    con, _ = built
    row = con.execute(
        "SELECT injury_severity FROM fact_participants WHERE participant_id = 'N2'"
    ).fetchone()
    assert row[0] == "unknown"


def test_driver_with_no_person_id_is_excluded(built):
    con, _ = built
    count = con.execute(
        "SELECT COUNT(*) FROM fact_participants WHERE crash_id = 'C3'"
    ).fetchone()[0]
    assert count == 0


def test_cyclist_classification_matches_multiple_real_world_labels(built):
    con, _ = built
    row = con.execute(
        "SELECT participant_type FROM fact_participants WHERE participant_id = 'N2'"
    ).fetchone()
    assert row[0] == "cyclist"


def test_orphaned_participant_still_kept_in_fact_participants(built):
    con, _ = built
    row = con.execute(
        "SELECT crash_id FROM fact_participants WHERE participant_id = 'D_orphan'"
    ).fetchone()
    assert row is not None  # kept, just flagged by the quality check


# --- quality report ---

def test_quality_report_catches_every_seeded_issue(built):
    _, report = built
    by_name = {c.name: c for c in report.checks}

    assert by_name["incidents_duplicate_report_number"].violations == 1
    assert by_name["participants_orphaned_from_incidents"].violations == 1
    assert by_name["participants_null_injury_severity_source"].violations == 1
    assert by_name["crash_date_unparseable"].violations == 1
    assert by_name["coordinates_out_of_montgomery_county_bounds"].violations == 1
    assert by_name["unknown_severity_classification"].violations == 1
    assert by_name["unrecognized_agency_name"].violations == 1
    assert by_name["fatal_severity_without_fatality_count"].violations == 1


def test_hard_checks_all_pass_on_valid_structural_data(built):
    _, report = built
    hard_checks = [c for c in report.checks if c.severity == "hard"]
    assert len(hard_checks) >= 3
    assert all(c.passed for c in hard_checks)


def test_report_not_ok_when_any_check_has_violations(built):
    _, report = built
    assert report.ok is False  # soft violations were seeded on purpose
