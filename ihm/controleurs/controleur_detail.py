"""Contrôleur du détail d'un ticket (F6) : sans tkinter, testable sans écran."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ihm.passerelle.client_api import ClientAPI
    from ihm.passerelle.objets_lecture import ElementLu, TicketLu, TicketRefLu
    from ihm.passerelle.source_tickets import SourceTickets


class ControleurDetail:
    """Parcourt une liste de tickets par leur identifiant et lit le détail du ticket affiché.

    La liste vient de F2 ou de F3 : seuls les identifiants sont gardés. Les tickets lus sont
    recréés à chaque rafraîchissement de la source, donc comparer les objets avec `is`
    échouerait toujours.

    Seul le ticket affiché est suivi en détail par la source (lireDetail) : elle le relit à
    chaque changement du serveur et prévient la fenêtre, y compris d'un changement de
    description ou de commentaire que le résumé de la liste ne montre pas.
    """

    def __init__(
        self,
        client: ClientAPI,
        source: SourceTickets,
        tickets: list[TicketRefLu],
        index: int,
    ) -> None:
        if not 0 <= index < len(tickets):
            raise IndexError(f"index {index} hors de la liste de {len(tickets)} tickets")
        self._client: ClientAPI = client
        self._source: SourceTickets = source
        self._identifiants: list[int] = [ticket.ticketID for ticket in tickets]
        self._index: int = index
        self._ticket: TicketLu | None = None
        # Octets des images déjà téléchargées, par url : une image d'un ticket ne change pas
        # (chaque copie a un nom unique), il est inutile de la retélécharger à chaque redessin.
        self._images: dict[str, bytes] = {}

    @property
    def source(self) -> SourceTickets:
        return self._source

    @property
    def identifiantCourant(self) -> int:
        return self._identifiants[self._index]

    @property
    def ticket(self) -> TicketLu:
        """Dernier détail lu du ticket affiché ; charger() doit avoir réussi une fois."""
        if self._ticket is None:
            raise RuntimeError("Le détail n'est pas chargé (appeler charger() d'abord)")
        return self._ticket

    @property
    def position(self) -> int:
        """Rang du ticket affiché, à partir de 1."""
        return self._index + 1

    @property
    def nombre(self) -> int:
        return len(self._identifiants)

    @property
    def peutReculer(self) -> bool:
        return self._index > 0

    @property
    def peutAvancer(self) -> bool:
        return self._index < len(self._identifiants) - 1

    # ------------------------------------------------------------------ lecture

    def charger(self) -> TicketLu:
        """Lit le détail du ticket affiché et le suit.

        La copie de la source est utilisée si elle est déjà détaillée : aucune requête de
        plus quand c'est la source elle-même qui vient de prévenir la fenêtre.
        Lève RessourceIntrouvable si le ticket n'existe plus sur le serveur.
        """
        self._ticket = self._lire(self.identifiantCourant)
        return self._ticket

    def aller(self, pas: int) -> bool:
        """Passe au ticket voisin ; rend faux s'il n'y en a pas.

        Le nouveau détail est lu avant de quitter l'ancien : si le serveur répond par une
        erreur, F6 reste sur le ticket qu'elle affichait.
        """
        index = self._index + pas
        if not 0 <= index < len(self._identifiants):
            return False
        ancien = self.identifiantCourant
        ticket = self._lire(self._identifiants[index])
        self._index = index
        self._ticket = ticket
        self._source.oublierDetail(ancien)
        return True

    def octetsImage(self, element: ElementLu) -> bytes:
        """Octets d'une image de la description, téléchargés par l'API (GET url)."""
        if element.url is None:
            raise ValueError(f"L'élément « {element.nom} » n'a pas d'url d'image")
        octets = self._images.get(element.url)
        if octets is None:
            octets = self._client.lireOctets(element.url)
            self._images[element.url] = octets
        return octets

    # ------------------------------------------------------------------ ticket retiré

    def parcourt(self, ticketId: int) -> bool:
        """Vrai si ce ticket fait partie de la liste parcourue."""
        return ticketId in self._identifiants

    def estCourant(self, ticketId: int) -> bool:
        return ticketId == self.identifiantCourant

    def retirer(self, ticketId: int) -> bool:
        """Retire un ticket supprimé de la liste ; dit s'il était affiché.

        Si c'était le dernier de la liste, l'affichage recule d'un rang. Quand la liste devient
        vide, plus rien n'est affiché : la fenêtre se ferme.
        """
        position = self._identifiants.index(ticketId)
        etaitCourant = position == self._index
        del self._identifiants[position]
        if position < self._index or (
            position == self._index and self._index == len(self._identifiants)
        ):
            self._index = max(self._index - 1, 0)
        self._source.oublierDetail(ticketId)
        if etaitCourant:
            self._ticket = None
        return etaitCourant

    @property
    def estVide(self) -> bool:
        return not self._identifiants

    def fermer(self) -> None:
        """La fenêtre se ferme : la source cesse de relire ce détail à chaque changement."""
        if self._identifiants:
            self._source.oublierDetail(self.identifiantCourant)

    # ------------------------------------------------------------------ interne

    def _lire(self, ticketId: int) -> TicketLu:
        connu = self._source.ticketParId(ticketId)
        if connu is not None and connu.estDetaille:
            return connu
        return self._source.lireDetail(ticketId)
