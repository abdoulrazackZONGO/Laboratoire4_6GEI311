"""Contrôleur de la liste Admin (F2) et du lot (F7) : sans tkinter, testable sans écran."""
from __future__ import annotations

from typing import TYPE_CHECKING

from modele.enums import Statut

if TYPE_CHECKING:
    from acteurs.admin import Admin
    from acteurs.user import User
    from ihm.controleurs.controleur_principal import ControleurPrincipal
    from modele.ticket import Ticket
    from sessions.lot_admin import LotAdmin

# Chaque action de l'Admin et le statut qu'elle demande à l'état du ticket.
# assigner couvre l'assignation, la réassignation et le rejet d'une validation.
STATUTS_DES_ACTIONS: dict[str, Statut] = {
    "assigner": Statut.ASSIGNE,
    "desassigner": Statut.OUVERT,
    "valider": Statut.TERMINE,
    "fermer": Statut.FERME,
}


class ControleurAdmin:
    """Toute modification passe par Admin et LotAdmin, jamais directement par le ticket.

    La vue F2 lit les tickets ici ; elle trouve le dépôt, ouvrirDetail() et
    ouvrirLot() dans principal. Un lot n'est appliqué que par appliquerLot().
    """

    def __init__(self, principal: ControleurPrincipal, admin: Admin) -> None:
        self._principal: ControleurPrincipal = principal
        self._admin: Admin = admin

    @property
    def principal(self) -> ControleurPrincipal:
        return self._principal

    @property
    def admin(self) -> Admin:
        return self._admin

    def tickets(self, statut: Statut | None = None) -> list[Ticket]:
        """Tous les tickets du dépôt, ou ceux d'un statut, par numéro croissant."""
        tickets = sorted(self._principal.systeme.tickets, key=lambda ticket: ticket.ticketID)
        if statut is None:
            return tickets
        return [ticket for ticket in tickets if ticket.status is statut]

    def actionsPossibles(self, tickets: list[Ticket]) -> dict[str, bool]:
        """Pour chaque action, vrai si au moins un ticket permet la transition.

        Les règles restent dans les états (transitionPossible) : la vue ne les
        recopie pas. Les tickets qui refusent l'action resteront dans le lot et
        apparaîtront, avec leur motif, dans le rapport.
        """
        return {
            action: any(ticket.transitionPossible(statut) for ticket in tickets)
            for action, statut in STATUTS_DES_ACTIONS.items()
        }

    def preparerLot(
        self, action: str, tickets: list[Ticket], user: User | None = None
    ) -> LotAdmin:
        """Construit un lot non appliqué : rien ne change tant que appliquerLot() n'est pas appelé.

        LotAdmin n'a ni retrait ni annulation : pour changer d'assigné, la vue
        demande un nouveau lot, et un lot jamais appliqué est simplement oublié.
        """
        if action not in STATUTS_DES_ACTIONS:
            raise ValueError(f"Action inconnue : {action}")
        if action == "assigner" and user is None:
            raise ValueError("L'action « assigner » demande l'utilisateur à qui assigner")
        lot = self._admin.ouvrirLot()
        for ticket in tickets:
            if action == "assigner" and user is not None:  # user vérifié ci-dessus
                lot.assigner(ticket, user)
            elif action == "desassigner":
                lot.desassigner(ticket)
            elif action == "valider":
                lot.validerTicket(ticket)
            else:
                lot.fermer(ticket)
        return lot

    def appliquerLot(self, lot: LotAdmin) -> None:
        """Applique le lot « au mieux », puis fait afficher le rapport (F8)."""
        rapport = lot.appliquer()
        self._principal.afficherRapport(rapport, lot.libelle)
