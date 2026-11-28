import pytest

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


def test_surrounding_whitespace_is_stripped_before_use(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "  real-key  ")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", " https://example.openai.azure.com/ ")
    captured = {}

    class FakeAzureChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(llm_module, "AzureChatOpenAI", FakeAzureChatOpenAI)
    llm_module.get_llm()
    assert captured["api_key"] == "real-key"
    assert captured["azure_endpoint"] == "https://example.openai.azure.com/"
    assert captured["azure_deployment"] == llm_module.DEPLOYMENT
    assert captured["api_version"] == llm_module.API_VERSION


def _captured_kwargs(monkeypatch, **env):
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "fake-key")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_VERSION", raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    captured = {}

    class FakeAzureChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(llm_module, "AzureChatOpenAI", FakeAzureChatOpenAI)
    llm_module.get_llm()
    return captured


def test_reasoning_deployment_sends_reasoning_effort_not_temperature(monkeypatch):
    """gpt-5 models reject a non-default temperature."""
    captured = _captured_kwargs(monkeypatch)
    assert captured["azure_deployment"] == "gpt-5.4-mini"
    assert captured["reasoning_effort"] == "low"
    assert "temperature" not in captured


def test_deployment_and_api_version_can_be_overridden_for_a_rollback(monkeypatch):
    captured = _captured_kwargs(
        monkeypatch, AZURE_OPENAI_DEPLOYMENT="gpt-4.1-mini", AZURE_OPENAI_API_VERSION="2025-01-01-preview",
    )
    assert captured["azure_deployment"] == "gpt-4.1-mini"
    assert captured["api_version"] == "2025-01-01-preview"
    assert captured["temperature"] == 0.1
    assert "reasoning_effort" not in captured


def test_foundry_project_endpoint_is_rejected_with_a_clear_message(monkeypatch):
    """The project endpoint cannot serve Chat Completions; fail early and say why."""
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "fake-key")
    monkeypatch.setenv(
        "AZURE_OPENAI_ENDPOINT", "https://mocolens.services.ai.azure.com/api/projects/mocolens",
    )
    with pytest.raises(RuntimeError, match="openai.azure.com"):
        llm_module.get_llm()
