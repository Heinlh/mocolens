"""The agent's final structured output - shaped to match
frontend/src/types/query.ts's QueryResponse (the narrative fields; id,
metrics/crashTrend/hotspots/dataAsOf are filled in outside the LLM call,
see graph.py's finalize node and api/main.py once /api/query exists).
"""
from typing import Literal

from pydantic import BaseModel, Field


class Citation(BaseModel):
    title: str
    source_type: Literal["dataset", "report"]
    url: str | None = None
    page: str | None = None
    published_at: str | None = None


class AgentAnswer(BaseModel):
    """What the LLM is asked to produce via structured output at the end of
    a run. Every field here is meant to be traceable back to a tool result
    that actually happened in this conversation - see graph.py's
    validate_citations node, which strips any citation that doesn't match
    a real search_reports/get_source_metadata result from this run.
    """
    answer: str = Field(description="1-2 sentence direct answer to the user's question.")
    summary: str = Field(description="Plain-language summary of what the data shows - numbers, not jargon.")
    what_data_means: str = Field(description="A short paragraph explaining what the finding means for the reader.")
    county_report_points: list[str] = Field(
        default_factory=list,
        description="Bullet points on what county reports say, ONLY if search_reports was actually called and returned relevant passages.",
    )
    caveats: list[str] = Field(
        default_factory=list,
        description="Limitations: partial-period data, counts vs. rates, correlation vs. causation, small samples - per the project's analytical-integrity rules.",
    )
    citations: list[Citation] = Field(
        default_factory=list,
        description="Every citation must correspond to an actual tool result seen in this conversation - never invent a source.",
    )
    follow_up_prompts: list[str] = Field(
        default_factory=list, description="2-4 short natural follow-up questions a user might ask next.",
    )
