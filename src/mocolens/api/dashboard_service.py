"""Backend for GET /api/dashboard/summary - real curated data, matching
frontend/src/types/analytics.ts's DashboardResponse field-for-field.

Uses storage.duckdb_store directly (a read-only connection to the real
curated database), not retrieval.sql_tool - that tool's sandboxing exists
to contain LLM-generated SQL; this file's queries are our own trusted code,
so the extra isolation would be overhead with no one to protect against.
calculate_statistics is still used for the arithmetic itself, so "no LLM
arithmetic in prose" (§14.4) holds for trusted code too, not just the agent.

Filters (time range, area, road user, severity) are real, applied in SQL -
not a client-side illusion. All 4 combine with AND; anything that collapses
a breakdown to one category (e.g. severity=Fatal + "crashes by severity")
is an honest, correct reflection of the filter, not special-cased away.

get_dashboard_map() is the one function here that reads something other
than DuckDB: its "what the county is focusing on" panel comes from a fixed
semantic search over the report index, so that panel states what county
documents actually say instead of hardcoded prose. The query is a constant
and the index is static, so the result is cached for the process.

One deliberate exception: the summary endpoint's `hotspots` never applies
the area filter to itself, even though area filters everything else. It's the
"by area" breakdown - the frontend's Area dropdown is populated from
`hotspots.map(h => h.area)`, so if hotspots came back pre-narrowed to the
selected area, every other area would vanish from the dropdown the moment
one was picked. hotspots always returns every area (respecting the other
3 filters); the frontend narrows it to one area client-side for the map
display, same as it always has.

The two hotspot groupings are deliberately different, and not interchangeable:
the summary's `_hotspots` groups by reporting agency because that is what its
Area filter selects on, while the map's `_cell_hotspots` groups by geographic
cell because an agency covers most of the county and its centroid is not a
place where crashes concentrate.
"""
import calendar
import re
from dataclasses import dataclass, replace
from datetime import date
from functools import lru_cache
from pathlib import Path

import duckdb

from ..processing.curate import data_as_of
from ..retrieval.report_tool import search_reports
from ..retrieval.statistics_tool import percent_change
from ..storage import duckdb_store
from . import schemas

DOMAIN = "vision_zero"

_SEVERITY_LABELS = {
    "property_damage": "Property damage",
    "injury": "Injury",
    "fatal": "Fatal",
    "unknown": "Unknown",
}
# Raw Socrata collision codes are all-caps shorthand; these are the public
# wordings for the ones that actually occur. Anything unmapped falls back to
# title case rather than being hidden, so a new upstream code still shows.
_COLLISION_LABELS = {
    "SAME DIR REAR END": "Rear-end (same direction)",
    "FRONT TO REAR": "Rear-end (front to rear)",
    "SINGLE VEHICLE": "Single vehicle",
    "STRAIGHT MOVEMENT ANGLE": "Angle (straight movement)",
    "SAME DIRECTION SIDESWIPE": "Sideswipe (same direction)",
    "OPPOSITE DIRECTION SIDESWIPE": "Sideswipe (opposite direction)",
    "HEAD ON LEFT TURN": "Head-on left turn",
    "SAME DIRECTION LEFT TURN": "Left turn (same direction)",
    "SAME DIRECTION RIGHT TURN": "Right turn (same direction)",
    "ANGLE MEETS LEFT TURN": "Angle into a left turn",
    "ANGLE MEETS RIGHT TURN": "Angle into a right turn",
    "HEAD ON": "Head-on",
    "ANGLE": "Angle",
}

_PARTICIPANT_LABELS = {
    "driver": "Drivers",
    "pedestrian": "Pedestrians",
    "cyclist": "Cyclists",
    "other_non_motorist": "Other",
    "unknown_non_motorist": "Other",
}


@dataclass(frozen=True)
class Filters:
    time_range: str = "Last 12 months"
    area: str = "All areas"
    road_user: str = "All road users"
    severity: str = "All severity levels"


