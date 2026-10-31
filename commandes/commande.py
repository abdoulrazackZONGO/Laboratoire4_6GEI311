from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from modele.ticket import Ticket


class Commande(ABC):
    """Opération différée sur un ticket (patron Command)."""

    def __init__(self, cible: Ticket) -> None:
        self._cible: Ticket = cible

    @property
    def cible(self) -> Ticket:
        return self._cible

    @property
    @abstractmethod
    def libelle(self) -> str:
        """Libellé lisible de la commande."""

    @abstractmethod
    def executer(self) -> None:
        """Applique la commande à sa cible."""
