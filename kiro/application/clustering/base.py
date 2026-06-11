"""Interface plugável para estratégias de clusterização."""

from abc import ABC, abstractmethod

from kiro.domain.models import Cluster, Ticket


class ClusteringStrategy(ABC):
    @abstractmethod
    def cluster(self, tickets: list[Ticket]) -> list[Cluster]:
        """Agrupa tickets em clusters temáticos."""
        ...
