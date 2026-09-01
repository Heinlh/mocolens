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

One deliberate exception: `hotspots` never applies the area filter to
itself, even though area filters everything else. It's the "by area"
breakdown - the frontend's Area dropdown is populated from
`hotspots.map(h => h.area)`, so if hotspots came back pre-narrowed to the
selected area, every other area would vanish from the dropdown the moment
one was picked. hotspots always returns every area (respecting the other
3 filters); the frontend narrows it to one area client-side for the map
display, same as it always has.
"""
import calendar
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

import duckdb

from ..processing.curate import latest_run_info
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
        latest = con.execute("SELECT MAX(crash_date) FROM fact_crashes").fetchone()[0]
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
            data_as_of=(latest_run_info(DOMAIN) or {}).get("ran_at"),
        )
    finally:
        con.close()
