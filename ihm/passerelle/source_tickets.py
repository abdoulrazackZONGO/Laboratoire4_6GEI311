"""Source observable des tickets : la copie locale que les vues observent (C2).

Au lab 3, les vues s'abonnaient à SystemeTickets, qui les prévenait à chaque changement.
Le dépôt vit maintenant dans le serveur : la source interroge GET /version, relit les tickets
quand ce compteur change, compare avec sa dernière copie et notifie les différences par les
mêmes méthodes (ticketAjoute, ticketModifie, ticketRetire). Les fenêtres s'abonnent à elle
exactement comme elles s'abonnaient à SystemeTickets.

Le sondage périodique (after() de Tkinter, une fois par seconde) est branché en C3 : ce
module n'a besoin ni de Tkinter ni de minuterie, il offre verifierVersion() à appeler.
"""
from __future__ import annotations

from typing import Any, Protocol

from ihm.passerelle.erreurs import ReponseInvalide, RessourceIntrouvable
from ihm.passerelle.objets_lecture import ObjetJSON, TicketLu
from modele.observateur import SujetTickets


class LecteurTickets(Protocol):
    """Ce que la source demande à la passerelle (ClientAPI le fournit)."""

    def lireVersion(self) -> int: ...

    def listerTickets(self) -> list[ObjetJSON]: ...

    def lireTicket(self, ticketId: int) -> ObjetJSON: ...


class SourceTickets(SujetTickets):
    """Dernière liste de tickets reçue du serveur, observable.

    Les tickets de la liste sont des résumés. Un ticket dont on a lu le détail
    (lireDetail) est suivi en entier : la source le relit à chaque rafraîchissement et
    le fournit détaillé, ce qui permet à sa fenêtre de détail de voir aussi un changement
    de description, que le résumé ne montre pas. Cette règle vaut partout : tickets,
    ticketParId et notifications donnent l'objet le plus complet connu.

    Ne pas utiliser `is` pour comparer ces tickets : chaque rafraîchissement en recrée.
    """

    def __init__(self, client: LecteurTickets) -> None:
        super().__init__()
        self._client: LecteurTickets = client
        self._version: int | None = None
        # Dernier JSON reçu et objet correspondant, par identifiant de ticket.
        self._resumesJSON: dict[int, ObjetJSON] = {}
        self._resumes: dict[int, TicketLu] = {}
        self._detailsJSON: dict[int, ObjetJSON] = {}
        self._details: dict[int, TicketLu] = {}

    @property
    def version(self) -> int | None:
        """Version du serveur au dernier chargement ; None tant que rien n'est chargé."""
        return self._version

    @property
    def tickets(self) -> list[TicketLu]:
        """Tickets connus, triés par identifiant comme le serveur les envoie."""
        return [self._objet(identifiant) for identifiant in sorted(self._resumes)]

    def ticketParId(self, id: int) -> TicketLu | None:
        return self._objet(id) if id in self._resumes else None

    # ------------------------------------------------------------------ chargement

    def rafraichir(self) -> None:
        """Relit les tickets et notifie ce qui a changé. À appeler après chaque action."""
        self._charger(self._client.lireVersion())

    def verifierVersion(self) -> bool:
        """Relit les tickets seulement si /version a changé ; dit si c'était le cas.

        Un seul petit appel quand rien n'a bougé : c'est ce que la GUI répète chaque seconde.
        """
        version = self._client.lireVersion()
        if version == self._version:
            return False
        self._charger(version)
        return True

    def lireDetail(self, ticketId: int) -> TicketLu:
        """Lit le détail d'un ticket (F6) et le suit jusqu'à oublierDetail.

        Si le serveur en sait plus que la copie déjà suivie, les abonnés sont notifiés.
        """
        donnees, ticket = self._lireDetailJSON(ticketId)
        ancien = self._detailsJSON.get(ticketId)
        self._detailsJSON[ticketId] = donnees
        self._details[ticketId] = ticket
        if ancien is not None and ancien != donnees:
            self._notifierModification(ticket)
        return ticket

    def oublierDetail(self, ticketId: int) -> None:
        """Cesse de suivre le détail (fenêtre fermée) ; sans effet s'il n'était pas suivi."""
        self._detailsJSON.pop(ticketId, None)
        self._details.pop(ticketId, None)

    def _charger(self, version: int) -> None:
        """Lit tout, compare, met la copie à jour, puis seulement notifie.

        La version est lue avant les tickets : un changement survenu entre les deux lectures
        sera vu par le prochain sondage (au pire, un rafraîchissement de trop). Toute lecture
        qui échoue laisse la copie intacte. La copie est à jour avant la première
        notification : un abonné qui lève une exception ne la laisse pas à moitié changée.
        """
        liste: Any = self._client.listerTickets()
        if not isinstance(liste, list):
            raise ReponseInvalide("Réponse de /tickets qui n'est pas une liste", 200)
        resumesJSON: dict[int, ObjetJSON] = {}
        resumes: dict[int, TicketLu] = {}
        for donnees in liste:
            ticket = TicketLu.depuisJSON(donnees)
            resumesJSON[ticket.ticketID] = donnees
            resumes[ticket.ticketID] = ticket

        detailsJSON: dict[int, ObjetJSON] = {}
        details: dict[int, TicketLu] = {}
        for identifiant in self._details:
            if identifiant not in resumes:
                continue
            try:
                detailsJSON[identifiant], details[identifiant] = self._lireDetailJSON(identifiant)
            except RessourceIntrouvable:
                # Supprimé entre les deux lectures : le prochain sondage le verra retiré.
                continue

        retires = sorted(set(self._resumes) - set(resumes))
        ajoutes = sorted(set(resumes) - set(self._resumes))
        modifies = sorted(
            identifiant
            for identifiant in set(resumes) & set(self._resumes)
            if resumesJSON[identifiant] != self._resumesJSON[identifiant]
            or (
                identifiant in details
                and detailsJSON[identifiant] != self._detailsJSON.get(identifiant)
            )
        )
        ticketsRetires = [self._objet(identifiant) for identifiant in retires]

        self._version = version
        self._resumesJSON, self._resumes = resumesJSON, resumes
        self._detailsJSON, self._details = detailsJSON, details

        for ticket in ticketsRetires:
            self._notifierRetrait(ticket)
        for identifiant in ajoutes:
            self._notifierAjout(self._objet(identifiant))
        for identifiant in modifies:
            self._notifierModification(self._objet(identifiant))

    def _lireDetailJSON(self, ticketId: int) -> tuple[ObjetJSON, TicketLu]:
        """GET /ticket/{id}, vérifié : la même règle pour lireDetail et pour le suivi."""
        donnees = self._client.lireTicket(ticketId)
        ticket = TicketLu.depuisJSON(donnees)
        if not ticket.estDetaille or ticket.ticketID != ticketId:
            raise ReponseInvalide(
                f"Réponse de /ticket/{ticketId} qui n'est pas le détail de ce ticket", 200
            )
        return donnees, ticket

    def _objet(self, identifiant: int) -> TicketLu:
        """L'objet le plus complet connu : le détail suivi, sinon le résumé."""
        detail = self._details.get(identifiant)
        return detail if detail is not None else self._resumes[identifiant]

