from collections import Counter
from dataclasses import dataclass

from customer_health.jira_client import CustomerTicket

_NEGATIVE_TERMS = {
    "falha": 3,
    "erro": 3,
    "indispon": 3,
    "instabilidade": 3,
    "urgente": 2,
    "crit": 3,
    "reclama": 2,
    "insatisfa": 2,
    "demora": 1,
    "lento": 1,
    "impacto": 2,
}

_POSITIVE_TERMS = {
    "resolvido": 2,
    "obrigad": 1,
    "normalizou": 2,
    "ok": 1,
}

_HIGH_PRIORITY_MARKERS = {"highest", "high", "alta", "urgent", "crítica"}


@dataclass(frozen=True)
class RelationshipTemperature:
    score: int
    level: str
    quality_status: str
    ticket_count: int
    high_priority_count: int
    done_like_count: int
    negative_hits: int
    positive_hits: int
    sla_targets_total: int
    sla_targets_breached: int
    top_signals: list[str]


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def compute_relationship_temperature(tickets: list[CustomerTicket]) -> RelationshipTemperature:
    if not tickets:
        return RelationshipTemperature(
            score=0,
            level="Sem dados",
            quality_status="Não foi possível avaliar",
            ticket_count=0,
            high_priority_count=0,
            done_like_count=0,
            negative_hits=0,
            positive_hits=0,
            sla_targets_total=0,
            sla_targets_breached=0,
            top_signals=[],
        )

    negative_hits = 0
    positive_hits = 0
    top_counter: Counter[str] = Counter()
    high_priority_count = 0
    done_like_count = 0
    sla_targets_total = 0
    sla_targets_breached = 0

    for ticket in tickets:
        combined = _normalize(f"{ticket.summary} {ticket.description}")

        for token, weight in _NEGATIVE_TERMS.items():
            if token in combined:
                negative_hits += weight
                top_counter[token] += 1

        for token, weight in _POSITIVE_TERMS.items():
            if token in combined:
                positive_hits += weight

        status_l = ticket.status.lower()
        if any(s in status_l for s in ("fechado", "resolvido", "done", "conclu")):
            done_like_count += 1

        priority_l = ticket.priority.lower()
        if any(marker in priority_l for marker in _HIGH_PRIORITY_MARKERS):
            high_priority_count += 1

        sla_targets_total += ticket.sla_targets_total
        sla_targets_breached += ticket.sla_targets_breached

    # Score de tensão: maior = relação sob maior pressão.
    ticket_count = len(tickets)
    backlog_factor = max(ticket_count - done_like_count, 0)
    raw = (
        (negative_hits * 2)
        + (high_priority_count * 3)
        + backlog_factor
        + (sla_targets_breached * 4)
        - positive_hits
    )
    score = max(0, min(100, raw))

    if score >= 70:
        level = "Crítica"
        quality = "Relação em risco"
    elif score >= 45:
        level = "Alta"
        quality = "Relação requer atenção"
    elif score >= 20:
        level = "Moderada"
        quality = "Relação estável com pontos de atenção"
    else:
        level = "Baixa"
        quality = "Relação saudável"

    top_signals = [item for item, _ in top_counter.most_common(5)]

    return RelationshipTemperature(
        score=score,
        level=level,
        quality_status=quality,
        ticket_count=ticket_count,
        high_priority_count=high_priority_count,
        done_like_count=done_like_count,
        negative_hits=negative_hits,
        positive_hits=positive_hits,
        sla_targets_total=sla_targets_total,
        sla_targets_breached=sla_targets_breached,
        top_signals=top_signals,
    )
