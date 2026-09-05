"""LangChain @tool wrappers around retrieval/*.py, for LLM tool-calling.

statistics_tool.py's calculate_statistics(operation, **kwargs) is one
Python dispatch function, but LangChain tool-calling wants narrow, typed,
single-purpose tools for reliable schema generation (§33.7: "Keep agent
tools narrow and explicit") - so each statistics operation gets its own
tool here, all backed by the same underlying pure functions.

Every wrapper catches the underlying tool's exceptions and returns
{"error": "..."} instead of letting them propagate - a malformed
LLM-generated call (bad domain, wrong kwarg) should come back as
something the agent can read and adapt to, not crash the whole graph run.
"""
from langchain_core.tools import tool

from ..retrieval import metadata_tool, report_tool, sql_tool, statistics_tool, visualization_tool


def _safe(fn, **kwargs) -> dict:
    try:
        return fn(**kwargs)
    except (ValueError, FileNotFoundError) as exc:
        return {"error": str(exc)}


@tool
def query_analytics(question: str, sql: str, reason: str) -> dict:
    """Run one read-only SQL SELECT against Montgomery County's curated crash data.

    Tables:
      fact_crashes(crash_id, crash_date, crash_time, latitude, longitude,
        road_name, agency_name, route_type, hit_run, severity
        ['property_damage'|'injury'|'fatal'], collision_type, weather,
        light_condition, surface_condition, pedestrian_involved,
        cyclist_involved, fatality_count, injury_count)
      fact_participants(participant_id, crash_id, participant_type
        ['driver'|'pedestrian'|'cyclist'|'other_non_motorist'|
        'unknown_non_motorist'], injury_severity, at_fault)
      dim_date(date, year, quarter, month, day_of_week)

    Data notes that change what a correct query looks like:
      - There is no municipality, neighborhood, or community column.
        agency_name is the reporting police agency (five values, the large
        majority "Montgomery County Police"), so it is a weak stand-in for
        "area"; road_name plus latitude/longitude is the usable geography.
      - Crash counts have no traffic-volume denominator. Most roads in the
        table carry only one or two recorded crashes because they are short
        or lightly travelled, not because they are safe - never read a low
        count as low risk.
      - road_name is NULL on roughly a quarter of rows. Any ranking of
        roads must exclude it (WHERE road_name IS NOT NULL), or the null
        group outranks every real road by an order of magnitude.
      - road_name holds the raw police-feed string: UPPERCASE and
        abbreviated ("GEORGIA AVE", never "Georgia Avenue"), with RD, DR,
        AVE, ST, LA, BLVD, PKWY and HWY as the common endings, and many
        rows carrying a direction, ramp, or second street on the end
        ("GEORGIA AVE (SB/L)", "CONNECTICUT AVE GEORGIA AVE"). So never
        match a road with = or a spelled-out name - that silently returns
        zero rows and looks like "no crashes here". Match the distinctive
        word only, with ILIKE '%GEORGIA%', which also gathers the ramp and
        intersection variants of the same road.
      - Coverage starts in 2015 and the most recent year is partial, so a
        year-over-year comparison that includes it will understate it.

    `question` states what you're trying to find out and `reason` explains
    why this query answers it - both are logged for audit, not optional
    filler. Results are capped and the query is validated before running;
    only SELECT statements against these tables are permitted.
    """
    return _safe(sql_tool.query_analytics, question=question, sql=sql, reason=reason)


@tool
def search_reports(query: str, top_k: int = 5, year_at_least: int | None = None) -> list[dict]:
    """Semantic search over Vision Zero county reports (annual reports,
    action plans, assessments). Returns passages with document title,
    page, publication year, source URL, and a similarity score - use those
    for citations, never invent a source. `year_at_least` optionally
    filters to reports published in or after that year.
    """
    return _safe(
        report_tool.search_reports, query=query, top_k=top_k, year_at_least=year_at_least,
    )


@tool
def get_source_metadata() -> list[dict]:
    """List every data source (datasets and report collections) with its
    description, refresh cadence, and last-updated date. Use this to
    answer questions about data freshness or provenance, or before citing
    a dataset by name.
    """
    return _safe(metadata_tool.get_source_metadata)


@tool
def percent_change(old: float, new: float) -> dict:
    """Percentage change from `old` to `new`. Use this instead of computing
    a percentage yourself - never do arithmetic in prose.
    """
    return statistics_tool.calculate_statistics("percent_change", old=old, new=new)


@tool
def rate_per(count: float, population: float, per: float = 100_000) -> dict:
    """`count` per `per` units of `population` (e.g. crashes per 100,000 residents)."""
    return statistics_tool.calculate_statistics("rate_per", count=count, population=population, per=per)


@tool
def average(values: list[float]) -> dict:
    """The mean of a list of numbers."""
    return statistics_tool.calculate_statistics("average", values=values)


@tool
def median(values: list[float]) -> dict:
    """The median of a list of numbers."""
    return statistics_tool.calculate_statistics("median", values=values)


@tool
def rank_items(items: list[dict], key: str, descending: bool = True) -> dict:
    """Rank a list of {"name"/"label": ..., <key>: number} dicts by `key`,
    adding a 1-based rank to each. Use for "which area had the most X" questions.
    """
    return statistics_tool.calculate_statistics("rank_items", items=items, key=key, descending=descending)


@tool
def year_over_year(series: list[dict]) -> dict:
    """Given [{"year": int, "value": number}, ...], returns each point with
    its change and percent change from the prior year. Use for trend questions.
    """
    return statistics_tool.calculate_statistics("year_over_year", series=series)


@tool
def build_visualization_spec(
    chart_type: str,
    columns: list[str],
    rows: list[list],
    x_field: str | None = None,
    y_field: str | None = None,
    title: str | None = None,
) -> dict:
    """Turn a query_analytics result (its `columns` and `rows`, unchanged)
    into a chart the user will see. chart_type is one of: 'line' (trend
    over time), 'bar' (comparison across categories), 'map' (needs
    latitude/longitude columns), 'kpi' (a single number), 'table'. Only
    call this with data that actually came from a prior query_analytics
    call in this conversation - never fabricate rows.
    """
    return visualization_tool.build_visualization_spec(
        chart_type, columns, rows, x_field=x_field, y_field=y_field, title=title,
    )


ALL_TOOLS = [
    query_analytics, search_reports, get_source_metadata,
    percent_change, rate_per, average, median, rank_items, year_over_year,
    build_visualization_spec,
]
