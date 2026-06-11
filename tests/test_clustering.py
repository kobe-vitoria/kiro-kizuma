from kiro.application.clustering.heuristic import HeuristicClusteringStrategy
from kiro.domain.models import Ticket


def _t(key: str, summary: str, description: str = "") -> Ticket:
    return Ticket(key=key, summary=summary, description=description)


def test_returns_empty_for_no_tickets():
    assert HeuristicClusteringStrategy().cluster([]) == []


def test_groups_similar_tickets():
    tickets = [
        _t("A-1", "Erro ao fazer login no aplicativo móvel"),
        _t("A-2", "Não consigo fazer login no aplicativo móvel"),
        _t("A-3", "Login bloqueado no aplicativo móvel"),
        _t("A-4", "Login no aplicativo móvel falhando sempre"),
        _t("B-1", "Relatório exporta com colunas faltando"),
        _t("B-2", "Bug no exportador de relatórios"),
    ]
    strategy = HeuristicClusteringStrategy(min_cluster_size=3, overlap_threshold=2)
    clusters = strategy.cluster(tickets)
    assert len(clusters) >= 1
    login = next((c for c in clusters if "login" in c.topic.lower()), None)
    assert login is not None
    assert login.count >= 3


def test_respects_min_cluster_size():
    tickets = [
        _t("A-1", "Erro singular único raro"),
        _t("B-1", "Outro problema isolado distinto"),
    ]
    assert HeuristicClusteringStrategy(min_cluster_size=3).cluster(tickets) == []


def test_returns_only_top_n():
    tickets = []
    for cat in ("login", "relatorio", "pagamento", "exportar"):
        for i in range(4):
            tickets.append(
                _t(
                    f"{cat}-{i}",
                    f"problema recorrente {cat} usuário falha repete sempre",
                )
            )
    strategy = HeuristicClusteringStrategy(
        min_cluster_size=3, top_n=2, overlap_threshold=2
    )
    clusters = strategy.cluster(tickets)
    assert len(clusters) <= 2
