import pytest

from mocolens.retrieval.statistics_tool import (
    average,
    calculate_statistics,
    median,
    percent_change,
    rank_items,
    rate_per,
    year_over_year,
)


def test_percent_change_increase():
    assert percent_change(94, 126) == pytest.approx(34.0425531914894)


def test_percent_change_decrease():
    assert percent_change(126, 94) == pytest.approx(-25.396825396825395)


def test_percent_change_no_change():
    assert percent_change(50, 50) == 0.0


def test_percent_change_zero_baseline_raises():
    with pytest.raises(ValueError, match="zero baseline"):
        percent_change(0, 10)


def test_rate_per_default_100k():
    assert rate_per(935, 1_062_061, per=100_000) == pytest.approx(88.0398, rel=1e-3)


def test_rate_per_custom_denominator():
    assert rate_per(10, 5, per=1) == 2.0


def test_rate_per_zero_population_raises():
    with pytest.raises(ValueError, match="zero population"):
        rate_per(10, 0)


def test_average_normal():
    assert average([1, 2, 3, 4]) == 2.5


def test_average_empty_raises():
    with pytest.raises(ValueError, match="empty list"):
        average([])


def test_median_odd_count():
    assert median([3, 1, 2]) == 2


def test_median_even_count():
    assert median([1, 2, 3, 4]) == 2.5


def test_median_empty_raises():
    with pytest.raises(ValueError, match="empty list"):
        median([])


def test_rank_items_descending_default():
    items = [{"area": "A", "count": 10}, {"area": "B", "count": 30}, {"area": "C", "count": 20}]
    ranked = rank_items(items, key="count")
    assert [r["area"] for r in ranked] == ["B", "C", "A"]
    assert [r["rank"] for r in ranked] == [1, 2, 3]


def test_rank_items_ascending():
    items = [{"area": "A", "count": 10}, {"area": "B", "count": 30}]
    ranked = rank_items(items, key="count", descending=False)
    assert [r["area"] for r in ranked] == ["A", "B"]


def test_rank_items_empty_list():
    assert rank_items([], key="count") == []


def test_rank_items_missing_key_raises():
    with pytest.raises(ValueError, match="count"):
        rank_items([{"area": "A"}], key="count")


def test_rank_items_does_not_mutate_original_dicts():
    items = [{"area": "A", "count": 1}]
    rank_items(items, key="count")
    assert "rank" not in items[0]


def test_year_over_year_basic_series():
    series = [{"year": 2022, "value": 94}, {"year": 2023, "value": 102}, {"year": 2024, "value": 115}]
    result = year_over_year(series)
    assert result[0] == {"year": 2022, "value": 94, "change": None, "change_pct": None}
    assert result[1]["change"] == 8
    assert result[1]["change_pct"] == pytest.approx(percent_change(94, 102))
    assert result[2]["change"] == 13


def test_year_over_year_sorts_out_of_order_input():
    series = [{"year": 2024, "value": 115}, {"year": 2022, "value": 94}, {"year": 2023, "value": 102}]
    result = year_over_year(series)
    assert [p["year"] for p in result] == [2022, 2023, 2024]


def test_year_over_year_zero_value_does_not_crash_next_point():
    series = [{"year": 2020, "value": 0}, {"year": 2021, "value": 5}]
    result = year_over_year(series)
    assert result[1]["change"] == 5
    assert result[1]["change_pct"] is None  # zero baseline - no fabricated percentage


def test_year_over_year_single_point():
    result = year_over_year([{"year": 2022, "value": 94}])
    assert result == [{"year": 2022, "value": 94, "change": None, "change_pct": None}]


def test_year_over_year_empty():
    assert year_over_year([]) == []


# --- dispatch ---

def test_dispatch_percent_change():
    r = calculate_statistics("percent_change", old=94, new=126)
    assert r["error"] is None
    assert r["result"] == pytest.approx(percent_change(94, 126))


def test_dispatch_unknown_operation():
    r = calculate_statistics("do_something_impossible")
    assert r["result"] is None
    assert "unknown operation" in r["error"]


def test_dispatch_missing_required_argument():
    r = calculate_statistics("percent_change", old=10)  # missing 'new'
    assert r["result"] is None
    assert r["error"] is not None


def test_dispatch_math_error_becomes_error_field_not_exception():
    r = calculate_statistics("percent_change", old=0, new=10)
    assert r["result"] is None
    assert "zero baseline" in r["error"]


def test_dispatch_never_raises_for_bad_input():
    # a battery of malformed calls - none should raise, all should report an error
    bad_calls = [
        ("average", {"values": []}),
        ("median", {"values": []}),
        ("rate_per", {"count": 1, "population": 0}),
        ("rank_items", {"items": [{"x": 1}], "key": "y"}),
        ("percent_change", {}),
        ("unknown_op", {}),
    ]
    for operation, kwargs in bad_calls:
        r = calculate_statistics(operation, **kwargs)
        assert r["error"] is not None
