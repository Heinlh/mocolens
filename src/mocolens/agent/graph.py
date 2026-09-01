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
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from .prompts import FINALIZE_INSTRUCTIONS, SYSTEM_PROMPT
from .schemas import AgentAnswer
from .tools import ALL_TOOLS

MAX_CYCLES = 3


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    cycle_count: int
    final: AgentAnswer | None


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


def build_graph(llm=None):
    """Builds and compiles the graph. `llm` is injectable (any object with
    .bind_tools() and .with_structured_output(), matching LangChain's chat
    model interface) so tests can substitute a fake model instead of
    calling watsonx.ai for real.
    """
    if llm is None:
        from .llm import get_llm
        llm = get_llm()

    llm_with_tools = llm.bind_tools(ALL_TOOLS)
    llm_structured = llm.with_structured_output(AgentAnswer)

    def agent_node(state: AgentState) -> dict:
        messages = state["messages"]
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(messages)
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}

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
        messages = list(state["messages"]) + [HumanMessage(content=FINALIZE_INSTRUCTIONS)]
        answer = llm_structured.invoke(messages)
        return {"final": answer}

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


def run(question: str, llm=None) -> AgentState:
    """Runs the graph on one question, returns the full final state (messages
    included) - the API layer needs the message history too, to pull any
    build_visualization_spec results out alongside the answer itself.
    """
    compiled = build_graph(llm)
    return compiled.invoke({
        "messages": [HumanMessage(content=question)],
        "cycle_count": 0,
        "final": None,
    })


def ask(question: str, llm=None) -> AgentAnswer:
    """Runs the graph on one question, returns just the validated final answer."""
    return run(question, llm)["final"]
