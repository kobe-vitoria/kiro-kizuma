"""Mock provider — não chama API real. Usado em dry-run para demo sem custo."""

import logging

from kiro.application.generation.base import LLMProvider
from kiro.domain.models import ArticleDraft, Cluster, FAQItem

log = logging.getLogger(__name__)


class MockLLMProvider(LLMProvider):
    """Retorna drafts determinísticos baseados no próprio cluster.

    Nenhuma chamada externa. Garante que `--dry-run` não consuma quota da API real
    e que a demo local seja reprodutível e gratuita.
    """

    def generate_article(self, cluster: Cluster) -> ArticleDraft:
        log.info(
            "MOCK LLM: gerando draft local para cluster '%s' (%d tickets)",
            cluster.topic,
            cluster.count,
        )
        sample = cluster.summaries[0] if cluster.summaries else cluster.topic
        components = ", ".join(cluster.components) or "não identificados"
        tags = cluster.labels[:5] if cluster.labels else [cluster.topic.split()[0].lower() or "geral"]
        return ArticleDraft(
            title=f"[DRY-RUN] {cluster.topic}",
            problem=(
                f"Foram identificados {cluster.count} tickets recorrentes sobre "
                f"'{cluster.topic}'. Sintoma típico relatado: {sample}."
            ),
            cause=(
                "Causa preliminar não confirmada — artigo gerado em modo dry-run, "
                f"sem consulta ao LLM real. Componentes afetados: {components}."
            ),
            solution=(
                "1. Reproduzir o problema em ambiente controlado\n"
                "2. Identificar a causa raiz a partir dos logs e dos tickets de origem\n"
                "3. Aplicar correção e validar com os tickets associados\n"
                "4. Documentar o procedimento neste artigo e publicar"
            ),
            faq=[
                FAQItem(
                    question=f"Como reconhecer o problema relacionado a '{cluster.topic}'?",
                    answer=(
                        f"Os tickets de origem ({cluster.count} ao todo) reportam sintomas "
                        f"semelhantes a: {sample}."
                    ),
                ),
            ],
            tags=tags,
        )