@dataclass(frozen=True)
class Window:
    start: date | None  # None = no lower bound ("All time")
    end: date
    prior_start: date | None
    prior_end: date | None  # None = no prior-period comparison available
    label: str  # human text, e.g. "the last 6 months"
    comparison_label: str | None  # e.g. "the previous 6 months", or None if no comparison applies


def _connect() -> duckdb.DuckDBPyConnection:
    db_path = Path("data") / "curated" / DOMAIN / "analytics.duckdb"
    if not db_path.exists():
        raise FileNotFoundError(
            f"{db_path} missing - run scripts/build_curated_tables.py --domain {DOMAIN} first."
        )
    return duckdb.connect(str(db_path), read_only=True)


def _latest_crash_date(con) -> date:
    """The end of the data, not today: every window on this endpoint is
    measured back from the most recent crash the curated tables hold.
    """
    return con.execute("SELECT MAX(crash_date) FROM fact_crashes").fetchone()[0]


def _subtract_months(d: date, months: int) -> date:
    total = d.month - 1 - months
    year = d.year + total // 12
    month = total % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _resolve_window(latest: date, time_range: str) -> Window:
    if time_range == "Last 6 months":
        start = _subtract_months(latest, 6)
        return Window(start, latest, _subtract_months(start, 6), start, "the last 6 months", "the previous 6 months")
    if time_range == "Year to date":
        start = date(latest.year, 1, 1)
        prior_end = _subtract_months(latest, 12)
        return Window(start, latest, date(prior_end.year, 1, 1), prior_end, "year to date", "the same period last year")
    if time_range == "All time":
        return Window(None, latest, None, None, "all time", None)
    # default: "Last 12 months"
    start = _subtract_months(latest, 12)
    return Window(start, latest, _subtract_months(start, 12), start, "the last 12 months", "the previous 12 months")


def _crash_filter_clauses(filters: Filters, prefix: str = "") -> tuple[list[str], list]:
    """WHERE clauses for area/road_user/severity - NOT the time window,
    which differs between "current" and "prior" periods in the same query
    and is handled separately by _window_clauses. `prefix` qualifies bare
    column names for queries joined against fact_crashes under an alias
    (e.g. "c." in _road_user_breakdown's fact_participants join).
    """
    p = prefix
    clauses: list[str] = []
    params: list = []

    if filters.area and filters.area != "All areas":
        clauses.append(f"{p}agency_name = ?")
        params.append(filters.area)

    if filters.road_user == "Pedestrians":
        clauses.append(f"{p}pedestrian_involved")
    elif filters.road_user == "Cyclists":
        clauses.append(f"{p}cyclist_involved")
    elif filters.road_user == "Drivers":
        clauses.append(f"NOT {p}pedestrian_involved AND NOT {p}cyclist_involved")

    if filters.severity == "Property damage only":
        clauses.append(f"{p}severity = 'property_damage'")
    elif filters.severity == "Injury":
        clauses.append(f"{p}severity = 'injury'")
    elif filters.severity == "Fatal":
        clauses.append(f"{p}severity = 'fatal'")
    elif filters.severity == "Serious injury":
        crash_id_col = f"{p}crash_id" if p else "fact_crashes.crash_id"
        clauses.append(f"""EXISTS (
            SELECT 1 FROM fact_participants sp
            WHERE sp.crash_id = {crash_id_col} AND sp.injury_severity = 'suspected_serious_injury'
        )""")

    return clauses, params


def _window_clauses(window: Window, prefix: str = "", start: date | None = None, end: date | None = None) -> tuple[list[str], list]:
    """Date-bound clauses for one period. Defaults to window.start/end (the
    "current" period); pass start/end explicitly for the "prior" period.
    """
    p = prefix
    bound_start = start if start is not None else window.start
    bound_end = end if end is not None else window.end
    clauses = [f"{p}crash_date <= ?"]
    params: list = [bound_end]
    if bound_start is not None:
        clauses.insert(0, f"{p}crash_date >= ?")
        params.insert(0, bound_start)
    return clauses, params


