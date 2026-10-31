from __future__ import annotations

from typing import TYPE_CHECKING

from etats.etat_ticket import EtatTicket
from modele.enums import Statut

if TYPE_CHECKING:
    from modele.ticket import Ticket


class EtatAssigne(EtatTicket):
    """Ticket confié à un utilisateur."""

    @property
    def nom(self) -> Statut:
        return Statut.ASSIGNE

    @property
    def transitionsPermises(self) -> frozenset[Statut]:
        return frozenset({Statut.ASSIGNE, Statut.OUVERT, Statut.VALIDATION, Statut.FERME})

    def gererTransition(self, ticket: Ticket, nouveau_statut: Statut) -> None:
        """Transitions autorisées : ASSIGNE, OUVERT, VALIDATION, FERME."""
        # Imports locaux : les états se référencent mutuellement.
        from etats.etat_ferme import EtatFerme
        from etats.etat_ouvert import EtatOuvert
        from etats.etat_validation import EtatValidation

        if nouveau_statut is Statut.ASSIGNE:
            # Réassignation : nouvelle instance du même état.
            ticket.setEtat(EtatAssigne())
        elif nouveau_statut is Statut.OUVERT:
            # Désassignation.
            ticket.setEtat(EtatOuvert())
        elif nouveau_statut is Statut.VALIDATION:
            ticket.setEtat(EtatValidation())
        elif nouveau_statut is Statut.FERME:
            ticket.setEtat(EtatFerme())
        else:
            super().gererTransition(ticket, nouveau_statut)
