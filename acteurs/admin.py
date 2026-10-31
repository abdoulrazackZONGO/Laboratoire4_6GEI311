from __future__ import annotations

from typing import TYPE_CHECKING

from acteurs.utilisateur_systeme import UtilisateurSysteme
from modele.enums import Statut
from sessions.lot_admin import LotAdmin

if TYPE_CHECKING:
    from acteurs.user import User
    from modele.ticket import Ticket


class Admin(UtilisateurSysteme):
    """Administrateur : pilote le cycle de vie des tickets.

    Chaque opération demande la transition d'abord, puis modifie la donnée :
    un refus de transition laisse ainsi le ticket intact.
    """

    @property
    def role(self) -> str:
        return "Admin"

    def assignTicket(self, ticket: Ticket, user: User) -> None:
        """Assignation, réassignation ou rejet de validation."""
        ticket.updateStatus(Statut.ASSIGNE)
        ticket.assignTo(user)

    def desassignerTicket(self, ticket: Ticket) -> None:
        ticket.updateStatus(Statut.OUVERT)
        ticket.retirerAssignation()

    def validerTicket(self, ticket: Ticket) -> None:
        ticket.updateStatus(Statut.TERMINE)

    def closeTicket(self, ticket: Ticket) -> None:
        """L'assigné éventuel est conservé pour la traçabilité."""
        ticket.updateStatus(Statut.FERME)

    def viewAllTickets(self) -> list[Ticket]:
        """MÉTHODE D'AFFICHAGE : une ligne par ticket du dépôt ; retourne la liste."""
        tickets = self._systeme.tickets
        for ticket in tickets:
            createur = ticket.creator.name if ticket.creator is not None else "aucun"
            assigne = ticket.assignedUser.name if ticket.assignedUser is not None else "aucun"
            print(
                f"  #{ticket.ticketID:<2} {ticket.title:<28} {ticket.status.name:<10}"
                f" créateur : {createur:<14} assigné : {assigne:<11}"
                f" commentaires : {len(ticket.comments)}"
            )
        return tickets

    def ouvrirLot(self) -> LotAdmin:
        return LotAdmin(self, self._systeme)
