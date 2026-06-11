"""Fixtures comuns. Limpa env de produção para isolar testes."""

import pytest


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch):
    """Garante que nenhum env real vaze para os testes."""
    for key in [
        "JIRA_BASE_URL", "JIRA_USER_EMAIL", "JIRA_API_TOKEN", "JIRA_PROJECT_KEY",
        "JIRA_EXTRA_JQL", "JIRA_CLOSED_STATUSES",
        "CONFLUENCE_BASE_URL", "CONFLUENCE_SPACE_KEY", "CONFLUENCE_PARENT_ID",
        "SLACK_WEBHOOK_URL",
        "LLM_API_KEY", "LLM_MODEL",
        "ENABLE_CONFLUENCE_PUBLISH", "ENABLE_SLACK_NOTIFY",
        "DRY_RUN", "LOOKBACK_DAYS",
    ]:
        monkeypatch.delenv(key, raising=False)
    yield
