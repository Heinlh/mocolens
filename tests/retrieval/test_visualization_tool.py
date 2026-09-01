import pytest

from mocolens.retrieval.visualization_tool import (
    ALLOWED_CHART_TYPES,
    build_visualization_spec,
    humanize_label,
)


def test_humanize_label_known_column():
    assert humanize_label("pedestrian_involved") == "Pedestrian involved"


def test_humanize_label_unknown_column_falls_back_to_title_case():
    assert humanize_label("some_future_column") == "Some future column"


def test_humanize_label_duckdb_count_star_alias():
    assert humanize_label("count_star()") == "Count"


def test_unsupported_chart_type_rejected():
    r = build_visualization_spec("radar", ["a"], [[1]])
    assert r["error"] is not None
    assert "radar" in r["error"]


def test_all_documented_chart_types_are_accepted_types():
    assert ALLOWED_CHART_TYPES == {"line", "bar", "map", "kpi", "table"}


def test_empty_rows_rejected():
    r = build_visualization_spec("line", ["year", "count"], [], x_field="year", y_field="count")
    assert r["error"] == "no rows to visualize"


def test_line_chart_basic():
    r = build_visualization_spec(
        "line", ["year", "count"], [[2022, 94], [2023, 102]],
        x_field="year", y_field="count", title="Pedestrian crashes over time",
    )
    assert r["error"] is None
    assert r["type"] == "line"
    assert r["title"] == "Pedestrian crashes over time"
    assert r["data"]["x_label"] == "Year"
    assert r["data"]["points"] == [{"x": 2022, "y": 94}, {"x": 2023, "y": 102}]


def test_bar_chart_basic():
    r = build_visualization_spec(
        "bar", ["severity", "count_star()"], [["injury", 5], ["fatal", 1]],
        x_field="severity", y_field="count_star()",
    )
    assert r["error"] is None
    assert r["data"]["y_label"] == "Count"
    assert r["data"]["points"][1] == {"x": "fatal", "y": 1}


def test_line_chart_missing_x_field_rejected():
    r = build_visualization_spec("line", ["year", "count"], [[2022, 94]], y_field="count")
    assert r["error"] is not None
    assert "x_field" in r["error"]


def test_field_not_in_columns_rejected():
    r = build_visualization_spec("line", ["year", "count"], [[2022, 94]], x_field="not_a_column", y_field="count")
    assert r["error"] is not None
    assert "not_a_column" in r["error"]


def test_kpi_basic():
    r = build_visualization_spec("kpi", ["total_crashes"], [[935]], y_field="total_crashes", title="Total crashes")
    assert r["error"] is None
    assert r["data"] == {"label": "Total crashes", "value": 935}


def test_kpi_missing_y_field_rejected():
    r = build_visualization_spec("kpi", ["total_crashes"], [[935]])
    assert r["error"] is not None


def test_map_basic_with_value():
    r = build_visualization_spec(
        "map", ["latitude", "longitude", "crash_id"],
        [[39.05, -77.10, "C1"], [39.10, -77.20, "C2"]],
        y_field="crash_id",
    )
    assert r["error"] is None
    assert r["data"]["points"] == [
        {"latitude": 39.05, "longitude": -77.10, "value": "C1"},
        {"latitude": 39.10, "longitude": -77.20, "value": "C2"},
    ]


def test_map_filters_out_null_coordinates():
    # matches the curation layer's behavior of nulling out-of-bounds coords
    # rather than dropping the row - the viz layer must not plot None,None
    r = build_visualization_spec(
        "map", ["latitude", "longitude"],
        [[39.05, -77.10], [None, None], [39.10, None]],
    )
    assert r["error"] is None
    assert len(r["data"]["points"]) == 1
    assert r["data"]["points"][0]["latitude"] == 39.05


def test_map_without_value_field():
    r = build_visualization_spec("map", ["latitude", "longitude"], [[39.05, -77.10]])
    assert r["error"] is None
    assert r["data"]["points"] == [{"latitude": 39.05, "longitude": -77.10}]
    assert r["data"]["value_label"] is None


def test_table_basic():
    r = build_visualization_spec("table", ["road_name", "fatality_count"], [["MAIN ST", 1], ["OAK AVE", 0]])
    assert r["error"] is None
    assert r["data"]["headers"] == ["Road", "Fatalities"]
    assert r["data"]["rows"] == [["MAIN ST", 1], ["OAK AVE", 0]]
    assert r["data"]["truncated"] is False
    assert r["data"]["total_rows"] == 2


def test_table_truncates_at_20_rows():
    rows = [[i] for i in range(50)]
    r = build_visualization_spec("table", ["n"], rows)
    assert r["error"] is None
    assert len(r["data"]["rows"]) == 20
    assert r["data"]["truncated"] is True
    assert r["data"]["total_rows"] == 50


def test_spec_ids_are_unique_across_calls():
    r1 = build_visualization_spec("kpi", ["x"], [[1]], y_field="x")
    r2 = build_visualization_spec("kpi", ["x"], [[1]], y_field="x")
    assert r1["id"] != r2["id"]


def test_title_defaults_to_empty_string_not_none():
    r = build_visualization_spec("kpi", ["x"], [[1]], y_field="x")
    assert r["title"] == ""