def _metric_count(con, filters: Filters, extra_clause: str | None, start: date | None, end: date) -> int:
    clauses, params = _crash_filter_clauses(filters)
    if extra_clause:
        clauses.append(extra_clause)
    window_clauses, window_params = _window_clauses(Window(start, end, None, None, "", None))
    clauses += window_clauses
    params += window_params
    where = " AND ".join(clauses) if clauses else "TRUE"
    return con.execute(f"SELECT COUNT(*) FROM fact_crashes WHERE {where}", params).fetchone()[0]


def _crash_metric(con, label: str, extra_clause: str | None, window: Window, filters: Filters) -> schemas.Metric:
    """One KPI card: count over the resolved window vs. the prior period of
    the same length (or no comparison for "All time" - there's no
    meaningful prior period for it).
    """
    current_count = _metric_count(con, filters, extra_clause, window.start, window.end)
    prior_count = None
    if window.prior_start is not None:
        prior_count = _metric_count(con, filters, extra_clause, window.prior_start, window.prior_end)

    change = None
    if prior_count:
        change = round(percent_change(prior_count, current_count), 1)

    description = f"from {window.comparison_label}" if window.comparison_label else "no prior period to compare (all time)"
    return schemas.Metric(
        label=label,
        value=current_count,
        change=change,
        change_direction=None if change is None else ("up" if change > 0 else "down" if change < 0 else "neutral"),
        change_is_positive=None if change is None else change <= 0,
        description=description,
    )


def _metrics(con, window: Window, filters: Filters) -> list[schemas.Metric]:
    return [
        _crash_metric(con, "Total crashes", None, window, filters),
        _crash_metric(con, "Pedestrian crashes", "pedestrian_involved", window, filters),
        _crash_metric(con, "Cyclist crashes", "cyclist_involved", window, filters),
        _crash_metric(
            con, "Serious or fatal crashes",
            """(severity = 'fatal' OR EXISTS (
                SELECT 1 FROM fact_participants p
                WHERE p.crash_id = fact_crashes.crash_id
                  AND p.injury_severity IN ('suspected_serious_injury', 'fatal_injury')
            ))""",
            window, filters,
        ),
    ]


def _crash_trend(con, window: Window, filters: Filters) -> list[schemas.TimeSeriesPoint]:
    clauses, params = _crash_filter_clauses(filters)
    window_clauses, window_params = _window_clauses(window)
    clauses += window_clauses
    params += window_params
    where = " AND ".join(clauses) if clauses else "TRUE"

    # "All time" spans a decade in this dataset - group by year to keep the
    # chart readable; every other window groups by month.
    if window.start is None:
        rows = con.execute(f"""
            SELECT CAST(EXTRACT(year FROM crash_date) AS VARCHAR), date_trunc('year', crash_date), COUNT(*)
            FROM fact_crashes WHERE {where} GROUP BY 1, 2 ORDER BY 2
        """, params).fetchall()
    else:
        rows = con.execute(f"""
            SELECT strftime(date_trunc('month', crash_date), '%b ''%y'), date_trunc('month', crash_date), COUNT(*)
            FROM fact_crashes WHERE {where} GROUP BY 1, 2 ORDER BY 2
        """, params).fetchall()
    return [schemas.TimeSeriesPoint(label=label, value=count) for label, _, count in rows]


def _severity_breakdown(con, window: Window, filters: Filters) -> list[schemas.CategoryValue]:
    clauses, params = _crash_filter_clauses(filters)
    window_clauses, window_params = _window_clauses(window)
    clauses += window_clauses
    params += window_params
    where = " AND ".join(clauses) if clauses else "TRUE"
    rows = con.execute(
        f"SELECT severity, COUNT(*) FROM fact_crashes WHERE {where} GROUP BY severity ORDER BY 2 DESC", params
    ).fetchall()
    return [schemas.CategoryValue(label=_SEVERITY_LABELS.get(sev, sev), value=count) for sev, count in rows]


