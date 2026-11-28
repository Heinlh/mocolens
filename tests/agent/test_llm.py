import pytest
from langchain_core.messages import HumanMessage

from mocolens.agent import llm as llm_module


def test_missing_credentials_raises_clear_error(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    with pytest.raises(RuntimeError, match="AZURE_OPENAI_API_KEY.*AZURE_OPENAI_ENDPOINT"):
        llm_module.get_llm()


def test_partial_credentials_names_only_whats_missing(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "fake-key")
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    with pytest.raises(RuntimeError) as exc_info:
        llm_module.get_llm()
    assert "AZURE_OPENAI_API_KEY" not in str(exc_info.value)
    assert "AZURE_OPENAI_ENDPOINT" in str(exc_info.value)


def test_whitespace_only_credential_counts_as_missing(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "   ")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    with pytest.raises(RuntimeError, match="AZURE_OPENAI_API_KEY"):
        llm_module.get_llm()


def _client(monkeypatch, endpoint="https://example.openai.azure.com/", **env):
    """A real client (no network call is made) built from the given settings."""
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", env.pop("key", "fake-key"))
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", endpoint)
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT", raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return llm_module.get_llm()


def _payload(client) -> dict:
    return client._get_request_payload([HumanMessage(content="hi")])


def test_surrounding_whitespace_is_stripped_before_use(monkeypatch):
    client = _client(monkeypatch, endpoint=" https://example.openai.azure.com/ ", key="  real-key  ")
    assert client.openai_api_key.get_secret_value() == "real-key"
    assert str(client.root_client.base_url) == "https://example.openai.azure.com/openai/v1/"


@pytest.mark.parametrize("endpoint", [
    "https://mocolens-res.openai.azure.com/",
    "https://mocolens-res.openai.azure.com",
    # How Foundry's Overview page shows it - this form caused the 404.
    "https://mocolens-res.openai.azure.com/openai/v1/",
    "https://mocolens-res.openai.azure.com/openai/deployments/gpt-5.4-mini/chat/completions?api-version=2025-04-01-preview",
    "https://mocolens-res.cognitiveservices.azure.com/",
    "https://mocolens-res.services.ai.azure.com/",
    "https://mocolens-res.services.ai.azure.com/api/projects/mocolens",
    "mocolens-res.openai.azure.com",
    "https://MOCOLENS-RES.openai.azure.com/",
])
def test_every_endpoint_form_resolves_to_the_v1_url(monkeypatch, endpoint):
    """A doubled path (.../openai/v1/openai/deployments/...) is a bare 404."""
    client = _client(monkeypatch, endpoint=endpoint)
    assert str(client.root_client.base_url) == "https://mocolens-res.openai.azure.com/openai/v1/"


def test_reasoning_deployment_sends_reasoning_effort_not_temperature(monkeypatch):
    """gpt-5 models reject a non-default temperature and max_tokens."""
    payload = _payload(_client(monkeypatch))
    assert payload["model"] == "gpt-5.4-mini"
    assert payload["reasoning_effort"] == "low"
    assert payload["max_completion_tokens"] == 4000
    assert "temperature" not in payload and "max_tokens" not in payload


def test_requests_use_chat_completions_not_responses(monkeypatch):
    client = _client(monkeypatch)
    assert client._use_responses_api(_payload(client)) is False
    assert "messages" in _payload(client)


def test_deployment_can_be_overridden_for_a_rollback(monkeypatch):
    payload = _payload(_client(monkeypatch, AZURE_OPENAI_DEPLOYMENT="gpt-4.1-mini"))
    assert payload["model"] == "gpt-4.1-mini"
    assert payload["temperature"] == 0.1
    assert "reasoning_effort" not in payload


def test_forced_final_answer_tool_is_sent_as_a_named_function(monkeypatch):
    """graph.py's streaming finalizer forces the AgentAnswer tool."""
    from mocolens.agent.schemas import AgentAnswer
    client = _client(monkeypatch)
    bound = client.bind_tools([AgentAnswer], tool_choice="AgentAnswer", parallel_tool_calls=False)
    payload = client._get_request_payload([HumanMessage(content="hi")], **bound.kwargs)
    assert payload["tool_choice"] == {"type": "function", "function": {"name": "AgentAnswer"}}
    assert payload["parallel_tool_calls"] is False
