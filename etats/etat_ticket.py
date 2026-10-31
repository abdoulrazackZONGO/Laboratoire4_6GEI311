from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from modele.exceptions import TransitionInvalideException

if TYPE_CHECKING:
    from modele.enums import Statut
    from modele.ticket import Ticket


class EtatTicket(ABC):
    """État abstrait d'un ticket (patron State)."""

    @property
    @abstractmethod
    def nom(self) -> Statut:
        """Statut correspondant à cet état."""

    @property
    def transitionsPermises(self) -> frozenset[Statut]:
        """Statuts vers lesquels cet état accepte de passer.

        Par défaut : aucun, ce qui convient aux états terminaux (TERMINE, FERME).
        Chaque état concret qui accepte des transitions redéfinit cette propriété,
        en cohérence avec gererTransition() (vérifié par tests/test_etats.py).
        """
        return frozenset()

    def transitionPossible(self, nouveau_statut: Statut) -> bool:
        """Indique, sans rien modifier, si la transition serait acceptée."""
        return nouveau_statut in self.transitionsPermises

    def gererTransition(self, ticket: Ticket, nouveau_statut: Statut) -> None:
        """Comportement par défaut : toute transition est refusée."""
        raise TransitionInvalideException(self.nom, nouveau_statut)
