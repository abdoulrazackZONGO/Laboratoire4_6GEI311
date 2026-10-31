from __future__ import annotations

from typing import TYPE_CHECKING

from etats.etat_ticket import EtatTicket
from modele.enums import Statut

if TYPE_CHECKING:
    from modele.ticket import Ticket


class EtatValidation(EtatTicket):
    """Travail soumis, en attente de la décision de l'administrateur."""

    @property
    def nom(self) -> Statut:
        return Statut.VALIDATION

    @property
    def transitionsPermises(self) -> frozenset[Statut]:
        return frozenset({Statut.ASSIGNE, Statut.TERMINE})

    def gererTransition(self, ticket: Ticket, nouveau_statut: Statut) -> None:
        """Transitions autorisées : ASSIGNE (rejet), TERMINE."""
        # Imports locaux : les états se référencent mutuellement.
        from etats.etat_assigne import EtatAssigne
        from etats.etat_termine import EtatTermine

        if nouveau_statut is Statut.ASSIGNE:
            # Rejet de la validation.
            ticket.setEtat(EtatAssigne())
        elif nouveau_statut is Statut.TERMINE:
            ticket.setEtat(EtatTermine())
        else:
            super().gererTransition(ticket, nouveau_statut)
