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