def _road_user_breakdown(con, window: Window, filters: Filters) -> list[schemas.CategoryValue]:
    clauses, params = _crash_filter_clauses(filters, prefix="c.")
    window_clauses, window_params = _window_clauses(window, prefix="c.")
    clauses += window_clauses
    params += window_params
    where = " AND ".join(clauses) if clauses else "TRUE"
    rows = con.execute(f"""
        SELECT p.participant_type, COUNT(*)
        FROM fact_participants p
        JOIN fact_crashes c ON c.crash_id = p.crash_id
        WHERE {where}
        GROUP BY p.participant_type
    """, params).fetchall()

    total = sum(count for _, count in rows)
    if total == 0:
        return []
    merged: dict[str, int] = {}
    for ptype, count in rows:
        label = _PARTICIPANT_LABELS.get(ptype, ptype)
        merged[label] = merged.get(label, 0) + count
    return [
        schemas.CategoryValue(label=label, value=round(count / total * 100, 1))
        for label, count in sorted(merged.items(), key=lambda kv: -kv[1])
    ]


def _hotspots(con, window: Window, filters: Filters) -> list[schemas.Hotspot]:
    """Grouped by agency_name - the closest real proxy for "area" the data
    has (no municipality/community field exists; see PROJECT_STATUS.txt).
    """
    base_clauses, base_params = _crash_filter_clauses(filters)

    cur_clauses, cur_params = _window_clauses(window)
    cur_where = " AND ".join(base_clauses + cur_clauses + ["agency_name IS NOT NULL"])
    current_rows = con.execute(f"""
        SELECT agency_name, COUNT(*), AVG(latitude), AVG(longitude)
        FROM fact_crashes WHERE {cur_where}
        GROUP BY agency_name
    """, base_params + cur_params).fetchall()

    prior_counts: dict[str, int] = {}
    if window.prior_start is not None:
        prior_clauses, prior_params = _window_clauses(window, start=window.prior_start, end=window.prior_end)
        prior_where = " AND ".join(base_clauses + prior_clauses + ["agency_name IS NOT NULL"])
        prior_rows = con.execute(f"""
            SELECT agency_name, COUNT(*) FROM fact_crashes WHERE {prior_where} GROUP BY agency_name
        """, base_params + prior_params).fetchall()
        prior_counts = dict(prior_rows)

    if not current_rows:
        return []
    max_count = max(r[1] for r in current_rows)

    hotspots = []
    for agency, count, lat, lon in current_rows:
        if lat is None or lon is None:
            continue
        prior = prior_counts.get(agency)
        trend = round(percent_change(prior, count), 1) if prior else 0.0
        hotspots.append(schemas.Hotspot(
            id=agency.lower().replace(" ", "-"),
            area=agency,
            latitude=lat,
            longitude=lon,
            crash_count=count,
            trend=trend,
            intensity=round(count / max_count, 3),
        ))
    hotspots.sort(key=lambda h: -h.crash_count)
    return hotspots


def _insights(metrics: list[schemas.Metric], hotspots: list[schemas.Hotspot], window: Window) -> list[schemas.Insight]:
    """Template sentences filled with real computed numbers - not
    LLM-generated prose (no LLM exists in this project yet for the
    dashboard), matching §14.4's "no nontrivial arithmetic in prose"
    principle: the arithmetic already happened in SQL/calculate_statistics,
    this just states it.
    """
    insights: list[schemas.Insight] = []

    total_metric = metrics[0]  # "Total crashes" - see _metrics()
    if total_metric.change is not None and window.comparison_label:
        change = total_metric.change
        direction = "risen" if change > 0 else "fallen" if change < 0 else "stayed flat"
        insights.append(schemas.Insight(
            id="trend",
            text=f"Total crashes have {direction} {abs(change)}% over {window.label} compared to {window.comparison_label}.",
        ))

    if hotspots:
        top = hotspots[0]
        insights.append(schemas.Insight(
            id="top-area",
            text=f"{top.area} reported the most crashes of any area over {window.label} ({top.crash_count:,}).",
        ))
        fastest = max(hotspots, key=lambda h: h.trend)
        if fastest.trend > 0:
            insights.append(schemas.Insight(
                id="fastest-increase",
                text=f"{fastest.area} had the fastest increase, up {fastest.trend}%.",
            ))

    return insights


