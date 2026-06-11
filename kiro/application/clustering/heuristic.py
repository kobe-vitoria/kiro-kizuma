"""Estratégia heurística baseada em TF-DF + bigramas, com filtro de raridade.

Trocável por embeddings/HDBSCAN sem alterar o pipeline.
"""

import logging
from collections import Counter

from kiro.application.clustering.base import ClusteringStrategy
from kiro.application.normalization import tokenize
from kiro.domain.models import Cluster, Ticket

log = logging.getLogger(__name__)


class HeuristicClusteringStrategy(ClusteringStrategy):
    def __init__(
        self,
        min_cluster_size: int = 3,
        top_n: int = 10,
        overlap_threshold: int = 3,
        keyword_window: int = 15,
    ) -> None:
        self.min_cluster_size = min_cluster_size
        self.top_n = top_n
        self.overlap_threshold = overlap_threshold
        self.keyword_window = keyword_window

    def cluster(self, tickets: list[Ticket]) -> list[Cluster]:
        if not tickets:
            return []

        all_tokens = [tokenize(t.text) for t in tickets]

        df: Counter[str] = Counter()
        for tokens in all_tokens:
            for term in set(tokens):
                df[term] += 1

        # Em corpora pequenos um cluster legítimo pode ser >50% do total,
        # então só filtramos termos "universais" (em >70% dos tickets) e apenas
        # quando há ticket suficiente para a estatística fazer sentido.
        if len(tickets) >= 20:
            universal_ceiling = max(2, int(len(tickets) * 0.7))
            useful_terms = {term for term, count in df.items() if count <= universal_ceiling}
        else:
            useful_terms = set(df.keys())

        term_sets: list[set[str]] = []
        for tokens in all_tokens:
            top_terms = {t for t in tokens[: self.keyword_window] if t in useful_terms}
            bigrams = {
                f"{tokens[i]}_{tokens[i + 1]}"
                for i in range(len(tokens) - 1)
                if tokens[i] in useful_terms and tokens[i + 1] in useful_terms
            }
            term_sets.append(top_terms | bigrams)

        assigned: set[int] = set()
        clusters: list[Cluster] = []

        for i, anchor in enumerate(tickets):
            if i in assigned:
                continue
            anchor_terms = term_sets[i]
            if not anchor_terms:
                assigned.add(i)
                continue

            group_indices = [i]
            assigned.add(i)

            for j in range(i + 1, len(tickets)):
                if j in assigned:
                    continue
                if len(anchor_terms & term_sets[j]) >= self.overlap_threshold:
                    group_indices.append(j)
                    assigned.add(j)

            if len(group_indices) >= self.min_cluster_size:
                group = [tickets[k] for k in group_indices]
                rep = min(group, key=lambda t: len(t.summary) or 9_999)
                # Pega descrições dos 3 tickets com texto mais rico (descrição
                # mais longa) — dão ao LLM matéria-prima narrativa de qualidade.
                with_desc = [t for t in group if t.description and t.description.strip()]
                top_desc_tickets = sorted(
                    with_desc, key=lambda t: len(t.description), reverse=True
                )[:3]
                sample_descriptions = [
                    f"[{t.key}] {t.description.strip()[:500]}"
                    for t in top_desc_tickets
                ]
                cluster = Cluster(
                    topic=rep.summary or anchor.summary or "Tópico recorrente",
                    tickets=[t.key for t in group],
                    summaries=[t.summary for t in group[:5]],
                    labels=list({lbl for t in group for lbl in t.labels})[:8],
                    components=list({c for t in group for c in t.components})[:5],
                    sample_descriptions=sample_descriptions,
                )
                clusters.append(cluster)

        clusters.sort(key=lambda c: c.count, reverse=True)
        log.info(
            "clustering: %d clusters acima de min_size=%d, retornando top %d",
            len(clusters), self.min_cluster_size, self.top_n,
        )
        return clusters[: self.top_n]
