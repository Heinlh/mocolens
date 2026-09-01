"""Response models mirroring frontend/src/types/analytics.ts and query.ts
field-for-field.

Python is snake_case, the frontend is camelCase - `alias_generator` handles
the conversion so the two stay in lockstep without hand-renaming every key.
Any field added to a TS interface should get the same name here.
"""
from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Metric(ApiModel):
    label: str
    value: float | str
    change: float | None = None
    change_direction: str | None = None  # 'up' | 'down' | 'neutral'
    change_is_positive: bool | None = None
    description: str | None = None


class TimeSeriesPoint(ApiModel):
    label: str
    value: float


class CategoryValue(ApiModel):
    label: str
    value: float
    color: str | None = None


class Hotspot(ApiModel):
    id: str
    area: str
    latitude: float
    longitude: float
    crash_count: int
    trend: float
    intensity: float


class Insight(ApiModel):
    id: str
    text: str


class DashboardResponse(ApiModel):
    metrics: list[Metric]
    crash_trend: list[TimeSeriesPoint]
    severity_breakdown: list[CategoryValue]
    road_user_breakdown: list[CategoryValue]
    hotspots: list[Hotspot]
    insights: list[Insight]
    data_as_of: str | None = None


# --- frontend/src/types/sources.ts + query.ts ---

class Citation(ApiModel):
    id: str
    title: str
    source_type: str  # 'dataset' | 'report'
    url: str | None = None
    page: str | None = None
    published_at: str | None = None


class VisualizationSpec(ApiModel):
    id: str
    type: str  # 'line' | 'bar' | 'map' | 'kpi' | 'table'
    title: str
    data: dict[str, Any] | None = None


class QueryResponse(ApiModel):
    id: str
    question: str
    answer: str
    summary: str
    # Not populated yet - these are tied to the old mock's fixed KPI+chart+map
    # layout, which assumes one specific shape of evidence. The agent's
    # evidence varies per question (whatever SQL/search it decided to run),
    # so there's no single generic mapping from "arbitrary query_analytics
    # rows" to these typed shapes yet. Real narrative content (answer,
    # summary, citations, visualizations from any build_visualization_spec
    # calls) IS populated below - this is a known, documented gap, not an
    # oversight.
    metrics: list[Metric] = []
    crash_trend: list[TimeSeriesPoint] = []
    hotspots: list[Hotspot] = []
    what_data_means: str
    county_report_points: list[str] = []
    visualizations: list[VisualizationSpec] = []
    citations: list[Citation] = []
    follow_up_prompts: list[str] = []
    limitations: list[str] = []
    data_as_of: str | None = None
