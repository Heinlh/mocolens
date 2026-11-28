"""The LangGraph state machine (architecture doc §13, §15, §17).

    START -> agent --(tool calls requested)--> tools --(cycles left)--> agent (loop)
                  \\--(no tool calls)--> finalize              \\--(3 cycles used)--> finalize
                                                                                          |
                                                                                          v
                                                                             validate_citations -> END

Bounded to MAX_CYCLES=3 retrieval/planning cycles per §17 ("Limit loops in
the MVP to avoid runaway behavior"). validate_citations is deterministic
Python, not another LLM call - it strips any citation the model produced
that doesn't correspond to an actual search_reports/get_source_metadata
result seen in this run, so a hallucinated source can't reach the user
(§27, §33.10).
"""
import json
import logging
from time import perf_counter
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.utils.json import parse_partial_json
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from .prompts import FINALIZE_INSTRUCTIONS, SYSTEM_PROMPT
from .schemas import AgentAnswer
from .tools import ALL_TOOLS

MAX_CYCLES = 3
logger = logging.getLogger(__name__)


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    cycle_count: int
    final: AgentAnswer | None
    planner_ms: list[int]
    finalizer_ms: int


def _collect_seen_sources(messages: list[BaseMessage]) -> set[tuple[str | None, str | None]]:
    """(title, url) pairs from every search_reports/get_source_metadata
    result actually returned during this run - the ground truth
    validate_citations checks the model's claimed citations against.
    """
    seen = set()
    for msg in messages:
        if not isinstance(msg, ToolMessage):
            continue
        try:
            data = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(data, list):
            continue
        for item in data:
            if not isinstance(item, dict):
                continue
            title = item.get("document_title") or item.get("title")
            url = item.get("source_url") or item.get("url")
            if title or url:
                seen.add((title, url))
    return seen


def validate_citations(answer: AgentAnswer, messages: list[BaseMessage]) -> AgentAnswer:
    seen = _collect_seen_sources(messages)
    if not seen:
        # no report/source tool ever ran - no citation can be real
        return answer.model_copy(update={"citations": []})

    seen_titles = {t for t, _ in seen if t}
    seen_urls = {u for _, u in seen if u}
    kept = [c for c in answer.citations if c.title in seen_titles or c.url in seen_urls]
    return answer.model_copy(update={"citations": kept})


def system_prompt(info: dict | None = None) -> str:
    """SYSTEM_PROMPT plus the dates the shipped crash data actually covers.

    Without them the model guesses which year is "last year" or the latest
    complete one, and in production it cannot look them up: the raw lake that
    get_source_metadata reads is not in the container image, so its
    last_updated is None there. build_info.json ships with the tables.
    """
    if info is None:
        from ..processing import curate
        info = curate.build_info("vision_zero") or {}
    end = info.get("coverage_end")
    if not end:
        return SYSTEM_PROMPT
    year = int(end[:4])
    latest_complete = year if end[5:] == "12-31" else year - 1
    downloaded = f", downloaded from the county on {info['snapshot_date']}" if info.get("snapshot_date") else ""
    partial = f" {year} is partial." if year != latest_complete else ""
    return SYSTEM_PROMPT + f"""

# The data right now
The crash data runs from {info.get('coverage_start') or '2015-01-01'} through {end}{downloaded}.
When you say how current the data is, give {end}, the date of the latest crash - not the
download date. The latest complete year is {latest_complete}: use it for "last year", for "the
most recent year", and for any single-year number when no year is asked for.{partial}"""