def get_dashboard_summary(filters: Filters | None = None) -> schemas.DashboardResponse:
    filters = filters or Filters()
    con = _connect()
    try:
        latest = _latest_crash_date(con)
        window = _resolve_window(latest, filters.time_range)

        metrics = _metrics(con, window, filters)
        hotspots = _hotspots(con, window, replace(filters, area="All areas"))
        return schemas.DashboardResponse(
            metrics=metrics,
            crash_trend=_crash_trend(con, window, filters),
            severity_breakdown=_severity_breakdown(con, window, filters),
            road_user_breakdown=_road_user_breakdown(con, window, filters),
            hotspots=hotspots,
            insights=_insights(metrics, hotspots, window),
            data_as_of=data_as_of(DOMAIN),
        )
    finally:
        con.close()


def get_dashboard_trends(filters: Filters | None = None) -> schemas.TrendsResponse:
    """GET /api/dashboard/trends - the same windowed series the summary
    endpoint returns, without the KPI/hotspot/insight queries alongside them.
    """
    filters = filters or Filters()
    con = _connect()
    try:
        window = _resolve_window(_latest_crash_date(con), filters.time_range)
        return schemas.TrendsResponse(
            crash_trend=_crash_trend(con, window, filters),
            severity_breakdown=_severity_breakdown(con, window, filters),
            road_user_breakdown=_road_user_breakdown(con, window, filters),
            data_as_of=data_as_of(DOMAIN),
        )
    finally:
        con.close()


# The map groups crashes into geographic cells, not into the reporting
# agencies the summary endpoint's Area filter uses. An agency covers most of
# the county, so agency centroids would draw one blob over Montgomery County
# and call it a hotspot. 0.01 degrees is roughly 1.1 km north-south and 0.9 km
# east-west at this latitude - about a neighbourhood, which is the scale a
# resident asking "where are crashes concentrated?" means.
HOTSPOT_GRID_DEGREES = 0.01
HOTSPOT_LIMIT = 10
# Below this a cell is noise, not a hotspot. Narrow filters (one road user and
# one severity, say) can leave every cell under it, in which case the map
# honestly shows nothing rather than promoting a single crash to a hotspot.
HOTSPOT_MIN_CRASHES = 5

_DIRECTION_SUFFIX_RE = re.compile(r"\s*\((?:[NSEW]B|[NSEW]B/[A-Z]|[A-Z]{1,3})\)\s*$")
# Route and compass tokens that str.title() would otherwise write as "Md 97"
# or "Nb". Anything not listed keeps its title case.
_UPPERCASE_ROAD_TOKENS = frozenset({"md", "us", "i", "sr", "nb", "sb", "eb", "wb", "sw", "se", "ne", "nw"})


def _clean_road_label(name: str | None) -> str | None:
    """Public wording for a raw road name from the crash records.

    Upstream values are all-caps and often carry a direction/lane suffix, and
    a few repeat the road name twice ("GEORGIA AVE GEORGIA AVE (SB/L)") where
    the source concatenated two fields. None of that belongs on a public map
    label; the underlying value is unchanged in the data.
    """
    if not name:
        return None
    cleaned = _DIRECTION_SUFFIX_RE.sub("", name.strip())
    words = cleaned.split()
    half = len(words) // 2
    if half and words[:half] == words[half:]:
        words = words[:half]
    titled = [
        word.upper() if word.lower() in _UPPERCASE_ROAD_TOKENS else word.title()
        for word in words
    ]
    return " ".join(titled) or None


