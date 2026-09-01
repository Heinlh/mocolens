"""build_visualization_spec (architecture doc §14.5): turns verified query
results into a chart/map spec - never raw data plus a chart library call.
Output shape aligns with frontend/src/types/visualization.ts's
VisualizationSpec (id/type/title); a "data" field is added here since that
frontend type is currently a stub with no payload - it's the natural next
field to add there when the frontend starts consuming real specs.

Only the 5 types the architecture doc names in §14.5 are accepted (line,
bar, map, kpi, table) - the frontend's own VisualizationType union also
lists 'donut', but nothing in the doc or an existing tool calls for one
yet, so it isn't built here (YAGNI - add it when something actually
needs it, matching it against whatever data shape that need turns out to
require).
"""
import itertools

ALLOWED_CHART_TYPES = {"line", "bar", "map", "kpi", "table"}

# §19: "Pedestrian crashes" not "non_motorist_incident_count". Falls back to
# a humanized version of the raw column name for anything not listed.
_LABELS = {
    "crash_id": "Crash ID",
    "crash_date": "Date",
    "crash_time": "Time",
    "year": "Year",
    "severity": "Severity",
    "pedestrian_involved": "Pedestrian involved",
    "cyclist_involved": "Cyclist involved",
    "fatality_count": "Fatalities",
    "injury_count": "Injuries",
    "road_name": "Road",
    "agency_name": "Reporting agency",
    "route_type": "Route type",
    "collision_type": "Collision type",
    "weather": "Weather",
    "light_condition": "Light condition",
    "latitude": "Latitude",
    "longitude": "Longitude",
    "count_star()": "Count",  # DuckDB's default alias for an unaliased COUNT(*)
}

_TABLE_ROW_LIMIT = 20
_id_counter = itertools.count(1)


def humanize_label(column: str) -> str:
    if column in _LABELS:
        return _LABELS[column]
    return column.replace("_", " ").replace("()", "").strip().capitalize()


def _column_index(columns: list[str], field: str) -> int:
    if field not in columns:
        raise ValueError(f"'{field}' is not one of the query's columns: {columns}")
    return columns.index(field)


def _build_line_or_bar(columns: list[str], rows: list[list], x_field: str, y_field: str) -> dict:
    x_i, y_i = _column_index(columns, x_field), _column_index(columns, y_field)
    return {
        "x_label": humanize_label(x_field),
        "y_label": humanize_label(y_field),
        "points": [{"x": row[x_i], "y": row[y_i]} for row in rows],
    }


def _build_map(columns: list[str], rows: list[list], lat_field: str, lon_field: str, value_field: str | None) -> dict:
    lat_i, lon_i = _column_index(columns, lat_field), _column_index(columns, lon_field)
    value_i = _column_index(columns, value_field) if value_field else None
    points = []
    for row in rows:
        if row[lat_i] is None or row[lon_i] is None:
            continue  # coordinates already nulled by the curation layer's bounds check
        point = {"latitude": row[lat_i], "longitude": row[lon_i]}
        if value_i is not None:
            point["value"] = row[value_i]
        points.append(point)
    return {"points": points, "value_label": humanize_label(value_field) if value_field else None}


def _build_kpi(columns: list[str], rows: list[list], y_field: str) -> dict:
    y_i = _column_index(columns, y_field)
    return {"label": humanize_label(y_field), "value": rows[0][y_i]}


def _build_table(columns: list[str], rows: list[list]) -> dict:
    truncated = len(rows) > _TABLE_ROW_LIMIT
    return {
        "headers": [humanize_label(c) for c in columns],
        "rows": rows[:_TABLE_ROW_LIMIT],
        "truncated": truncated,
        "total_rows": len(rows),
    }


def build_visualization_spec(
    chart_type: str,
    columns: list[str],
    rows: list[list],
    *,
    x_field: str | None = None,
    y_field: str | None = None,
    lat_field: str = "latitude",
    lon_field: str = "longitude",
    title: str | None = None,
) -> dict:
    """Converts a query_analytics-shaped result (columns + rows) into a
    chart spec. Never raises - returns {"error": "..."} for a bad chart
    type, missing field, or empty result, so an agent can see why and
    retry with a different spec instead of crashing.
    """
    if chart_type not in ALLOWED_CHART_TYPES:
        return {"error": f"unsupported chart_type '{chart_type}', allowed: {sorted(ALLOWED_CHART_TYPES)}"}
    if not rows:
        return {"error": "no rows to visualize"}

    try:
        if chart_type in ("line", "bar"):
            if not x_field or not y_field:
                raise ValueError(f"chart_type '{chart_type}' requires both x_field and y_field")
            data = _build_line_or_bar(columns, rows, x_field, y_field)
        elif chart_type == "map":
            data = _build_map(columns, rows, lat_field, lon_field, y_field)
        elif chart_type == "kpi":
            if not y_field:
                raise ValueError("chart_type 'kpi' requires y_field")
            data = _build_kpi(columns, rows, y_field)
        else:  # table
            data = _build_table(columns, rows)
    except ValueError as exc:
        return {"error": str(exc)}

    return {
        "id": f"viz-{next(_id_counter)}",
        "type": chart_type,
        "title": title or "",
        "data": data,
        "error": None,
    }
