from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROVIDER_DEFAULT_MODEL: dict[str, str] = {
    "gemini": "gemini-2.5-flash",
    "anthropic": "claude-sonnet-4-20250514",
}
_PROVIDER_DEFAULT_BASE_URL: dict[str, str] = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta",
    "anthropic": "https://api.anthropic.com/v1",
}

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_ENV_FILE = _PROJECT_ROOT / ".env.customer_health"
_LEGACY_ENV_FILE = _PROJECT_ROOT / ".env"


class RelationshipSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(_DEFAULT_ENV_FILE), str(_LEGACY_ENV_FILE)),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    jira_base_url: str = Field(validation_alias="JIRA_BASE_URL")
    jira_user_email: str = Field(validation_alias="JIRA_USER_EMAIL")
    jira_api_token: SecretStr = Field(validation_alias="JIRA_API_TOKEN")
    jira_project_key: str = Field(validation_alias="JIRA_PROJECT_KEY")
    jira_timeout_seconds: int = Field(default=30, ge=1, validation_alias="JIRA_TIMEOUT_SECONDS")
    jira_page_size: int = Field(default=100, ge=1, le=100, validation_alias="JIRA_PAGE_SIZE")

    llm_provider: Literal["gemini", "anthropic"] = Field(default="gemini", validation_alias="LLM_PROVIDER")
    llm_api_key: SecretStr = Field(validation_alias="LLM_API_KEY")
    llm_model: str = Field(default="", validation_alias="LLM_MODEL")
    llm_base_url: str = Field(default="", validation_alias="LLM_BASE_URL")
    llm_timeout_seconds: int = Field(default=60, ge=1, validation_alias="LLM_TIMEOUT_SECONDS")
    llm_temperature: float = Field(default=0.2, ge=0.0, le=2.0, validation_alias="LLM_TEMPERATURE")

    # 0 = sem limite temporal (analisa histórico completo)
    lookback_days: int = Field(default=0, ge=0, validation_alias="REL_LOOKBACK_DAYS")
    lookback_months: int = Field(default=0, ge=0, validation_alias="REL_LOOKBACK_MONTHS")
    all_history: bool = Field(default=True, validation_alias="REL_ALL_HISTORY")
    ticket_limit: int = Field(default=40, ge=5, le=200, validation_alias="REL_TICKET_LIMIT")
    customer_jql_template: str = Field(
        default=(
            'project = "{project_key}" '
            'AND text ~ "\\"{customer_name}\\"" '
            '{time_clause}'
            "ORDER BY updated DESC"
        ),
        validation_alias="REL_CUSTOMER_JQL_TEMPLATE",
    )
    output_dir: Path = Field(default=Path("output/customer_relationship"), validation_alias="REL_OUTPUT_DIR")

    @model_validator(mode="after")
    def _apply_provider_defaults(self) -> "RelationshipSettings":
        if not self.llm_model:
            self.llm_model = _PROVIDER_DEFAULT_MODEL[self.llm_provider]
        if not self.llm_base_url:
            self.llm_base_url = _PROVIDER_DEFAULT_BASE_URL[self.llm_provider]
        return self
