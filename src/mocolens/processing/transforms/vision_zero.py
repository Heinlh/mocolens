"""Normalizes raw Vision Zero Socrata JSON into the curated fact_crashes /
fact_participants tables (architecture doc §10, §11, §26).

All normalization runs as SQL against DuckDB (already the project's chosen
analytics engine) rather than pandas/polars - it's read_json_auto for the
extract, a few CREATE MACRO helpers for the messy enum values, and CREATE
TABLE AS SELECT for the transform. No new dependency, and every step is a
query you can run by hand to debug it.

Real-data quirks this deliberately handles (found by inspecting the actual
downloaded Socrata data, not assumed):
  - injury_severity / acrs_report_type / collision_type etc. mix
    ALL-CAPS and Title Case for the same value ("NO APPARENT INJURY" vs
    "No Apparent Injury") - normalize_* macros canonicalize both.
  - agency_name has the same problem in a nastier shape: each of the 5
    real reporting agencies appears as BOTH an all-caps abbreviation
    ("MONTGOMERY") AND a separately-truncated title-case name
    ("Montgomery County Police") - e.g. "Rockville Police Departme" is
    cut off mid-word. A naive GROUP BY agency_name silently splits every
    real agency into two "different" ones. normalize_agency() maps both
    forms of each agency to one canonical name.
  - crash_incidents had one exact-duplicate report_number in the wild -
    deduped via ROW_NUMBER, counted as a soft quality violation.
  - ~1.6% of driver rows have a null injury_severity - mapped to
    'unknown', not dropped.
  - latitude/longitude are always present but not always sane (seen
    points outside the county entirely) - out-of-bounds coordinates are
    nulled for mapping purposes and counted, the crash row is kept.
  - the real Socrata schema has no participant age or municipality field
    at all, despite the architecture doc's suggested model listing them.
    Age is not fabricated. Place is derived, not invented: each crash's
    own coordinates are tested against Census place boundaries
    (_tag_communities), which is the only community signal in the table.
"""
from pathlib import Path

import duckdb

from ..quality import QualityReport, run_check

# Montgomery County, MD bounding box with a small buffer for legitimate
# edge-of-county roads. Anything outside this is almost certainly a bad
# geocode, not a real Montgomery County crash location.
LAT_MIN, LAT_MAX = 38.85, 39.40
LON_MIN, LON_MAX = -77.65, -76.80

# Census place boundaries as ring vertices, written by
# scripts/build_community_boundaries.py and committed.
BOUNDARIES_PATH = Path("data/reference/community_boundaries.parquet")
# Each city's own police force works almost entirely inside that city, which
# makes agency_name an independent check on the boundaries: 90-94% of each
# force's crashes fall inside its city's polygon. Well below that means the
# boundary file is wrong, not that the police moved.
CITY_POLICE = {
    "Rockville Police": "Rockville",
    "Gaithersburg Police": "Gaithersburg",
    "Takoma Park Police": "Takoma Park",
}
MIN_CITY_POLICE_AGREEMENT = 0.85