def build_graph(llm=None, emit=None):
    """Builds and compiles the graph. `llm` is injectable (any object with
    .bind_tools() and .with_structured_output(), matching LangChain's chat
    model interface) so tests can substitute a fake model instead of
    calling watsonx.ai for real.
    """
    if llm is None:
        from .llm import get_llm
        llm = get_llm()

    llm_with_tools = llm.bind_tools(ALL_TOOLS)
    prompt = system_prompt()
    if emit is None:
        llm_structured = llm.with_structured_output(AgentAnswer)
    else:
        final_tool = llm.bind_tools([AgentAnswer], tool_choice="AgentAnswer", parallel_tool_calls=False)

    def agent_node(state: AgentState) -> dict:
        messages = state["messages"]
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=prompt)] + list(messages)
        started = perf_counter()
        response = llm_with_tools.invoke(messages)
        elapsed = round((perf_counter() - started) * 1000)
        return {"messages": [response], "planner_ms": [*state.get("planner_ms", []), elapsed]}

    def tools_node(state: AgentState) -> dict:
        result = ToolNode(ALL_TOOLS).invoke(state)
        return {"messages": result["messages"], "cycle_count": state["cycle_count"] + 1}

    def route_after_agent(state: AgentState) -> str:
        last = state["messages"][-1]
        has_tool_calls = isinstance(last, AIMessage) and bool(last.tool_calls)
        return "tools" if has_tool_calls else "finalize"

    def route_after_tools(state: AgentState) -> str:
        # Checked here, not after the next agent call - once the cap is hit
        # there is no point asking the model to plan a 4th round just to
        # discard whatever tool call it decides on. Cheaper and matches
        # "3 retrieval/planning cycles" (§17) exactly: 3 tool executions,
        # not 3 tool executions plus one wasted planning call.
        return "finalize" if state["cycle_count"] >= MAX_CYCLES else "agent"

    def finalize_node(state: AgentState) -> dict:
        # The system prompt is not stored in state (agent_node adds it per
        # call), so it is added here too: its scope, privacy and integrity
        # rules have to bind the call that writes the user-facing answer.
        messages = (
            [SystemMessage(content=prompt)]
            + [m for m in state["messages"] if not isinstance(m, SystemMessage)]
            + [HumanMessage(content=FINALIZE_INSTRUCTIONS)]
        )
        started = perf_counter()
        if emit is None:
            answer = llm_structured.invoke(messages)
        else:
            # Preview only public narrative fields. Require complete, valid
            # structured output before publishing citations or caching anything.
            args = ""
            previous = None
            for chunk in final_tool.stream(messages):
                for part in chunk.tool_call_chunks:
                    args += part.get("args") or ""
                if not args:
                    continue
                try:
                    parsed = parse_partial_json(args)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict) and isinstance(parsed.get("answer"), str):
                    preview = (parsed["answer"], parsed.get("summary") or "")
                    if preview != previous:
                        emit({"type": "text", "answer": preview[0], "summary": preview[1]})
                        previous = preview
            answer = AgentAnswer.model_validate_json(args)
        return {"final": answer, "finalizer_ms": round((perf_counter() - started) * 1000)}

    def validate_citations_node(state: AgentState) -> dict:
        return {"final": validate_citations(state["final"], state["messages"])}

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)
    graph.add_node("finalize", finalize_node)
    graph.add_node("validate_citations", validate_citations_node)

    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", route_after_agent, {"tools": "tools", "finalize": "finalize"})
    graph.add_conditional_edges("tools", route_after_tools, {"agent": "agent", "finalize": "finalize"})
    graph.add_edge("finalize", "validate_citations")
    graph.add_edge("validate_citations", END)

    return graph.compile()


def run(question: str, llm=None, emit=None) -> AgentState:
    """Runs the graph on one question, returns the full final state (messages
    included) - the API layer needs the message history too, to pull any
    build_visualization_spec results out alongside the answer itself.
    """
    compiled = build_graph(llm, emit)
    result = compiled.invoke({
        "messages": [HumanMessage(content=question)],
        "cycle_count": 0,
        "final": None,
    })
    from ..retrieval.sql_tool import request_id
    logger.info("agent_trace %s", json.dumps({
        "request_id": request_id.get(), **trace(result),
        "planner_ms": result["planner_ms"], "finalizer_ms": result["finalizer_ms"],
    }))
    return result


def trace(result: AgentState) -> dict:
    planners = len(result["planner_ms"])
    return {"plannerCalls": planners, "finalizerCalls": 1, "modelCalls": planners + 1}


def ask(question: str, llm=None) -> AgentAnswer:
    """Runs the graph on one question, returns just the validated final answer."""
    return run(question, llm)["final"]
