from __future__ import annotations

from typing import TYPE_CHECKING

from commandes.commande import Commande

if TYPE_CHECKING:
    from acteurs.admin import Admin
    from acteurs.user import User
    from modele.ticket import Ticket


class CommandeAssigner(Commande):
    """Délègue l'assignation à Admin.assignTicket()."""

    def __init__(self, admin: Admin, cible: Ticket, user: User) -> None:
        super().__init__(cible)
        self._admin: Admin = admin
        self._user: User = user

    @property
    def libelle(self) -> str:
        return f"Assigner le ticket #{self.cible.ticketID} à {self._user.name}"

    def executer(self) -> None:
        self._admin.assignTicket(self.cible, self._user)