_MACROS = """
CREATE OR REPLACE MACRO clean_upper(v) AS NULLIF(UPPER(TRIM(COALESCE(v, ''))), '');

CREATE OR REPLACE MACRO normalize_severity(v) AS
    CASE UPPER(TRIM(COALESCE(v, '')))
        WHEN 'FATAL CRASH' THEN 'fatal'
        WHEN 'INJURY CRASH' THEN 'injury'
        WHEN 'PROPERTY DAMAGE CRASH' THEN 'property_damage'
        ELSE 'unknown'
    END;

CREATE OR REPLACE MACRO normalize_injury(v) AS
    CASE UPPER(TRIM(COALESCE(v, '')))
        WHEN 'NO APPARENT INJURY' THEN 'no_apparent_injury'
        WHEN 'POSSIBLE INJURY' THEN 'possible_injury'
        WHEN 'SUSPECTED MINOR INJURY' THEN 'suspected_minor_injury'
        WHEN 'SUSPECTED SERIOUS INJURY' THEN 'suspected_serious_injury'
        WHEN 'FATAL INJURY' THEN 'fatal_injury'
        ELSE 'unknown'
    END;

CREATE OR REPLACE MACRO normalize_agency(v) AS
    CASE UPPER(TRIM(COALESCE(v, '')))
        WHEN 'MONTGOMERY' THEN 'Montgomery County Police'
        WHEN 'MONTGOMERY COUNTY POLICE' THEN 'Montgomery County Police'
        WHEN 'ROCKVILLE' THEN 'Rockville Police'
        WHEN 'ROCKVILLE POLICE DEPARTME' THEN 'Rockville Police'
        WHEN 'GAITHERSBURG' THEN 'Gaithersburg Police'
        WHEN 'GAITHERSBURG POLICE DEPAR' THEN 'Gaithersburg Police'
        WHEN 'TAKOMA' THEN 'Takoma Park Police'
        WHEN 'TAKOMA PARK POLICE DEPART' THEN 'Takoma Park Police'
        WHEN 'MCPARK' THEN 'Maryland-National Capital Park Police'
        WHEN 'MARYLAND-NATIONAL CAPITAL' THEN 'Maryland-National Capital Park Police'
        WHEN '' THEN NULL
        ELSE v
    END;

CREATE OR REPLACE MACRO classify_non_motorist(pedestrian_type) AS
    CASE
        WHEN pedestrian_type IS NULL OR TRIM(pedestrian_type) = '' THEN 'unknown_non_motorist'
        WHEN LOWER(pedestrian_type) LIKE '%cyclist%'
          OR LOWER(pedestrian_type) LIKE '%bicyc%'
          OR LOWER(pedestrian_type) LIKE '%pedalcycl%' THEN 'cyclist'
        WHEN LOWER(pedestrian_type) LIKE '%pedestrian%' THEN 'pedestrian'
        ELSE 'other_non_motorist'
    END;
"""


def _load_raw_json(con: duckdb.DuckDBPyConnection, snapshot_dir: Path) -> None:
    """Register the raw Socrata JSON snapshots as DuckDB views. sample_size=-1
    forces a full-file type scan instead of DuckDB's default sample, so a rare
    value late in a 200k-row file can't silently mis-infer a column's type.
    """
    files = {
        "raw_incidents": "crash_incidents.json",
        "raw_drivers": "crash_drivers.json",
        "raw_non_motorists": "crash_non_motorists.json",
    }
    for view_name, filename in files.items():
        path = snapshot_dir / filename
        if not path.exists():
            raise FileNotFoundError(
                f"Missing {filename} in {snapshot_dir} - run scripts/ingest.py first."
            )
        # DuckDB can't bind a prepared parameter inside CREATE VIEW, so the
        # path is escaped and inlined instead - it's a filesystem path this
        # process constructed itself (snapshot_dir / a fixed filename), never
        # raw user input.
        escaped_path = str(path).replace("'", "''")
        con.execute(
            f"CREATE OR REPLACE VIEW {view_name} AS "
            f"SELECT * FROM read_json_auto('{escaped_path}', sample_size=-1)"
        )
        # An empty JSON array (`[]`) gives DuckDB nothing to infer a schema
        # from - it comes back as one untyped "json" column instead of the
        # real fields, and every downstream query referencing a named
        # column (report_number, person_id, ...) would fail with a cryptic
        # BinderException. Catch it here with a message that actually says
        # what's wrong.
        row_count = con.execute(f"SELECT COUNT(*) FROM {view_name}").fetchone()[0]
        if row_count == 0:
            raise ValueError(
                f"{filename} in {snapshot_dir} has zero records - refusing to "
                f"build curated tables from an empty extract."
            )


def _build_fact_participants(con: duckdb.DuckDBPyConnection, report: QualityReport) -> None:
    con.execute("""
        CREATE OR REPLACE TABLE fact_participants AS
        SELECT
            person_id AS participant_id,
            report_number AS crash_id,
            'driver' AS participant_type,
            normalize_injury(injury_severity) AS injury_severity,
            clean_upper(driver_at_fault) = 'YES' AS at_fault
        FROM raw_drivers
        WHERE person_id IS NOT NULL

        UNION ALL

        SELECT
            person_id AS participant_id,
            report_number AS crash_id,
            classify_non_motorist(pedestrian_type) AS participant_type,
            normalize_injury(injury_severity) AS injury_severity,
            clean_upper(at_fault) = 'YES' AS at_fault
        FROM raw_non_motorists
        WHERE person_id IS NOT NULL
    """)

    run_check(
        con, report,
        name="participants_orphaned_from_incidents",
        sql="""
            SELECT COUNT(*) FROM fact_participants p
            WHERE NOT EXISTS (SELECT 1 FROM raw_incidents i WHERE i.report_number = p.crash_id)
        """,
        severity="soft",
        max_allowed=0,
        detail="participant rows whose crash_id has no matching row in crash_incidents",
    )
    run_check(
        con, report,
        name="participants_null_injury_severity_source",
        sql="""
            SELECT COUNT(*) FROM (
                SELECT injury_severity FROM raw_drivers
                UNION ALL
                SELECT injury_severity FROM raw_non_motorists
            ) WHERE injury_severity IS NULL OR TRIM(injury_severity) = ''
        """,
        severity="soft",
        max_allowed=0,
        detail="source rows with no injury_severity at all - mapped to 'unknown', not dropped",
    )


