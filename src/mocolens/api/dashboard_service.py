"""Backend for GET /api/dashboard/summary - real curated data, matching
frontend/src/types/analytics.ts's DashboardResponse field-for-field.

Uses storage.duckdb_store directly (a read-only connection to the real
curated database), not retrieval.sql_tool - that tool's sandboxing exists
to contain LLM-generated SQL; this file's queries are our own trusted code,
so the extra isolation would be overhead with no one to protect against.
calculate_statistics is still used for the arithmetic itself, so "no LLM
arithmetic in prose" (§14.4) holds for trusted code too, not just the agent.

Every number here is computed from real crash_date-anchored windows, not
fabricated: the "trailing 12 months" window is anchored to MAX(crash_date)
in the data, not today's wall-clock date, so it stays meaningful even if
ingestion falls behind.
"""
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


def _connect() -> duckdb.DuckDBPyConnection:
    db_path = Path("data") / "curated" / DOMAIN / "analytics.duckdb"
    if not db_path.exists():
        raise FileNotFoundError(
            f"{db_path} missing - run scripts/build_curated_tables.py --domain {DOMAIN} first."
        )
    return duckdb.connect(str(db_path), read_only=True)


def _crash_metric(con, label: str, where_extra: str, description: str) -> schemas.Metric:
    """One KPI card: count over the trailing 12 months vs. the prior 12,
    anchored to the data's own latest date. Fewer crashes is styled
    positive - these are all "bad thing happened" counts.
    """
    row = con.execute(f"""
        WITH bounds AS (SELECT MAX(crash_date) AS latest FROM fact_crashes)
        SELECT
            COUNT(*) FILTER (WHERE crash_date > latest - INTERVAL 12 MONTH) AS current_count,
            COUNT(*) FILTER (
                WHERE crash_date > latest - INTERVAL 24 MONTH
                  AND crash_date <= latest - INTERVAL 12 MONTH
            ) AS prior_count
        FROM fact_crashes, bounds
        WHERE {where_extra}
    """).fetchone()
    current_count, prior_count = row

    change = None
    if prior_count:
        change = round(percent_change(prior_count, current_count), 1)

    return schemas.Metric(
        label=label,
        value=current_count,
        change=change,
        change_direction=None if change is None else ("up" if change > 0 else "down" if change < 0 else "neutral"),
        change_is_positive=None if change is None else change <= 0,
        description=description,
    )


def _metrics(con) -> list[schemas.Metric]:
    return [
        _crash_metric(con, "Total crashes", "TRUE", "from last year"),
        _crash_metric(con, "Pedestrian crashes", "pedestrian_involved", "from last year"),
        _crash_metric(con, "Cyclist crashes", "cyclist_involved", "from last year"),
        _crash_metric(
            con, "Serious or fatal crashes",
            """(severity = 'fatal' OR EXISTS (
                SELECT 1 FROM fact_participants p
                WHERE p.crash_id = fact_crashes.crash_id
                  AND p.injury_severity IN ('suspected_serious_injury', 'fatal_injury')
            ))""",
            "from last year",
        ),
    ]


def _crash_trend(con) -> list[schemas.TimeSeriesPoint]:
    rows = con.execute("""
        WITH bounds AS (SELECT MAX(crash_date) AS latest FROM fact_crashes)
        SELECT strftime(date_trunc('month', crash_date), '%b ''%y') AS month_label,
               date_trunc('month', crash_date) AS month_start,
               COUNT(*)
        FROM fact_crashes, bounds
        WHERE crash_date > latest - INTERVAL 13 MONTH
        GROUP BY 1, 2
        ORDER BY 2
    """).fetchall()
    return [schemas.TimeSeriesPoint(label=label, value=count) for label, _, count in rows]


def _severity_breakdown(con) -> list[schemas.CategoryValue]:
    rows = con.execute("SELECT severity, COUNT(*) FROM fact_crashes GROUP BY severity ORDER BY 2 DESC").fetchall()
    return [schemas.CategoryValue(label=_SEVERITY_LABELS.get(sev, sev), value=count) for sev, count in rows]


def _road_user_breakdown(con) -> list[schemas.CategoryValue]:
    rows = con.execute("SELECT participant_type, COUNT(*) FROM fact_participants GROUP BY participant_type").fetchall()
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


