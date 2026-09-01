"""calculate_statistics (architecture doc §14.4): deterministic arithmetic
the agent calls instead of doing math in prose. Every function here is a
plain, independently-testable pure function; `calculate_statistics` is a
thin name -> function dispatch on top, for a uniform agent tool-call shape.
"""
import statistics as _stats


def percent_change(old: float, new: float) -> float:
    """(new - old) / old * 100. Raises ValueError on a zero baseline rather
    than returning inf/nan - "the county had 0 crashes in 2020" is a real
    baseline an agent could hit, and silently returning inf would likely
    get parroted into an answer as a real percentage.
    """
    if old == 0:
        raise ValueError("cannot compute percent change from a zero baseline")
    return (new - old) / old * 100


def rate_per(count: float, population: float, per: float = 100_000) -> float:
    """count per `per` units of population (e.g. crashes per 100,000 residents)."""
    if population == 0:
        raise ValueError("cannot compute a rate with zero population")
    return count / population * per


def average(values: list[float]) -> float:
    if not values:
        raise ValueError("cannot average an empty list")
    return sum(values) / len(values)


def median(values: list[float]) -> float:
    if not values:
        raise ValueError("cannot take the median of an empty list")
    return _stats.median(values)


def rank_items(items: list[dict], key: str, descending: bool = True) -> list[dict]:
    """Sort `items` by `items[i][key]` and add a 1-based "rank" field to each."""
    if not items:
        return []
    if any(key not in item for item in items):
        raise ValueError(f"every item must have a '{key}' field")
    ranked = sorted(items, key=lambda item: item[key], reverse=descending)
    return [{**item, "rank": i + 1} for i, item in enumerate(ranked)]


def year_over_year(series: list[dict]) -> list[dict]:
    """series: [{"year": int, "value": number}, ...], any order.

    Returns the same points sorted by year, each with "change" (absolute)
    and "change_pct" (None where the prior value was 0, matching
    percent_change's own zero-baseline guard - never inf/nan).
    """
    if not series:
        return []
    ordered = sorted(series, key=lambda p: p["year"])
    result = []
    prev_value = None
    for point in ordered:
        value = point["value"]
        change = None if prev_value is None else value - prev_value
        change_pct = None
        if prev_value is not None:
            try:
                change_pct = percent_change(prev_value, value)
            except ValueError:
                change_pct = None
        result.append({"year": point["year"], "value": value, "change": change, "change_pct": change_pct})
        prev_value = value
    return result


_OPERATIONS = {
    "percent_change": percent_change,
    "rate_per": rate_per,
    "average": average,
    "median": median,
    "rank_items": rank_items,
    "year_over_year": year_over_year,
}


def calculate_statistics(operation: str, **kwargs) -> dict:
    """Uniform dispatch: {"operation": "...", "result": ..., "error": None}
    on success, {"result": None, "error": "..."} on a bad operation name,
    missing/wrong arguments, or a math error (zero baseline, empty list).
    Never raises - matches query_analytics' agent-facing contract of
    returning a readable rejection instead of crashing the caller.
    """
    fn = _OPERATIONS.get(operation)
    if fn is None:
        return {"operation": operation, "result": None, "error": f"unknown operation '{operation}', allowed: {sorted(_OPERATIONS)}"}
    try:
        result = fn(**kwargs)
    except (TypeError, ValueError) as exc:
        return {"operation": operation, "result": None, "error": str(exc)}
    return {"operation": operation, "result": result, "error": None}