def _build_fact_crashes(con: duckdb.DuckDBPyConnection, report: QualityReport) -> None:
    run_check(
        con, report,
        name="incidents_duplicate_report_number",
        sql="""
            SELECT COUNT(*) - COUNT(DISTINCT report_number) FROM raw_incidents
        """,
        severity="soft",
        max_allowed=0,
        detail="exact duplicate crash rows in the raw incidents feed, deduped (first kept)",
    )

    # Materialized as a real table, not a CTE scoped to one statement - the
    # quality checks below need to query it after fact_crashes is built.
    con.execute("""
        CREATE OR REPLACE TABLE _stg_crashes_base AS
        WITH deduped AS (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY report_number ORDER BY crash_date_time
            ) AS rn
            FROM raw_incidents
        )
        SELECT
            report_number AS crash_id,
            TRY_CAST(crash_date_time AS TIMESTAMP) AS crash_datetime,
            TRY_CAST(latitude AS DOUBLE) AS raw_latitude,
            TRY_CAST(longitude AS DOUBLE) AS raw_longitude,
            cross_street_name AS road_name,
            normalize_agency(agency_name) AS agency_name,
            route_type,
            clean_upper(hit_run) = 'YES' AS hit_run,
            normalize_severity(acrs_report_type) AS severity,
            clean_upper(collision_type) AS collision_type,
            clean_upper(weather) AS weather,
            clean_upper(light) AS light_condition,
            clean_upper(surface_condition) AS surface_condition
        FROM deduped WHERE rn = 1
    """)

    con.execute(f"""
        CREATE OR REPLACE TABLE fact_crashes AS
        WITH participant_stats AS (
            SELECT
                crash_id,
                COUNT(*) FILTER (WHERE participant_type = 'pedestrian') > 0 AS pedestrian_involved,
                COUNT(*) FILTER (WHERE participant_type = 'cyclist') > 0 AS cyclist_involved,
                COUNT(*) FILTER (WHERE injury_severity = 'fatal_injury') AS fatality_count,
                COUNT(*) FILTER (WHERE injury_severity IN (
                    'possible_injury', 'suspected_minor_injury',
                    'suspected_serious_injury', 'fatal_injury'
                )) AS injury_count
            FROM fact_participants
            GROUP BY crash_id
        )
        SELECT
            b.crash_id,
            CAST(b.crash_datetime AS DATE) AS crash_date,
            CAST(b.crash_datetime AS TIME) AS crash_time,
            CASE WHEN b.raw_latitude BETWEEN {LAT_MIN} AND {LAT_MAX}
                  AND b.raw_longitude BETWEEN {LON_MIN} AND {LON_MAX}
                 THEN b.raw_latitude END AS latitude,
            CASE WHEN b.raw_latitude BETWEEN {LAT_MIN} AND {LAT_MAX}
                  AND b.raw_longitude BETWEEN {LON_MIN} AND {LON_MAX}
                 THEN b.raw_longitude END AS longitude,
            b.road_name,
            b.agency_name,
            b.route_type,
            b.hit_run,
            b.severity,
            b.collision_type,
            b.weather,
            b.light_condition,
            b.surface_condition,
            COALESCE(p.pedestrian_involved, FALSE) AS pedestrian_involved,
            COALESCE(p.cyclist_involved, FALSE) AS cyclist_involved,
            COALESCE(p.fatality_count, 0) AS fatality_count,
            COALESCE(p.injury_count, 0) AS injury_count
        FROM _stg_crashes_base b
        LEFT JOIN participant_stats p ON p.crash_id = b.crash_id
    """)

    # Hard checks - these mean something structural is wrong (schema drift,
    # a join key that stopped matching, an empty extract), not routine
    # source-data messiness. Fail loudly rather than build a broken table.
    run_check(
        con, report,
        name="fact_crashes_not_empty",
        sql="SELECT CASE WHEN COUNT(*) = 0 THEN 1 ELSE 0 END FROM fact_crashes",
        severity="hard",
        max_allowed=0,
        detail="fact_crashes has zero rows",
    )
    run_check(
        con, report,
        name="fact_crashes_crash_id_not_null",
        sql="SELECT COUNT(*) FROM fact_crashes WHERE crash_id IS NULL",
        severity="hard",
        max_allowed=0,
        detail="crash_id must never be null - it's the table's primary key",
    )
    run_check(
        con, report,
        name="fact_crashes_no_duplicate_crash_id",
        sql="""
            SELECT COUNT(*) FROM (
                SELECT crash_id, COUNT(*) c FROM fact_crashes GROUP BY crash_id HAVING c > 1
            )
        """,
        severity="hard",
        max_allowed=0,
        detail="dedup logic failed - crash_id should be unique after ROW_NUMBER filtering",
    )

    # Soft checks - real messiness worth surfacing but not worth blocking on.
    run_check(
        con, report,
        name="crash_date_unparseable",
        sql="SELECT COUNT(*) FROM fact_crashes WHERE crash_date IS NULL",
        severity="soft",
        max_allowed=0,
        detail="crash_date_time values TRY_CAST couldn't parse",
    )
    run_check(
        con, report,
        name="coordinates_out_of_montgomery_county_bounds",
        sql="""
            SELECT COUNT(*) FROM fact_crashes c
            JOIN _stg_crashes_base b ON b.crash_id = c.crash_id
            WHERE b.raw_latitude IS NOT NULL AND c.latitude IS NULL
        """,
        severity="soft",
        max_allowed=0,
        detail=f"lat/lon outside ({LAT_MIN},{LON_MIN})-({LAT_MAX},{LON_MAX}) - nulled, row kept",
    )
    run_check(
        con, report,
        name="unknown_severity_classification",
        sql="SELECT COUNT(*) FROM fact_crashes WHERE severity = 'unknown'",
        severity="soft",
        max_allowed=0,
        detail="acrs_report_type values normalize_severity() didn't recognize",
    )
    run_check(
        con, report,
        name="fatal_severity_without_fatality_count",
        sql="""
            SELECT COUNT(*) FROM fact_crashes
            WHERE severity = 'fatal' AND fatality_count = 0
        """,
        severity="soft",
        max_allowed=0,
        detail="crashes police classified as fatal but with no matching fatal participant row - "
               "a cross-check between the two independent severity signals",
    )
    run_check(
        con, report,
        name="unrecognized_agency_name",
        sql="""
            SELECT COUNT(*) FROM fact_crashes
            WHERE agency_name IS NOT NULL AND agency_name NOT IN (
                'Montgomery County Police', 'Rockville Police', 'Gaithersburg Police',
                'Takoma Park Police', 'Maryland-National Capital Park Police'
            )
        """,
        severity="soft",
        max_allowed=0,
        detail="agency_name values normalize_agency() didn't recognize - passed through as-is, "
               "which likely means a new reporting agency showed up and needs a mapping added",
    )


