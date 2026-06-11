"""Interface plugável para provedores de LLM."""

from abc import ABC, abstractmethod

from kiro.domain.models import ArticleDraft, Cluster


class LLMProvider(ABC):
    @abstractmethod
    def generate_article(self, cluster: Cluster) -> ArticleDraft:
        """Gera um draft de artigo a partir de um cluster.

        Deve lançar LLMError/LLMResponseError em caso de falha.
        """
        ...
