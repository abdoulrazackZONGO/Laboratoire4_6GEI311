from __future__ import annotations

from typing import TYPE_CHECKING

from commandes.commande import Commande

if TYPE_CHECKING:
    from acteurs.admin import Admin
    from modele.ticket import Ticket


class CommandeFermer(Commande):
    """Délègue la fermeture à Admin.closeTicket()."""

    def __init__(self, admin: Admin, cible: Ticket) -> None:
        super().__init__(cible)
        self._admin: Admin = admin

    @property
    def libelle(self) -> str:
        return f"Fermer le ticket #{self.cible.ticketID}"

    def executer(self) -> None:
        self._admin.closeTicket(self.cible)
