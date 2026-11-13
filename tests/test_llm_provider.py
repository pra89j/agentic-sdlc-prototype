import pytest

from agent_engine.nodes import _get_llm
from agent_engine.schemas import EngineeringSpec


def test_gemini_provider_uses_configured_model_and_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.8-flash")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    llm = _get_llm()
    structured_llm = llm.with_structured_output(EngineeringSpec)

    assert llm.model == "gemini-3.8-flash"
    assert structured_llm is not None


def test_gemini_provider_requires_api_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="no GEMINI_API_KEY or GOOGLE_API_KEY"):
        _get_llm()


def test_unknown_llm_provider_is_rejected(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "unknown")

    with pytest.raises(ValueError, match="Unsupported LLM_PROVIDER"):
        _get_llm()
