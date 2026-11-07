"""Contrôleur de la liste Admin (F2) et du lot (F7) : sans tkinter, testable sans écran."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ihm.passerelle.objets_lecture import RapportLu
from modele.enums import Statut

if TYPE_CHECKING:
    from ihm.controleurs.controleur_principal import ControleurPrincipal
    from ihm.passerelle.client_api import ClientAPI
    from ihm.passerelle.objets_lecture import ActeurLu, TicketLu
    from ihm.passerelle.source_tickets import SourceTickets

# Chaque action de l'Admin et le statut qu'elle demande à l'état du ticket.
# assigner couvre l'assignation, la réassignation et le rejet d'une validation.
STATUTS_DES_ACTIONS: dict[str, Statut] = {
    "assigner": Statut.ASSIGNE,
    "desassigner": Statut.OUVERT,
    "valider": Statut.TERMINE,
    "fermer": Statut.FERME,
}

# Libellé du lot, comme LotAdmin.libelle : le rapport du serveur porte le même.
LIBELLE_LOT = "Lot administrateur"


@dataclass(frozen=True)
class LotPrepare:
    """Aperçu d'un lot (F7), construit sur le client : rien n'est envoyé avant appliquerLot().

    Le serveur ne garde pas les lots (pas de GET sur /lots) : l'aperçu n'a pas besoin de lui,
    puisqu'il ne modifie rien. Ses libellés reprennent ceux des commandes du modèle, pour que
    F7 annonce exactement les opérations que le rapport F8 détaillera.
    """

    action: str
    ticketIds: tuple[int, ...]
    assigneId: int | None
    modificationsEnAttente: tuple[str, ...]
    libelle: str = LIBELLE_LOT


def libelleOperation(action: str, ticket: TicketLu, assigne: ActeurLu | None = None) -> str:
    """Libellé d'une opération du lot, identique à celui de la commande du modèle."""
    if action == "assigner" and assigne is not None:
        return f"Assigner le ticket #{ticket.ticketID} à {assigne.name}"
    if action == "desassigner":
        return f"Désassigner le ticket #{ticket.ticketID}"
    if action == "valider":
        return f"Valider le ticket #{ticket.ticketID}"
    if action == "fermer":
        return f"Fermer le ticket #{ticket.ticketID}"
    raise ValueError(f"Action inconnue : {action}")


class ControleurAdmin:
    """Toute modification passe par l'API, jamais par les objets de lecture.

    La vue F2 lit les tickets ici ; elle s'abonne à la source et trouve ouvrirDetail()
    et ouvrirLot() dans principal. Un lot n'est envoyé au serveur que par appliquerLot().
    """

    def __init__(
        self,
        principal: ControleurPrincipal,
        admin: ActeurLu,
        client: ClientAPI,
        source: SourceTickets,
    ) -> None:
        self._principal: ControleurPrincipal = principal
        self._admin: ActeurLu = admin
        self._client: ClientAPI = client
        self._source: SourceTickets = source

    @property
    def principal(self) -> ControleurPrincipal:
        return self._principal

    @property
    def admin(self) -> ActeurLu:
        return self._admin

    @property
    def source(self) -> SourceTickets:
        """Copie locale des tickets du serveur, à laquelle F2 et F7 s'abonnent."""
        return self._source

    def tickets(self, statut: Statut | None = None) -> list[TicketLu]:
        """Tous les tickets, ou ceux d'un statut, par numéro croissant.

        La source tient déjà toute la liste : filtrer ici évite une requête par
        changement de filtre, et le tableau reste celui que la source vient de notifier.
        """
        tickets = self._source.tickets
        if statut is None:
            return tickets
        return [ticket for ticket in tickets if ticket.status is statut]

    def actionsPossibles(self, tickets: list[TicketLu]) -> dict[str, bool]:
        """Pour chaque action, vrai si au moins un ticket permet la transition.

        Les règles restent dans les états du serveur (transitionsPermises) : la vue ne
        les recopie pas. Les tickets qui refusent l'action resteront dans le lot et
        apparaîtront, avec leur motif, dans le rapport.
        """
        return {
            action: any(ticket.transitionPossible(statut) for ticket in tickets)
            for action, statut in STATUTS_DES_ACTIONS.items()
        }

    def preparerLot(
        self, action: str, tickets: list[TicketLu], user: ActeurLu | None = None
    ) -> LotPrepare:
        """Construit l'aperçu d'un lot : rien ne change tant que appliquerLot() n'est pas appelé.

        Pour changer d'assigné, la vue demande un nouvel aperçu ; un aperçu jamais
        appliqué est simplement oublié.
        """
        if action not in STATUTS_DES_ACTIONS:
            raise ValueError(f"Action inconnue : {action}")
        if action == "assigner" and user is None:
            raise ValueError("L'action « assigner » demande l'utilisateur à qui assigner")
        assigne = user if action == "assigner" else None
        return LotPrepare(
            action=action,
            ticketIds=tuple(ticket.ticketID for ticket in tickets),
            assigneId=None if assigne is None else assigne.id,
            modificationsEnAttente=tuple(
                libelleOperation(action, ticket, assigne) for ticket in tickets
            ),
        )

    def appliquerLot(self, lot: LotPrepare) -> RapportLu:
        """Envoie le lot (POST /acteur/{id}/lots), rafraîchit la source, puis affiche F8.

        Le serveur applique « au mieux » : les refus sont dans le rapport, pas en exception.
        La source est relue tout de suite, sans attendre le prochain sondage : F2 se met à
        jour avant que le rapport ne s'affiche.
        """
        rapport = RapportLu.depuisJSON(
            self._client.appliquerLot(lot.action, list(lot.ticketIds), lot.assigneId)
        )
        self._source.rafraichir()
        self._principal.afficherRapport(rapport, rapport.libelle)
        return rapport
