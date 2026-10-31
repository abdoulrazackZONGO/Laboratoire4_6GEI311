from __future__ import annotations

from typing import TYPE_CHECKING

from modele.observateur import ObservateurTickets, SujetTickets

if TYPE_CHECKING:
    from acteurs.user import User
    from acteurs.utilisateur_systeme import UtilisateurSysteme
    from modele.ticket import Ticket


class SystemeTickets(SujetTickets, ObservateurTickets):
    """Dépôt central des tickets.

    Sujet observable pour les vues, et relais : il observe chacun de ses
    tickets et retransmet leurs modifications à ses propres abonnés. Une vue
    de liste n'a ainsi qu'un seul abonnement à gérer, au lieu d'un par ticket.
    """

    def __init__(self) -> None:
        super().__init__()
        self._tickets: list[Ticket] = []
        self._utilisateurs: list[UtilisateurSysteme] = []

    @property
    def tickets(self) -> list[Ticket]:
        return list(self._tickets)

    def ajouterTicket(self, ticket: Ticket) -> None:
        self._tickets.append(ticket)
        ticket.abonner(self)
        self._notifierAjout(ticket)

    def retirerTicket(self, ticket: Ticket) -> None:
        self._tickets.remove(ticket)
        ticket.desabonner(self)
        self._notifierRetrait(ticket)

    @property
    def utilisateurs(self) -> list[UtilisateurSysteme]:
        """Annuaire : sert à la connexion (choix de l'utilisateur) et à la sauvegarde."""
        return list(self._utilisateurs)

    def inscrireUtilisateur(self, utilisateur: UtilisateurSysteme) -> None:
        """Inscription idempotente ; deux utilisateurs distincts ne partagent pas un identifiant."""
        existant = self.utilisateurParId(utilisateur.id)
        if existant is utilisateur:
            return
        if existant is not None:
            raise ValueError(
                f"Identifiant d'utilisateur déjà utilisé : {utilisateur.id} ({existant.name})"
            )
        self._utilisateurs.append(utilisateur)

    def utilisateurParId(self, id: int) -> UtilisateurSysteme | None:
        for utilisateur in self._utilisateurs:
            if utilisateur.id == id:
                return utilisateur
        return None

    def contient(self, ticket: Ticket) -> bool:
        return ticket in self._tickets

    def ticketsDe(self, user: User) -> list[Ticket]:
        """Tickets dont l'utilisateur est le créateur."""
        return [ticket for ticket in self._tickets if ticket.creator is user]

    def ticketsAssignesA(self, user: User) -> list[Ticket]:
        """Tickets dont l'utilisateur est l'assigné courant.

        Comprend aussi les tickets TERMINE ou FERME : l'assigné y est conservé
        pour la traçabilité. La vue filtre par statut si nécessaire.
        """
        return [ticket for ticket in self._tickets if ticket.assignedUser is user]

    def ticketModifie(self, ticket: Ticket) -> None:
        """Relais : retransmet la modification d'un ticket du dépôt à ses abonnés."""
        if ticket in self._tickets:
            self._notifierModification(ticket)
