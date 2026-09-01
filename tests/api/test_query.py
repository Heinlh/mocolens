"""Tests for query_service.py and POST /api/query. The agent itself
(graph.run) is mocked throughout - these test the reshaping and the HTTP
layer, not the LLM. Live agent behavior is already covered by
tests/agent/test_graph.py (fake-LLM) plus the real live runs documented in
PROJECT_STATUS.txt; this suite would otherwise need real Azure OpenAI
credentials and cost real tokens on every run.
"""
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from mocolens.agent.schemas import AgentAnswer, Citation
from mocolens.api import query_service, schemas
from mocolens.api.main import app, limiter

client = TestClient(app)


@pytest.fixture(autouse=True)
def _isolate_rate_limiter():
    """`limiter` is a module-level singleton with in-memory state that
    persists for the life of the test process, not per-test - without this,
    the dedicated rate-limit tests below (which make 10+ rapid calls on
    purpose) would burn through every other test's quota for the rest of
    the pytest run, in this file and any other that imports the same app.
    Disabled by default; the rate-limit tests turn it on for themselves.
    """
    limiter.enabled = False
    limiter.reset()
    yield
    limiter.enabled = False
    limiter.reset()


def _viz_tool_message(**overrides) -> ToolMessage:
    payload = {"id": "viz-1", "type": "line", "title": "Crashes over time", "data": {"points": []}, "error": None}
    payload.update(overrides)
    return ToolMessage(content=json.dumps(payload), tool_call_id="x")


BASE_ANSWER = AgentAnswer(
    answer="Yes.", summary="Crashes rose.", what_data_means="More crashes happened.",
    county_report_points=["The county is doing X."],
    caveats=["Counts, not rates."],
    citations=[Citation(title="FY25 Report", source_type="report", url="https://x.gov/r.pdf", page="3")],
    follow_up_prompts=["What about cyclists?"],
)


# --- query_service internals ---

def test_extract_visualizations_picks_up_successful_specs():
    messages = [HumanMessage(content="hi"), _viz_tool_message()]
    specs = query_service._extract_visualizations(messages)
    assert len(specs) == 1
    assert specs[0].id == "viz-1"
    assert specs[0].type == "line"


def test_extract_visualizations_skips_errored_specs():
    messages = [_viz_tool_message(error="no rows to visualize")]
    assert query_service._extract_visualizations(messages) == []


def test_extract_visualizations_ignores_non_viz_tool_results():
    messages = [ToolMessage(content=json.dumps({"columns": ["a"], "rows": [[1]]}), tool_call_id="x")]
    assert query_service._extract_visualizations(messages) == []


def test_extract_visualizations_ignores_ai_messages():
    messages = [AIMessage(content="thinking...")]
    assert query_service._extract_visualizations(messages) == []


def test_to_response_maps_agent_answer_fields():
    resp = query_service._to_response("a question?", BASE_ANSWER, [])
    assert resp.question == "a question?"
    assert resp.answer == "Yes."
    assert resp.what_data_means == "More crashes happened."
    assert resp.county_report_points == ["The county is doing X."]
    assert resp.limitations == ["Counts, not rates."]  # caveats -> limitations
    assert resp.follow_up_prompts == ["What about cyclists?"]


def test_to_response_assigns_citation_ids():
    resp = query_service._to_response("q", BASE_ANSWER, [])
    assert resp.citations[0].id == "cite-0"
    assert resp.citations[0].title == "FY25 Report"
    assert resp.citations[0].source_type == "report"


def test_to_response_includes_visualizations_from_messages():
    resp = query_service._to_response("q", BASE_ANSWER, [_viz_tool_message()])
    assert len(resp.visualizations) == 1


def test_ask_calls_agent_graph_run_and_reshapes(monkeypatch):
    def fake_run(question, llm=None):
        return {"final": BASE_ANSWER, "messages": []}

    monkeypatch.setattr(query_service.agent_graph, "run", fake_run)
    resp = query_service.ask("a real question")
    assert resp.answer == "Yes."
    assert resp.question == "a real question"


# --- POST /api/query ---

