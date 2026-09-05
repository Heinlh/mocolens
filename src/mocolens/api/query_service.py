"""Backend for POST /api/query - runs the LangGraph agent and reshapes its
AgentAnswer into QueryResponse (frontend/src/types/query.ts).
"""
import json
import uuid

from langchain_core.messages import ToolMessage

from ..agent.schemas import AgentAnswer
from ..processing.curate import data_as_of
from ..retrieval.visualization_tool import build_visualization_spec
from . import schemas

DOMAIN = "vision_zero"
_VIZ_TYPES = {"line", "bar", "map", "kpi", "table"}
_TIME_FIELDS = {"year", "month", "date", "crash_date", "quarter", "week"}
_COUNT_FIELD_HINTS = ("count", "total", "number", "fatal", "injur", "rate", "percent")


class _LazyAgentGraph:
    """Keep LangGraph and the retrieval stack out of API startup.

    Render's free instance has 512 MiB of RAM. Importing the complete agent
    tool graph before Uvicorn binds its port can exhaust that budget even
    when the request is only for /api/health or the dashboard. Tests also
    patch ``agent_graph.run``, so this small proxy preserves that seam.
    """

    @staticmethod
    def run(question: str):
        from ..agent import graph

        return graph.run(question)


agent_graph = _LazyAgentGraph()


def _tool_payloads(messages: list) -> list[dict]:
    """Return successfully decoded object payloads from tool messages."""
    payloads = []
    for msg in messages:
        if not isinstance(msg, ToolMessage):
            continue
        try:
            data = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict):
            payloads.append(data)
    return payloads


def _extract_visualizations(messages: list) -> list[schemas.VisualizationSpec]:
    """Pull any build_visualization_spec results out of the tool-call
    history. Only successful specs (no "error") are surfaced.
    """
    specs = []
    for data in _tool_payloads(messages):
        if isinstance(data, dict) and data.get("type") in _VIZ_TYPES and not data.get("error"):
            specs.append(schemas.VisualizationSpec(
                id=data["id"], type=data["type"], title=data.get("title") or "", data=data.get("data"),
            ))
    return specs


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _numeric_fields(columns: list[str], rows: list[list]) -> list[str]:
    return [
        column
        for index, column in enumerate(columns)
        if any(index < len(row) and _is_number(row[index]) for row in rows)
    ]


def _best_value_field(columns: list[str], numeric_fields: list[str], excluded: set[str]) -> str | None:
    candidates = [field for field in numeric_fields if field not in excluded]
    if not candidates:
        return None
    return next(
        (field for field in candidates if any(hint in field.lower() for hint in _COUNT_FIELD_HINTS)),
        candidates[-1],
    )


def _derive_visualization(question: str, messages: list) -> schemas.VisualizationSpec | None:
    """Choose a useful chart for verified query results when the agent omitted
    an explicit visualization tool call. This is deliberately deterministic:
    it never invents values and only reshapes rows returned by query_analytics.
    """
    query_results = [
        payload for payload in _tool_payloads(messages)
        if isinstance(payload.get("columns"), list)
        and isinstance(payload.get("rows"), list)
        and payload.get("rows")
        and not payload.get("error")
    ]
    if not query_results:
        return None

    result = query_results[-1]
    columns = [str(column) for column in result["columns"]]
    rows = [row for row in result["rows"] if isinstance(row, list)]
    if not columns or not rows:
        return None

    numeric = _numeric_fields(columns, rows)
    lowered = {column.lower(): column for column in columns}
    title = question.strip().rstrip("?.!")
    chart_type = "table"
    x_field = None
    y_field = None

    if "latitude" in lowered and "longitude" in lowered:
        chart_type = "map"
        y_field = _best_value_field(
            columns, numeric, {lowered["latitude"], lowered["longitude"]},
        )
    else:
        time_field = next((column for column in columns if column.lower() in _TIME_FIELDS), None)
        value_field = _best_value_field(columns, numeric, {time_field} if time_field else set())
        if time_field and value_field and len(rows) > 1:
            chart_type, x_field, y_field = "line", time_field, value_field
        elif len(rows) == 1 and value_field:
            chart_type, y_field = "kpi", value_field
        elif value_field and len(rows) > 1:
            category_field = next((column for column in columns if column not in numeric), None)
            if category_field:
                chart_type, x_field, y_field = "bar", category_field, value_field

    spec = build_visualization_spec(
        chart_type, columns, rows, x_field=x_field, y_field=y_field,
        title=title or "Query results",
    )
    if spec.get("error"):
        return None
    return schemas.VisualizationSpec(
        id=spec["id"], type=spec["type"], title=spec["title"], data=spec["data"],
    )


def _to_response(question: str, answer: AgentAnswer, messages: list) -> schemas.QueryResponse:
    citations = [
        schemas.Citation(
            id=f"cite-{i}", title=c.title, source_type=c.source_type,
            url=c.url, page=c.page, published_at=c.published_at,
        )
        for i, c in enumerate(answer.citations)
    ]
    visualizations = _extract_visualizations(messages)
    if not visualizations:
        derived = _derive_visualization(question, messages)
        if derived:
            visualizations = [derived]

    return schemas.QueryResponse(
        id=str(uuid.uuid4()),
        question=question,
        answer=answer.answer,
        summary=answer.summary,
        what_data_means=answer.what_data_means,
        county_report_points=answer.county_report_points,
        visualizations=visualizations,
        citations=citations,
        follow_up_prompts=answer.follow_up_prompts,
        limitations=answer.caveats,
        data_as_of=data_as_of(DOMAIN),
    )


def ask(question: str) -> schemas.QueryResponse:
    result = agent_graph.run(question)
    return _to_response(question, result["final"], result["messages"])