def _cell_hotspots(con, window: Window, filters: Filters) -> list[schemas.Hotspot]:
    """Top geographic crash clusters in the window, with their real centroid.

    The coordinates returned are the mean of the crashes in the cell, not the
    cell's corner, so a marker sits where the crashes actually are. Rows with
    no coordinates are excluded - 0.07% of the table, and a crash with no
    location cannot be placed on a map.

    Each cell is labelled with its two most common road names, because a long
    corridor produces several separate hotspots: three cells on Georgia Ave
    are three different places, and "Georgia Ave" three times in a ranked list
    tells a reader nothing about which one is near them.
    """
    clauses, params = _crash_filter_clauses(filters)
    window_clauses, window_params = _window_clauses(window)
    where = " AND ".join(
        clauses + window_clauses + ["latitude IS NOT NULL", "longitude IS NOT NULL"]
    )
    grid = HOTSPOT_GRID_DEGREES

    rows = con.execute(f"""
        WITH located AS (
            SELECT
                CAST(latitude / ? AS BIGINT) AS lat_cell,
                CAST(longitude / ? AS BIGINT) AS lon_cell,
                latitude, longitude, road_name
            FROM fact_crashes WHERE {where}
        ), cells AS (
            SELECT lat_cell, lon_cell, COUNT(*) AS crash_count,
                   AVG(latitude) AS latitude, AVG(longitude) AS longitude
            FROM located GROUP BY 1, 2
            HAVING COUNT(*) >= ? ORDER BY crash_count DESC LIMIT ?
        ), roads AS (
            SELECT lat_cell, lon_cell, road_name,
                   ROW_NUMBER() OVER (
                       PARTITION BY lat_cell, lon_cell ORDER BY COUNT(*) DESC, road_name
                   ) AS road_rank
            FROM located WHERE road_name IS NOT NULL GROUP BY 1, 2, 3
        )
        SELECT c.lat_cell, c.lon_cell, c.crash_count, c.latitude, c.longitude,
               first_road.road_name, second_road.road_name
        FROM cells c
        LEFT JOIN roads first_road
               ON (first_road.lat_cell, first_road.lon_cell, first_road.road_rank)
                = (c.lat_cell, c.lon_cell, 1)
        LEFT JOIN roads second_road
               ON (second_road.lat_cell, second_road.lon_cell, second_road.road_rank)
                = (c.lat_cell, c.lon_cell, 2)
        ORDER BY c.crash_count DESC
    """, [grid, grid] + params + window_params + [HOTSPOT_MIN_CRASHES, HOTSPOT_LIMIT]).fetchall()

    if not rows:
        return []

    prior_counts: dict[tuple[int, int], int] = {}
    if window.prior_start is not None:
        prior_clauses, prior_params = _window_clauses(
            window, start=window.prior_start, end=window.prior_end
        )
        prior_where = " AND ".join(
            clauses + prior_clauses + ["latitude IS NOT NULL", "longitude IS NOT NULL"]
        )
        prior_counts = {
            (lat_cell, lon_cell): count
            for lat_cell, lon_cell, count in con.execute(f"""
                SELECT CAST(latitude / ? AS BIGINT), CAST(longitude / ? AS BIGINT), COUNT(*)
                FROM fact_crashes WHERE {prior_where} GROUP BY 1, 2
            """, [grid, grid] + params + prior_params).fetchall()
        }

    max_count = rows[0][2]
    hotspots = []
    for lat_cell, lon_cell, count, latitude, longitude, first_road, second_road in rows:
        prior = prior_counts.get((lat_cell, lon_cell))
        hotspots.append(schemas.Hotspot(
            id=f"{lat_cell}_{lon_cell}",
            area=_cell_label(first_road, second_road, latitude, longitude),
            latitude=latitude,
            longitude=longitude,
            crash_count=count,
            trend=round(percent_change(prior, count), 1) if prior else 0.0,
            intensity=round(count / max_count, 3),
        ))
    return hotspots


