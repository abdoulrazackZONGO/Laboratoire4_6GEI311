from __future__ import annotations

from etats.etat_ticket import EtatTicket
from modele.enums import Statut


class EtatFerme(EtatTicket):
    """État terminal : ticket fermé, aucune transition possible."""

    @property
    def nom(self) -> Statut:
        return Statut.FERME
