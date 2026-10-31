from __future__ import annotations

from etats.etat_ticket import EtatTicket
from modele.enums import Statut


class EtatTermine(EtatTicket):
    """État terminal : travail validé, aucune transition possible."""

    @property
    def nom(self) -> Statut:
        return Statut.TERMINE
