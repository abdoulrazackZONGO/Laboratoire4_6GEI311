"""Contrôleur de la liste User (F3) : sans tkinter, testable sans écran."""
from __future__ import annotations

from typing import TYPE_CHECKING

from modele.enums import Statut

if TYPE_CHECKING:
    from acteurs.user import User
    from ihm.controleurs.controleur_principal import ControleurPrincipal
    from modele.ticket import Ticket
    from sessions.session_edition import SessionEdition


class ControleurUser:
    """Seulement les tickets qui concernent l'utilisateur : ceux qu'il a créés, ceux qui lui sont
    assignés et ses brouillons. Toute modification passe par User (Lab 2), jamais par le ticket.

    Les règles des boutons (peutSupprimer, peutSoumettre, peutEditer) sont celles du modèle :
    un bouton grisé évite l'exception, qui ne sert plus que de filet de sécurité.
    """

    def __init__(self, principal: ControleurPrincipal, user: User) -> None:
        self._principal: ControleurPrincipal = principal
        self._user: User = user

    @property
    def principal(self) -> ControleurPrincipal:
        return self._principal

    @property
    def user(self) -> User:
        return self._user

    # ------------------------------------------------------------------ listes des trois onglets

    def ticketsCrees(self) -> list[Ticket]:
        """Onglet « Créés par moi », par numéro croissant."""
        return sorted(self._user.mesTickets(), key=lambda ticket: ticket.ticketID)

    def ticketsAssignes(self) -> list[Ticket]:
        """Onglet « Assignés à moi » (M1), par numéro croissant."""
        tickets = self._principal.systeme.ticketsAssignesA(self._user)
        return sorted(tickets, key=lambda ticket: ticket.ticketID)

    def brouillons(self) -> list[SessionEdition]:
        """Onglet « Brouillons » : créations ouvertes, dont le ticket n'est pas encore dans le dépôt.

        Une édition en pause d'un ticket existant n'est pas un brouillon : elle se
        reprend depuis la ligne du ticket (colonne « Édition »).
        """
        systeme = self._principal.systeme
        sessions = [
            session for session in self._user.sessionsOuvertes
            if not systeme.contient(session.ticket)
        ]
        return sorted(sessions, key=lambda session: session.ticket.ticketID)

    def etatEdition(self, ticket: Ticket) -> str:
        """Colonne « Édition » : "en pause", "en cours" ou "" s'il n'y a pas de session ouverte."""
        session = self._user.sessionEnCours(ticket)
        if session is None:
            return ""
        return "en pause" if session.estEnPause else "en cours"

    # ------------------------------------------------------------------ boutons actifs ou grisés

    def peutEditer(self, ticket: Ticket) -> bool:
        """Seul le créateur édite ; un brouillon (ticket hors du dépôt) se reprend aussi."""
        return ticket.creator is self._user or self._user.sessionEnCours(ticket) is not None

    def peutSupprimer(self, ticket: Ticket) -> bool:
        """Mêmes règles que User.supprimerTicket() : créateur, et ticket jamais assigné."""
        return (
            self._principal.systeme.contient(ticket)
            and ticket.creator is self._user
            and not ticket.aDejaEteAssigne
        )

    def peutSoumettre(self, ticket: Ticket) -> bool:
        """Mêmes règles que User.soumettreValidation() : assigné, et transition permise."""
        return ticket.assignedUser is self._user and ticket.transitionPossible(Statut.VALIDATION)

    # ------------------------------------------------------------------ actions

    def supprimer(self, ticket: Ticket) -> None:
        self._user.supprimerTicket(ticket)

    def soumettre(self, ticket: Ticket) -> None:
        self._user.soumettreValidation(ticket)

    def nouveauTicket(self) -> None:
        self._principal.ouvrirCreation(self._user)

    def editer(self, ticket: Ticket) -> None:
        """Reprend la session en cours (même en pause) ou en ouvre une, puis F5."""
        self._principal.ouvrirEdition(self._user, ticket)