@patch("mocolens.api.main.query_service.ask")
def test_query_endpoint_happy_path(mock_ask):
    from mocolens.api import schemas
    mock_ask.return_value = schemas.QueryResponse(
        id="q1", question="test?", answer="Yes.", summary="s", what_data_means="m",
    )
    r = client.post("/api/query", json={"question": "test?"})
    assert r.status_code == 200
    data = r.json()
    assert data["answer"] == "Yes."
    assert data["whatDataMeans"] == "m"  # camelCase


def test_query_endpoint_empty_question_rejected():
    r = client.post("/api/query", json={"question": "   "})
    assert r.status_code == 400


def test_query_endpoint_missing_question_field_rejected():
    r = client.post("/api/query", json={})
    assert r.status_code == 422  # FastAPI/pydantic validation


@patch("mocolens.api.main.query_service.ask")
def test_query_endpoint_missing_credentials_returns_503_not_500(mock_ask):
    mock_ask.side_effect = RuntimeError("Missing Azure OpenAI credentials: AZURE_OPENAI_API_KEY")
    r = client.post("/api/query", json={"question": "test?"})
    assert r.status_code == 503
    assert "AZURE_OPENAI_API_KEY" in r.json()["detail"]


@patch("mocolens.api.main.query_service.ask")
def test_query_endpoint_unexpected_error_returns_generic_500_not_internals(mock_ask):
    mock_ask.side_effect = ValueError("some SQL detail: SELECT secret_column FROM x")
    r = client.post("/api/query", json={"question": "test?"})
    assert r.status_code == 500
    assert "secret_column" not in r.json()["detail"]
    assert "SELECT" not in r.json()["detail"]


# --- rate limiting (main.py: 10/minute on POST /api/query) ---

def test_query_endpoint_allows_up_to_the_configured_limit():
    limiter.enabled = True
    with patch("mocolens.api.main.query_service.ask") as mock_ask:
        mock_ask.return_value = schemas.QueryResponse(
            id="q", question="q", answer="a", summary="s", what_data_means="m",
        )
        statuses = [client.post("/api/query", json={"question": "test"}).status_code for _ in range(10)]
    assert statuses == [200] * 10


def test_query_endpoint_rejects_the_11th_request_in_the_same_minute():
    limiter.enabled = True
    with patch("mocolens.api.main.query_service.ask") as mock_ask:
        mock_ask.return_value = schemas.QueryResponse(
            id="q", question="q", answer="a", summary="s", what_data_means="m",
        )
        for _ in range(10):
            assert client.post("/api/query", json={"question": "test"}).status_code == 200
        eleventh = client.post("/api/query", json={"question": "test"})
    assert eleventh.status_code == 429


def test_query_endpoint_rate_limit_does_not_call_the_agent():
    # A rejected-by-rate-limit request must never reach the (real, billed)
    # agent - that's the entire point of the limit existing.
    limiter.enabled = True
    with patch("mocolens.api.main.query_service.ask") as mock_ask:
        mock_ask.return_value = schemas.QueryResponse(
            id="q", question="q", answer="a", summary="s", what_data_means="m",
        )
        for _ in range(10):
            client.post("/api/query", json={"question": "test"})
        calls_before = mock_ask.call_count
        client.post("/api/query", json={"question": "test"})
        assert mock_ask.call_count == calls_before  # the 11th call never invoked the agent


def test_dashboard_endpoint_rate_limit_does_not_trip_under_normal_filter_clicking():
    # 60/minute on the dashboard endpoint exists to stop scripted abuse, not
    # to constrain a person clicking through 4 filters - a handful of rapid
    # requests (e.g. changing every filter dropdown in quick succession)
    # must never 429.
    limiter.enabled = True
    with patch("mocolens.api.dashboard_service.get_dashboard_summary") as mock_dashboard:
        mock_dashboard.return_value = schemas.DashboardResponse(
            metrics=[], crash_trend=[], severity_breakdown=[], road_user_breakdown=[], hotspots=[], insights=[],
        )
        statuses = [client.get("/api/dashboard/summary").status_code for _ in range(8)]
    assert statuses == [200] * 8
