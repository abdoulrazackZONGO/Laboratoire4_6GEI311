from __future__ import annotations

from typing import TYPE_CHECKING

from acteurs.utilisateur_systeme import UtilisateurSysteme
from modele.enums import Statut
from modele.exceptions import (
    AccesRefuseException,
    SessionIndisponibleException,
    SuppressionInterditeException,
)
from sessions.session_creation import SessionCreation
from sessions.session_edition import SessionEdition

if TYPE_CHECKING:
    from modele.systeme_tickets import SystemeTickets
    from modele.ticket import Ticket


class User(UtilisateurSysteme):
    """Utilisateur : crée ses tickets et traite ceux qui lui sont assignés."""

    def __init__(self, id: int, name: str, email: str, systeme: SystemeTickets) -> None:
        super().__init__(id, name, email, systeme)
        # Le ticket sert de clé par identité (Ticket ne définit pas __eq__).
        self._sessions: dict[Ticket, SessionEdition] = {}

    @property
    def role(self) -> str:
        return "User"

    @property
    def sessionsOuvertes(self) -> list[SessionEdition]:
        """Sessions d'édition et de création encore ouvertes."""
        return [session for session in self._sessions.values() if session.estOuverte]

    def sessionEnCours(self, ticket: Ticket) -> SessionEdition | None:
        """Session encore ouverte sur ce ticket, même en pause ; une session close est oubliée."""
        session = self._sessions.get(ticket)
        if session is None:
            return None
        if session.estOuverte:
            return session
        del self._sessions[ticket]
        return None

    def createTicket(self, ticket: Ticket) -> None:
        ticket.definirCreateur(self)
        self._systeme.ajouterTicket(ticket)

    def supprimerTicket(self, ticket: Ticket) -> None:
        """Suppression directe dans le dépôt, sans passer par la machine à états."""
        if ticket.creator is not self:
            raise AccesRefuseException(
                f"{self._name} n'est pas le créateur du ticket {ticket.ticketID}"
            )
        if ticket.aDejaEteAssigne:
            raise SuppressionInterditeException(
                f"Le ticket {ticket.ticketID} a déjà été assigné : suppression interdite"
            )
        self._systeme.retirerTicket(ticket)

    def soumettreValidation(self, ticket: Ticket) -> None:
        if ticket.assignedUser is not self:
            raise AccesRefuseException(
                f"{self._name} n'est pas l'assigné du ticket {ticket.ticketID}"
            )
        ticket.updateStatus(Statut.VALIDATION)

    def ouvrirSessionEdition(self, ticket: Ticket) -> SessionEdition:
        """Seulement par le créateur, et une seule session ouverte par ticket."""
        if ticket.creator is not self:
            raise AccesRefuseException(
                f"{self._name} n'est pas le créateur du ticket {ticket.ticketID} : "
                f"session d'édition refusée"
            )
        if self.sessionEnCours(ticket) is not None:
            raise SessionIndisponibleException(
                f"Une session est déjà ouverte sur le ticket {ticket.ticketID} : "
                f"session d'édition refusée"
            )
        session = SessionEdition(self, ticket, self._systeme)
        self._sessions[ticket] = session
        return session

    def ouvrirSessionCreation(self, ticket: Ticket) -> SessionCreation:
        """Le ticket n'entrera dans le dépôt qu'à l'application de la session."""
        if ticket.creator is not None:
            raise AccesRefuseException(
                f"Le ticket {ticket.ticketID} a déjà un créateur : session de création refusée"
            )
        if self._systeme.contient(ticket):
            raise AccesRefuseException(
                f"Le ticket {ticket.ticketID} est déjà dans le dépôt : session de création refusée"
            )
        if self.sessionEnCours(ticket) is not None:
            raise SessionIndisponibleException(
                f"Une session est déjà ouverte sur le ticket {ticket.ticketID} : "
                f"session de création refusée"
            )
        session = SessionCreation(self, ticket, self._systeme)
        self._sessions[ticket] = session
        return session

    def mesTickets(self, ids: list[int] | None = None) -> list[Ticket]:
        """Tickets créés par cet utilisateur, éventuellement filtrés par identifiant."""
        tickets = self._systeme.ticketsDe(self)
        if ids is None:
            return tickets
        return [ticket for ticket in tickets if ticket.ticketID in ids]