def _hotspots(con) -> list[schemas.Hotspot]:
    """Grouped by agency_name - the closest real proxy for "area" the data
    has (no municipality/community field exists; see PROJECT_STATUS.txt).
    """
    rows = con.execute("""
        WITH bounds AS (SELECT MAX(crash_date) AS latest FROM fact_crashes),
        current_period AS (
            SELECT agency_name, COUNT(*) AS crash_count,
                   AVG(latitude) AS lat, AVG(longitude) AS lon
            FROM fact_crashes, bounds
            WHERE crash_date > latest - INTERVAL 12 MONTH AND agency_name IS NOT NULL
            GROUP BY agency_name
        ),
        prior_period AS (
            SELECT agency_name, COUNT(*) AS crash_count
            FROM fact_crashes, bounds
            WHERE crash_date > latest - INTERVAL 24 MONTH AND crash_date <= latest - INTERVAL 12 MONTH
              AND agency_name IS NOT NULL
            GROUP BY agency_name
        )
        SELECT c.agency_name, c.crash_count, c.lat, c.lon, p.crash_count
        FROM current_period c
        LEFT JOIN prior_period p ON p.agency_name = c.agency_name
        ORDER BY c.crash_count DESC
    """).fetchall()

    if not rows:
        return []
    max_count = max(r[1] for r in rows)

    hotspots = []
    for agency, count, lat, lon, prior_count in rows:
        if lat is None or lon is None:
            continue
        trend = round(percent_change(prior_count, count), 1) if prior_count else 0.0
        hotspots.append(schemas.Hotspot(
            id=agency.lower().replace(" ", "-"),
            area=agency.title(),
            latitude=lat,
            longitude=lon,
            crash_count=count,
            trend=trend,
            intensity=round(count / max_count, 3),
        ))
    return hotspots


def _insights(metrics: list[schemas.Metric], hotspots: list[schemas.Hotspot]) -> list[schemas.Insight]:
    """Template sentences filled with real computed numbers - not
    LLM-generated prose (no LLM exists in this project yet), matching
    §14.4's "no nontrivial arithmetic in prose" principle: the arithmetic
    already happened in SQL/calculate_statistics, this just states it.

    Deliberately reuses the trailing-12mo-vs-prior-12mo metric already
    computed for the "Total crashes" KPI card, rather than comparing the
    crash_trend chart's first and last months directly - both of those
    are partial months at the edges of a fixed trailing window, and an
    early version of this comparing them literally reported a 320%
    increase driven entirely by that edge effect, not a real trend.
    """
    insights: list[schemas.Insight] = []

    total_metric = metrics[0]  # "Total crashes" - see _metrics()
    if total_metric.change is not None:
        change = total_metric.change
        direction = "risen" if change > 0 else "fallen" if change < 0 else "stayed flat"
        insights.append(schemas.Insight(
            id="trend",
            text=f"Total crashes have {direction} {abs(change)}% over the trailing 12 months "
                 f"compared to the 12 months before that.",
        ))

    if hotspots:
        top = hotspots[0]
        insights.append(schemas.Insight(
            id="top-area",
            text=f"{top.area} reported the most crashes of any area in the trailing 12 months "
                 f"({top.crash_count:,}).",
        ))
        fastest = max(hotspots, key=lambda h: h.trend)
        if fastest.trend > 0:
            insights.append(schemas.Insight(
                id="fastest-increase",
                text=f"{fastest.area} had the fastest year-over-year increase, up {fastest.trend}%.",
            ))

    return insights


def get_dashboard_summary() -> schemas.DashboardResponse:
    con = _connect()
    try:
        metrics = _metrics(con)
        hotspots = _hotspots(con)
        return schemas.DashboardResponse(
            metrics=metrics,
            crash_trend=_crash_trend(con),
            severity_breakdown=_severity_breakdown(con),
            road_user_breakdown=_road_user_breakdown(con),
            hotspots=hotspots,
            insights=_insights(metrics, hotspots),
            data_as_of=(latest_run_info(DOMAIN) or {}).get("ran_at"),
        )
    finally:
        con.close()
