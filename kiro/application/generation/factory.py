"""Fábrica de LLMProvider — seleção por configuração."""

import logging

from kiro.application.generation.anthropic_provider import AnthropicProvider
from kiro.application.generation.base import LLMProvider
from kiro.application.generation.gemini_provider import GeminiProvider
from kiro.application.generation.mock_provider import MockLLMProvider
from kiro.config.settings import Settings
from kiro.domain.exceptions import ConfigError

log = logging.getLogger(__name__)


def build_llm_provider(settings: Settings, *, dry_run: bool = False) -> LLMProvider:
    """Retorna o LLMProvider correto com base em `settings.llm_provider`.

    Em modo `dry_run`, devolve um `MockLLMProvider` que NÃO chama nenhuma API real,
    independentemente do provedor configurado — garantia em runtime para demo
    e CI sem custo de tokens.
    """
    if dry_run:
        log.info("LLM provider: MOCK (dry-run)")
        return MockLLMProvider()

    provider = settings.llm_provider
    api_key = settings.llm_api_key.get_secret_value()
    common = {
        "api_key": api_key,
        "model": settings.llm_model,
        "base_url": settings.llm_base_url,
        "max_tokens": settings.llm_max_tokens,
        "temperature": settings.llm_temperature,
        "timeout_seconds": settings.llm_timeout_seconds,
    }

    if provider == "gemini":
        log.info("LLM provider: gemini (model=%s)", settings.llm_model)
        return GeminiProvider(**common)

    if provider == "anthropic":
        log.info("LLM provider: anthropic (model=%s)", settings.llm_model)
        return AnthropicProvider(**common)

    raise ConfigError(f"LLM_PROVIDER desconhecido: {provider!r}")
