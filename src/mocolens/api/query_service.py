"""Backend for POST /api/query - runs the LangGraph agent and reshapes its
AgentAnswer into QueryResponse (frontend/src/types/query.ts).
"""
import json
import uuid

from langchain_core.messages import ToolMessage

from ..agent.schemas import AgentAnswer
from ..processing.curate import latest_run_info
from . import schemas

DOMAIN = "vision_zero"
_VIZ_TYPES = {"line", "bar", "map", "kpi", "table"}


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


def _extract_visualizations(messages: list) -> list[schemas.VisualizationSpec]:
    """Pull any build_visualization_spec results out of the tool-call
    history. Only successful specs (no "error") are surfaced.
    """
    specs = []
    for msg in messages:
        if not isinstance(msg, ToolMessage):
            continue
        try:
            data = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict) and data.get("type") in _VIZ_TYPES and not data.get("error"):
            specs.append(schemas.VisualizationSpec(
                id=data["id"], type=data["type"], title=data.get("title") or "", data=data.get("data"),
            ))
    return specs


def _to_response(question: str, answer: AgentAnswer, messages: list) -> schemas.QueryResponse:
    citations = [
        schemas.Citation(
            id=f"cite-{i}", title=c.title, source_type=c.source_type,
            url=c.url, page=c.page, published_at=c.published_at,
        )
        for i, c in enumerate(answer.citations)
    ]
    return schemas.QueryResponse(
        id=str(uuid.uuid4()),
        question=question,
        answer=answer.answer,
        summary=answer.summary,
        what_data_means=answer.what_data_means,
        county_report_points=answer.county_report_points,
        visualizations=_extract_visualizations(messages),
        citations=citations,
        follow_up_prompts=answer.follow_up_prompts,
        limitations=answer.caveats,
        data_as_of=(latest_run_info(DOMAIN) or {}).get("ran_at"),
    )


def ask(question: str) -> schemas.QueryResponse:
    result = agent_graph.run(question)
    return _to_response(question, result["final"], result["messages"])
