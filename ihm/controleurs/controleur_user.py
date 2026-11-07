"""Contrôleur de la liste User (F3) : sans tkinter, testable sans écran."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ihm.passerelle.objets_lecture import BrouillonLu, TicketLu
from modele.enums import Statut

if TYPE_CHECKING:
    from ihm.controleurs.controleur_principal import ControleurPrincipal
    from ihm.passerelle.client_api import ClientAPI
    from ihm.passerelle.objets_lecture import ActeurLu, TicketRefLu
    from ihm.passerelle.source_tickets import SourceTickets


class ControleurUser:
    """Seulement les tickets qui concernent l'utilisateur : ceux qu'il a créés, ceux qui lui sont
    assignés et ses brouillons. Toute modification passe par l'API, jamais par les objets lus.

    Les règles des boutons (peutSupprimer, peutSoumettre, peutEditer) sont celles du modèle :
    un bouton grisé évite le refus du serveur, qui ne sert plus que de filet de sécurité.
    Elles comparent les acteurs par identifiant : chaque lecture crée de nouveaux objets.
    """

    def __init__(
        self,
        principal: ControleurPrincipal,
        user: ActeurLu,
        client: ClientAPI,
        source: SourceTickets,
    ) -> None:
        self._principal: ControleurPrincipal = principal
        self._user: ActeurLu = user
        self._client: ClientAPI = client
        self._source: SourceTickets = source
        self._brouillons: list[BrouillonLu] = []

    @property
    def principal(self) -> ControleurPrincipal:
        return self._principal

    @property
    def user(self) -> ActeurLu:
        return self._user

    @property
    def source(self) -> SourceTickets:
        """Source observée par F3 : tout changement de ticket sur le serveur la notifie."""
        return self._source

    # ------------------------------------------------------------------ listes des trois onglets

    def ticketsCrees(self) -> list[TicketLu]:
        """Onglet « Créés par moi » : GET /tickets?createur=..., par numéro croissant."""
        return self._lireTickets(createur=self._user.id)

    def ticketsAssignes(self) -> list[TicketLu]:
        """Onglet « Assignés à moi » (M1) : GET /tickets?assigne=..., TERMINE et FERME compris."""
        return self._lireTickets(assigne=self._user.id)

    def _lireTickets(self, createur: int | None = None, assigne: int | None = None) -> list[TicketLu]:
        donnees = self._client.listerTickets(createur=createur, assigne=assigne)
        return [TicketLu.depuisJSON(ticket) for ticket in donnees]

    def chargerBrouillons(self) -> None:
        """Relit les brouillons de l'utilisateur (GET /acteur/{id}/brouillons).

        Une seule requête par rafraîchissement de F3 : brouillons() et etatEdition() lisent
        ensuite cette copie, au lieu d'interroger le serveur pour chaque ligne.
        """
        donnees = self._client.listerBrouillons()
        self._brouillons = [BrouillonLu.depuisJSON(brouillon) for brouillon in donnees]

    def brouillons(self) -> list[BrouillonLu]:
        """Onglet « Brouillons » : créations ouvertes, dont le ticket n'est pas encore dans le dépôt.

        Une édition en pause d'un ticket existant n'est pas un brouillon : elle se
        reprend depuis la ligne du ticket (colonne « Édition »).
        """
        creations = [brouillon for brouillon in self._brouillons if brouillon.estCreation]
        return sorted(creations, key=lambda brouillon: brouillon.ticket.ticketID)

    def etatEdition(self, ticket: TicketRefLu) -> str:
        """Colonne « Édition » : "en pause", "en cours" ou "" s'il n'y a pas de brouillon ouvert."""
        brouillon = self._brouillonDe(ticket)
        if brouillon is None:
            return ""
        return "en pause" if brouillon.estEnPause else "en cours"

    def _brouillonDe(self, ticket: TicketRefLu) -> BrouillonLu | None:
        """Brouillon ouvert sur ce ticket ; comparaison par identifiant."""
        return next(
            (b for b in self._brouillons if b.estOuverte and b.ticket == ticket), None
        )

    # ------------------------------------------------------------------ boutons actifs ou grisés
    # Un TicketRefLu (ticket d'un brouillon de création) n'est pas encore dans le dépôt :
    # seul un TicketLu, lu dans la liste du serveur, peut être supprimé ou soumis.

    def peutEditer(self, ticket: TicketRefLu) -> bool:
        """Seul le créateur édite ; un brouillon (ticket hors du dépôt) se reprend aussi."""
        createur = ticket.creator if isinstance(ticket, TicketLu) else None
        return createur == self._user or self._brouillonDe(ticket) is not None

    def peutSupprimer(self, ticket: TicketRefLu) -> bool:
        """Mêmes règles que User.supprimerTicket() : créateur, et ticket jamais assigné."""
        return (
            isinstance(ticket, TicketLu)
            and ticket.creator == self._user
            and not ticket.aDejaEteAssigne
        )

    def peutSoumettre(self, ticket: TicketRefLu) -> bool:
        """Mêmes règles que User.soumettreValidation() : assigné, et transition permise."""
        return (
            isinstance(ticket, TicketLu)
            and ticket.assignedUser == self._user
            and ticket.transitionPossible(Statut.VALIDATION)
        )

    # ------------------------------------------------------------------ actions
    # Après une action, la source est relue tout de suite : F3, F2 et les autres fenêtres de
    # cette GUI sont notifiées sans attendre le prochain sondage de /version.

    def supprimer(self, ticket: TicketLu) -> None:
        """DELETE /ticket/{id} ; le serveur refuse (409) un ticket déjà assigné."""
        self._client.supprimerTicket(ticket.ticketID)
        self._source.rafraichir()

    def soumettre(self, ticket: TicketLu) -> None:
        """PATCH /ticket/{id} vers VALIDATION : User.soumettreValidation() côté serveur."""
        self._client.changerStatut(ticket.ticketID, Statut.VALIDATION)
        self._source.rafraichir()

    def nouveauTicket(self) -> None:
        self._principal.ouvrirCreation(self._user)

    def editer(self, ticket: TicketRefLu) -> None:
        """Reprend le brouillon en cours (même en pause) ou en ouvre un, puis F5."""
        self._principal.ouvrirEdition(self._user, ticket)
