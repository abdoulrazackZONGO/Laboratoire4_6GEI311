from __future__ import annotations

from typing import TYPE_CHECKING

from commandes.commande_assigner import CommandeAssigner
from commandes.commande_desassigner import CommandeDesassigner
from commandes.commande_fermer import CommandeFermer
from commandes.commande_valider import CommandeValider
from sessions.session_operations import SessionOperations

if TYPE_CHECKING:
    from acteurs.admin import Admin
    from acteurs.user import User
    from modele.systeme_tickets import SystemeTickets
    from modele.ticket import Ticket


class LotAdmin(SessionOperations):
    """Lot d'opérations administrateur : ni pause, ni reprise, ni annulation."""

    # Restreint le type du propriétaire hérité : un lot appartient toujours à un Admin.
    _proprietaire: Admin

    def __init__(self, proprietaire: Admin, systeme: SystemeTickets) -> None:
        super().__init__(proprietaire, systeme)

    @property
    def libelle(self) -> str:
        return "Lot administrateur"

    def assigner(self, ticket: Ticket, user: User) -> None:
        self._ajouter(CommandeAssigner(self._proprietaire, ticket, user))

    def desassigner(self, ticket: Ticket) -> None:
        self._ajouter(CommandeDesassigner(self._proprietaire, ticket))

    def validerTicket(self, ticket: Ticket) -> None:
        self._ajouter(CommandeValider(self._proprietaire, ticket))

    def fermer(self, ticket: Ticket) -> None:
        self._ajouter(CommandeFermer(self._proprietaire, ticket))