def _cell_label(first_road: str | None, second_road: str | None, latitude: float, longitude: float) -> str:
    """A place name for one cell: its main road, and the next road along.

    "near" rather than "&" on purpose - the two roads are the most common in a
    half-mile cell, which does not mean they intersect. Falls back to
    coordinates when the cell's crashes have no road name at all.
    """
    primary = _clean_road_label(first_road)
    secondary = _clean_road_label(second_road)
    if not primary:
        return f"{latitude:.3f}, {longitude:.3f}"
    if secondary and secondary != primary:
        return f"{primary} near {secondary}"
    return primary


def _ranked_areas(hotspots: list[schemas.Hotspot]) -> list[schemas.RankedArea]:
    """Hotspots come back ordered by crash count, so the rank is their position."""
    return [
        schemas.RankedArea(rank=i + 1, name=h.area, crash_count=h.crash_count, trend=h.trend)
        for i, h in enumerate(hotspots)
    ]


def _common_collision_type(con, window: Window, filters: Filters) -> tuple[str, float] | None:
    """The most frequent collision type in the window, and its share of all
    crashes in that window.

    'OTHER' and NULL are excluded from the ranking: both are catch-all
    buckets rather than a kind of crash, and naming one "the most common
    crash type" would tell the reader nothing. The share is still measured
    against every crash in the window, so the percentage is not inflated by
    dropping them.
    """
    clauses, params = _crash_filter_clauses(filters)
    window_clauses, window_params = _window_clauses(window)
    clauses += window_clauses
    params += window_params
    where = " AND ".join(clauses) if clauses else "TRUE"

    total = con.execute(f"SELECT COUNT(*) FROM fact_crashes WHERE {where}", params).fetchone()[0]
    if not total:
        return None

    row = con.execute(f"""
        SELECT collision_type, COUNT(*) FROM fact_crashes
        WHERE {where} AND collision_type IS NOT NULL AND collision_type <> 'OTHER'
        GROUP BY 1 ORDER BY 2 DESC LIMIT 1
    """, params).fetchone()
    if row is None:
        return None

    collision_type, count = row
    label = _COLLISION_LABELS.get(collision_type, collision_type.title())
    return label, round(count / total * 100, 1)


def _summary_cards(
    con, window: Window, filters: Filters, hotspots: list[schemas.Hotspot]
) -> list[schemas.HotspotSummaryCard]:
    """Three headline facts about the current window, each computed - a card
    with no supporting data is left out rather than filled with a guess.
    """
    cards: list[schemas.HotspotSummaryCard] = []

    if hotspots:
        top = hotspots[0]
        cards.append(schemas.HotspotSummaryCard(
            label="Most affected location",
            # No "share of all county crashes" here: these are the top cells,
            # not a partition of the county, so a percentage taken across them
            # would describe the cells rather than the county.
            primary_text=top.area,
            secondary_text=f"{top.crash_count:,} crashes over {window.label}, within about a half-mile area",
        ))

        fastest = max(hotspots, key=lambda h: h.trend)
        if fastest.trend > 0 and window.comparison_label:
            cards.append(schemas.HotspotSummaryCard(
                label="Fastest increase",
                primary_text=fastest.area,
                secondary_text=f"up {fastest.trend}% vs. {window.comparison_label}",
            ))

    common = _common_collision_type(con, window, filters)
    if common:
        label, share = common
        cards.append(schemas.HotspotSummaryCard(
            label="Most common crash type",
            primary_text=label,
            secondary_text=f"{share}% of all crashes over {window.label}",
        ))

    return cards