def _tag_communities(con: duckdb.DuckDBPyConnection, report: QualityReport) -> None:
    """Add fact_crashes.community: the Census place each crash's coordinates
    fall inside, or NULL outside every named place.

    Point-in-polygon by even-odd ray casting, in plain SQL: a point is inside
    a place if a ray drawn east from it crosses that place's boundary an odd
    number of times. Rings are not told apart - a hole is just more boundary,
    and the parity comes out right - so multi-part places and places with
    holes need no special handling. Checked against DuckDB's spatial
    ST_Contains over every crash in the table: 124,765 of 124,769 identical,
    and the other four sit exactly on a boundary line, which ST_Contains
    excludes by definition and this assigns to the place.

    ponytail: the range join below compares each crash with every boundary
    edge spanning its latitude (a few seconds at this size). If the table
    grows by an order of magnitude, prefilter on each place's bounding box.
    """
    if not BOUNDARIES_PATH.exists():
        raise FileNotFoundError(
            f"{BOUNDARIES_PATH} missing - run scripts/build_community_boundaries.py first."
        )
    boundaries = str(BOUNDARIES_PATH).replace("'", "''")
    # One row per boundary edge. Horizontal edges are dropped: a horizontal
    # ray cannot cross one, and they would divide by zero below. The
    # half-open latitude range makes a ray through a shared vertex count
    # exactly one of the two edges that meet there.
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE _community_edges AS
        SELECT community, x1, y1, x2, y2, LEAST(y1, y2) AS y_low, GREATEST(y1, y2) AS y_high
        FROM (
            SELECT community, lon AS x1, lat AS y1,
                   LEAD(lon) OVER ring_order AS x2, LEAD(lat) OVER ring_order AS y2
            FROM read_parquet('{boundaries}')
            WINDOW ring_order AS (PARTITION BY ring ORDER BY seq)
        )
        WHERE x2 IS NOT NULL AND y1 <> y2
    """)
    con.execute("""
        CREATE OR REPLACE TEMP TABLE _crash_community AS
        SELECT crash_id, MIN(community) AS community, COUNT(*) AS matches
        FROM (
            SELECT c.crash_id, e.community
            FROM fact_crashes c
            JOIN _community_edges e
              ON c.latitude >= e.y_low AND c.latitude < e.y_high
            WHERE c.longitude < e.x1 + (c.latitude - e.y1) * (e.x2 - e.x1) / (e.y2 - e.y1)
            GROUP BY c.crash_id, e.community
            HAVING COUNT(*) % 2 = 1
        )
        GROUP BY crash_id
    """)
    con.execute("""
        CREATE OR REPLACE TABLE fact_crashes AS
        SELECT c.*, t.community
        FROM fact_crashes c LEFT JOIN _crash_community t USING (crash_id)
    """)

    run_check(
        con, report,
        name="community_tagging_matched_nothing",
        sql="""
            SELECT CASE WHEN COUNT(*) FILTER (WHERE latitude IS NOT NULL) > 0
                         AND COUNT(community) = 0 THEN 1 ELSE 0 END
            FROM fact_crashes
        """,
        severity="hard",
        detail="located crashes exist but none fell inside any community boundary - "
               "the boundary file is empty, or its coordinates are not longitude/latitude",
    )
    run_check(
        con, report,
        name="crash_in_more_than_one_community",
        sql="SELECT COUNT(*) FROM _crash_community WHERE matches > 1",
        severity="soft",
        detail="place boundaries should not overlap; the alphabetically first community was kept",
    )
    run_check(
        con, report,
        name="located_crash_outside_every_community",
        sql="SELECT COUNT(*) FROM fact_crashes WHERE latitude IS NOT NULL AND community IS NULL",
        severity="soft",
        detail="coordinates outside every Census place (rural areas, parkland) - community left NULL",
    )
    city_cases = " ".join(f"WHEN '{agency}' THEN '{city}'" for agency, city in CITY_POLICE.items())
    run_check(
        con, report,
        name="city_police_crashes_outside_their_city",
        sql=f"""
            SELECT COUNT(*) FROM (
                SELECT agency_name
                FROM fact_crashes
                WHERE agency_name IN ({", ".join(f"'{a}'" for a in CITY_POLICE)}) AND latitude IS NOT NULL
                GROUP BY agency_name
                HAVING AVG((community IS NOT DISTINCT FROM CASE agency_name {city_cases} END)::INT)
                       < {MIN_CITY_POLICE_AGREEMENT}
            )
        """,
        severity="soft",
        detail=f"city police forces with under {MIN_CITY_POLICE_AGREEMENT:.0%} of their crashes inside "
               "their own city's boundary - an independent check that the boundaries are right",
    )


def build(con: duckdb.DuckDBPyConnection, snapshot_dir: Path) -> QualityReport:
    """Load one raw Vision Zero snapshot and build fact_crashes + fact_participants.

    Order matters: fact_participants is built first so fact_crashes can join
    against its per-crash aggregates (pedestrian_involved, fatality_count, ...),
    and communities are tagged last, from the bounds-checked coordinates.
    """
    report = QualityReport()
    con.execute(_MACROS)
    _load_raw_json(con, snapshot_dir)
    _build_fact_participants(con, report)
    _build_fact_crashes(con, report)
    _tag_communities(con, report)
    return report
