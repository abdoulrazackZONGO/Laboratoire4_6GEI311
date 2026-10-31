from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from description.description import Description
from etats.etat_ouvert import EtatOuvert
from etats.fabrique_etat import FabriqueEtat
from modele.commentaire import Commentaire
from modele.exceptions import AccesRefuseException
from modele.observateur import SujetTickets

if TYPE_CHECKING:
    from acteurs.user import User
    from acteurs.utilisateur_systeme import UtilisateurSysteme
    from description.element_description import ElementDescription
    from etats.etat_ticket import EtatTicket
    from modele.enums import Priorite, Statut


class Ticket(SujetTickets):
    """Ticket de support : contexte de la machine à états (patron State)
    et sujet observable (patron Observateur)."""

    @classmethod
    def restaurer(
        cls,
        *,
        ticketID: int,
        title: str,
        priority: Priorite,
        status: Statut,
        creationDate: date,
        updateDate: date,
        creator: User | None,
        assignedUser: User | None,
        aDejaEteAssigne: bool,
        comments: list[Commentaire],
        elements: list[ElementDescription],
    ) -> Ticket:
        """Reconstruit un ticket sauvegardé exactement tel qu'il était.

        Restauration privilégiée : le statut sauvegardé a déjà été atteint
        légalement, donc on ne rejoue pas la machine à états ; et le ticket est
        neuf, donc aucun observateur n'est à prévenir.
        """
        ticket = cls(ticketID, title, priority)
        ticket._etat = FabriqueEtat.creer(status)
        ticket._creator = creator
        ticket._assignedUser = assignedUser
        ticket._aEteAssigne = aDejaEteAssigne
        ticket._comments = list(comments)
        for element in elements:
            ticket._description.ajouterElement(element)
        ticket._creationDate = creationDate
        ticket._updateDate = updateDate
        return ticket

    def __init__(self, ticketID: int, title: str, priority: Priorite) -> None:
        super().__init__()
        self._ticketID: int = ticketID
        self._title: str = title
        self._priority: Priorite = priority
        self._creationDate: date = date.today()
        self._updateDate: date = date.today()
        self._etat: EtatTicket = EtatOuvert()
        self._creator: User | None = None
        self._assignedUser: User | None = None
        self._aEteAssigne: bool = False
        self._comments: list[Commentaire] = []
        self._description: Description = Description()

    @property
    def ticketID(self) -> int:
        return self._ticketID

    @property
    def title(self) -> str:
        return self._title

    @property
    def priority(self) -> Priorite:
        return self._priority

    @property
    def creationDate(self) -> date:
        return self._creationDate

    @property
    def updateDate(self) -> date:
        return self._updateDate

    @property
    def status(self) -> Statut:
        """Attribut dérivé : le statut n'est pas stocké, il provient de l'état courant."""
        return self._etat.nom

    @property
    def creator(self) -> User | None:
        return self._creator

    @property
    def assignedUser(self) -> User | None:
        return self._assignedUser

    @property
    def aDejaEteAssigne(self) -> bool:
        return self._aEteAssigne

    @property
    def comments(self) -> list[Commentaire]:
        return list(self._comments)

    @property
    def description(self) -> Description:
        return self._description

    @property
    def transitionsPermises(self) -> frozenset[Statut]:
        """Statuts accessibles depuis l'état courant (lecture seule, pour les vues)."""
        return self._etat.transitionsPermises

    def updateStatus(self, nouveau_statut: Statut) -> None:
        """Délègue entièrement la décision à l'état courant."""
        self._etat.gererTransition(self, nouveau_statut)

    def transitionPossible(self, nouveau_statut: Statut) -> bool:
        """Interroge l'état courant sans rien modifier.

        Permet à la vue d'activer ou de griser un bouton sans recopier
        les règles de la machine à états.
        """
        return self._etat.transitionPossible(nouveau_statut)

    def setEtat(self, nouvel_etat: EtatTicket) -> None:
        """Réservée aux classes d'état."""
        self._etat = nouvel_etat
        self._signalerModification()

    def definirCreateur(self, user: User) -> None:
        if self._creator is not None:
            raise AccesRefuseException(
                f"Le ticket {self._ticketID} a déjà un créateur : {self._creator.name}"
            )
        self._creator = user
        self._signalerModification()

    def assignTo(self, user: User) -> None:
        self._assignedUser = user
        self._aEteAssigne = True
        self._signalerModification()

    def retirerAssignation(self) -> None:
        # _aEteAssigne n'est jamais remis à False : l'historique d'assignation est conservé.
        self._assignedUser = None
        self._signalerModification()

    def addComment(self, texte: str, auteur: UtilisateurSysteme) -> None:
        """Autorisé dans tous les états."""
        self._comments.append(Commentaire(texte, auteur, date.today()))
        self._signalerModification()

    def ajouterElementDescription(self, element: ElementDescription) -> None:
        """Ajoute un élément à la description et prévient les observateurs.

        Passer par le ticket plutôt que par ticket.description garantit
        que la modification est notifiée.
        """
        self._description.ajouterElement(element)
        self._signalerModification()

    def _signalerModification(self) -> None:
        """Point unique de toute modification : date de mise à jour, puis notification."""
        self._updateDate = date.today()
        self._notifierModification(self)
