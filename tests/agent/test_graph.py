"""Tests the graph's control flow (routing, the 3-cycle bound, citation
validation) against a fake, scriptable LLM - none of this needs real
watsonx.ai credentials. The tools themselves are already covered by
tests/retrieval/; here a tiny fake tool stands in so these tests don't
depend on real data files being present.
"""
import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool

from mocolens.agent import graph as graph_module
from mocolens.agent.schemas import AgentAnswer, Citation


@tool
def fake_search_reports(query: str) -> list[dict]:
    """test-only stand-in for search_reports"""
    return [{"document_title": "FY25 Annual Report", "source_url": "https://example.gov/fy25.pdf", "page": "3"}]


@tool
def fake_no_op(note: str) -> dict:
    """test-only tool that does nothing useful, for cycle-limit tests"""
    return {"ok": True}


class FakeStructured:
    def __init__(self, answer: AgentAnswer):
        self._answer = answer

    def invoke(self, messages):
        return self._answer


class FakeLLM:
    """Scriptable stand-in for a LangChain chat model: .bind_tools() then
    .invoke() pops the next scripted AIMessage each call; .with_structured_output()
    returns the scripted final answer.
    """
    def __init__(self, agent_responses: list[AIMessage], final_answer: AgentAnswer):
        self._responses = list(agent_responses)
        self._final_answer = final_answer
        self.invoke_count = 0

    def bind_tools(self, tools):
        return self

    def with_structured_output(self, schema):
        return FakeStructured(self._final_answer)

    def invoke(self, messages):
        self.invoke_count += 1
        return self._responses.pop(0)


def _tool_call_message(tool_name: str, call_id: str = "call_1", args: dict | None = None) -> AIMessage:
    default_args = {"fake_search_reports": {"query": "test"}, "fake_no_op": {"note": "test"}}
    return AIMessage(content="", tool_calls=[
        {"name": tool_name, "args": args if args is not None else default_args.get(tool_name, {}), "id": call_id}
    ])


def _no_tool_call_message() -> AIMessage:
    return AIMessage(content="Here is my answer.")


BASE_ANSWER = AgentAnswer(answer="Yes.", summary="Crashes rose.", what_data_means="More crashes happened.")


@pytest.fixture(autouse=True)
def use_fake_tool(monkeypatch):
    monkeypatch.setattr(graph_module, "ALL_TOOLS", [fake_search_reports, fake_no_op])


def test_no_tools_needed_goes_straight_to_finalize():
    llm = FakeLLM(agent_responses=[_no_tool_call_message()], final_answer=BASE_ANSWER)
    result = graph_module.ask("trivial question", llm=llm)
    assert result.answer == "Yes."
    assert llm.invoke_count == 1  # only the initial agent call, no loop


def test_single_tool_call_then_finalize():
    llm = FakeLLM(
        agent_responses=[_tool_call_message("fake_search_reports"), _no_tool_call_message()],
        final_answer=BASE_ANSWER,
    )
    result = graph_module.ask("a real question", llm=llm)
    assert result.answer == "Yes."
    assert llm.invoke_count == 2  # agent -> tools -> agent (sees results, stops)


def test_cycle_limit_is_enforced():
    # the model keeps asking for more tools forever - must stop at MAX_CYCLES
    responses = [_tool_call_message("fake_no_op", call_id=f"c{i}") for i in range(10)]
    llm = FakeLLM(agent_responses=responses, final_answer=BASE_ANSWER)
    result = graph_module.ask("keeps wanting more evidence", llm=llm)
    assert result.answer == "Yes."
    # exactly MAX_CYCLES agent->tools round trips before being forced to finalize
    assert llm.invoke_count == graph_module.MAX_CYCLES


def test_finalize_receives_tool_results_in_message_history():
    """Regression check: the finalize call must see what the tools actually
    returned, not just the original question."""
    seen_messages = []

    class RecordingStructured:
        def invoke(self, messages):
            seen_messages.extend(messages)
            return BASE_ANSWER

    class RecordingLLM(FakeLLM):
        def with_structured_output(self, schema):
            return RecordingStructured()

    llm = RecordingLLM(
        agent_responses=[_tool_call_message("fake_search_reports"), _no_tool_call_message()],
        final_answer=BASE_ANSWER,
    )
    graph_module.ask("a real question", llm=llm)
    tool_messages = [m for m in seen_messages if isinstance(m, ToolMessage)]
    assert len(tool_messages) == 1
    assert "FY25 Annual Report" in tool_messages[0].content


# --- citation validation ---

def _tool_message(payload) -> ToolMessage:
    return ToolMessage(content=json.dumps(payload), tool_call_id="x")


def test_validate_citations_keeps_a_real_one():
    messages = [_tool_message([{"document_title": "FY25 Annual Report", "source_url": "https://x.gov/fy25.pdf"}])]
    answer = BASE_ANSWER.model_copy(update={"citations": [
        Citation(title="FY25 Annual Report", source_type="report", url="https://x.gov/fy25.pdf"),
    ]})
    result = graph_module.validate_citations(answer, messages)
    assert len(result.citations) == 1


def test_validate_citations_strips_a_hallucinated_one():
    messages = [_tool_message([{"document_title": "FY25 Annual Report", "source_url": "https://x.gov/fy25.pdf"}])]
    answer = BASE_ANSWER.model_copy(update={"citations": [
        Citation(title="A Report That Was Never Retrieved", source_type="report", url="https://fake.gov/nope.pdf"),
    ]})
    result = graph_module.validate_citations(answer, messages)
    assert result.citations == []


def test_validate_citations_strips_everything_if_no_search_ever_ran():
    answer = BASE_ANSWER.model_copy(update={"citations": [
        Citation(title="Made Up Report", source_type="report"),
    ]})
    result = graph_module.validate_citations(answer, messages=[])
    assert result.citations == []


def test_validate_citations_matches_by_url_when_title_differs_slightly():
    messages = [_tool_message([{"document_title": "FY25 Vision Zero Annual Report", "source_url": "https://x.gov/fy25.pdf"}])]
    answer = BASE_ANSWER.model_copy(update={"citations": [
        Citation(title="FY25 Report", source_type="report", url="https://x.gov/fy25.pdf"),
    ]})
    result = graph_module.validate_citations(answer, messages)
    assert len(result.citations) == 1


def test_validate_citations_ignores_non_list_tool_results():
    # e.g. query_analytics returns a dict, not a list - must not crash
    messages = [_tool_message({"columns": ["a"], "rows": [[1]], "row_count": 1})]
    answer = BASE_ANSWER.model_copy(update={"citations": [Citation(title="X", source_type="dataset")]})
    result = graph_module.validate_citations(answer, messages)
    assert result.citations == []  # a dataset citation with no matching source is still dropped