# The question the "what the county is focusing on" panel asks of the report
# index. A constant, not model-chosen, so the panel is reproducible.
COUNTY_FOCUS_QUERY = (
    "Montgomery County Vision Zero priority actions and focus areas for reducing "
    "crashes on high injury roads"
)
COUNTY_FOCUS_LIMIT = 3
# Below this cosine similarity a passage is not really about the question, and
# showing it would put unrelated report text under a confident heading.
COUNTY_FOCUS_MIN_SIMILARITY = 0.45
_FOCUS_EXCERPT_CHARS = 260


# Bullet glyphs these county PDFs use, as they survive text extraction: a
# guillemet, a bullet, a middle dot, dashes, and the replacement character a
# symbol-font bullet decays into.
_BULLET_CHARS = " \t-\u00b7\u00bb\u2013\u2014\u2022\u2023\u25aa\u25cf\ufffd"


def _clean_quoted_line(line: str) -> str:
    """One line of report text, safe to quote on a public page.

    Strips the bullet glyph a line starts or ends with and normalizes runs of
    whitespace. Done here, where text is quoted, rather than edited into the
    stored chunks - the chunk keeps exactly what was extracted, so what the
    agent searches is unchanged.
    """
    return " ".join(line.split()).strip(_BULLET_CHARS)


def _focus_item(hit: dict) -> schemas.CountyFocusItem:
    """Split one retrieved chunk into a heading plus a short excerpt.

    Chunks are contextualized with their section headings during chunking, so
    the first line is a real heading from the document, not something written
    here.
    """
    lines = [
        cleaned for cleaned in (_clean_quoted_line(line) for line in hit["text"].splitlines())
        if cleaned
    ]
    title = lines[0] if lines else (hit.get("section") or "County report passage")
    body = " ".join(lines[1:]) or title
    if len(body) > _FOCUS_EXCERPT_CHARS:
        body = body[:_FOCUS_EXCERPT_CHARS].rsplit(" ", 1)[0] + "..."
    return schemas.CountyFocusItem(
        title=title,
        excerpt=body,
        document_title=hit.get("document_title"),
        page=hit.get("page"),
        url=hit.get("source_url"),
    )


@lru_cache(maxsize=1)
def _county_focus() -> tuple[schemas.CountyFocusItem, ...]:
    """Report passages on the county's stated priorities.

    Cached for the life of the process: the query is a constant and the
    report index is a static build artifact, so this can only produce one
    answer - and caching it means the ONNX query encoder is loaded at most
    once for everyone browsing the map, instead of per request.

    ponytail: an in-process cache with no invalidation, which is correct only
    because the index ships baked into the image. If the index ever becomes
    reloadable at runtime, this needs to be cleared when it reloads.
    """
    try:
        hits = search_reports(COUNTY_FOCUS_QUERY, top_k=COUNTY_FOCUS_LIMIT, domain=DOMAIN)
    except FileNotFoundError:
        # No report index in this deployment - the panel is simply absent,
        # which is honest; the rest of the map does not depend on it.
        return ()
    return tuple(
        _focus_item(hit) for hit in hits
        if hit["similarity_score"] >= COUNTY_FOCUS_MIN_SIMILARITY
    )


def get_dashboard_map(filters: Filters | None = None) -> schemas.MapResponse:
    """GET /api/dashboard/map - crash geography plus the ranked areas,
    headline facts, and county-report context the Hotspots screen shows.
    """
    filters = filters or Filters()
    con = _connect()
    try:
        window = _resolve_window(_latest_crash_date(con), filters.time_range)
        hotspots = _cell_hotspots(con, window, filters)
        return schemas.MapResponse(
            hotspots=hotspots,
            ranked_areas=_ranked_areas(hotspots),
            summary_cards=_summary_cards(con, window, filters, hotspots),
            county_focus=list(_county_focus()),
            data_as_of=data_as_of(DOMAIN),
        )
    finally:
        con.close()
