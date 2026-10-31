from __future__ import annotations

from typing import TYPE_CHECKING

from etats.etat_ticket import EtatTicket
from modele.enums import Statut

if TYPE_CHECKING:
    from modele.ticket import Ticket


class EtatOuvert(EtatTicket):
    """Ticket créé, en attente d'assignation."""

    @property
    def nom(self) -> Statut:
        return Statut.OUVERT

    @property
    def transitionsPermises(self) -> frozenset[Statut]:
        return frozenset({Statut.ASSIGNE, Statut.FERME})

    def gererTransition(self, ticket: Ticket, nouveau_statut: Statut) -> None:
        """Transitions autorisées : ASSIGNE, FERME."""
        # Imports locaux : les états se référencent mutuellement.
        from etats.etat_assigne import EtatAssigne
        from etats.etat_ferme import EtatFerme

        if nouveau_statut is Statut.ASSIGNE:
            ticket.setEtat(EtatAssigne())
        elif nouveau_statut is Statut.FERME:
            ticket.setEtat(EtatFerme())
        else:
            super().gererTransition(ticket, nouveau_statut)
