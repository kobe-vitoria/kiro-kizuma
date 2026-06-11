"""Modelos de domínio. Imutáveis sempre que possível."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class Ticket(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    summary: str
    description: str = ""
    labels: list[str] = Field(default_factory=list)
    components: list[str] = Field(default_factory=list)
    status: Optional[str] = None
    resolved_at: Optional[datetime] = None

    @property
    def text(self) -> str:
        return f"{self.summary} {self.description}".strip()


class Cluster(BaseModel):
    topic: str
    tickets: list[str]
    summaries: list[str]
    labels: list[str] = Field(default_factory=list)
    components: list[str] = Field(default_factory=list)
    # Excerto da `description` dos top N tickets (key prefixado) — dá ao LLM
    # contexto narrativo dos casos reais, não só os títulos curtos.
    sample_descriptions: list[str] = Field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.tickets)


class FAQItem(BaseModel):
    question: str = Field(..., min_length=1)
    answer: str = Field(..., min_length=1)


class ArticleDraft(BaseModel):
    """Schema validado da resposta do LLM."""

    title: str = Field(..., min_length=1)
    problem: str = Field(..., min_length=1)
    cause: str = Field(..., min_length=1)
    solution: str = Field(..., min_length=1)
    faq: list[FAQItem] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class PublishResult(BaseModel):
    cluster_topic: str
    article_title: str
    ticket_count: int
    confluence_url: Optional[str] = None
    local_path: Optional[str] = None
    error: Optional[str] = None

    @property
    def succeeded(self) -> bool:
        return self.error is None
