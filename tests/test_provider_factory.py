"""Testes da fábrica de LLMProvider — seleção por settings e dry-run."""

from kiro.application.generation.anthropic_provider import AnthropicProvider
from kiro.application.generation.factory import build_llm_provider
from kiro.application.generation.gemini_provider import GeminiProvider
from kiro.application.generation.mock_provider import MockLLMProvider
from kiro.config.settings import Settings


def _set_required(monkeypatch):
    monkeypatch.setenv("JIRA_BASE_URL", "https://x.atlassian.net")
    monkeypatch.setenv("JIRA_USER_EMAIL", "u@x.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "tok")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "PROJ")
    monkeypatch.setenv("LLM_API_KEY", "fake-key")


def test_builds_gemini_when_provider_is_gemini(monkeypatch):
    _set_required(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    settings = Settings(_env_file=None)
    provider = build_llm_provider(settings, dry_run=False)
    assert isinstance(provider, GeminiProvider)


def test_builds_anthropic_when_provider_is_anthropic(monkeypatch):
    _set_required(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    settings = Settings(_env_file=None)
    provider = build_llm_provider(settings, dry_run=False)
    assert isinstance(provider, AnthropicProvider)


def test_returns_mock_when_dry_run(monkeypatch):
    """Em dry-run, factory devolve MockLLMProvider mesmo com provider real configurado."""
    _set_required(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    settings = Settings(_env_file=None)
    provider = build_llm_provider(settings, dry_run=True)
    assert isinstance(provider, MockLLMProvider)
