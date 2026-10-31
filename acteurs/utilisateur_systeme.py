from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from modele.systeme_tickets import SystemeTickets
    from modele.ticket import Ticket


class UtilisateurSysteme(ABC):
    """Acteur du système ; le dépôt de tickets est injecté par le constructeur."""

    def __init__(self, id: int, name: str, email: str, systeme: SystemeTickets) -> None:
        self._id: int = id
        self._name: str = name
        self._email: str = email
        self._systeme: SystemeTickets = systeme

    @property
    def id(self) -> int:
        return self._id

    @property
    def name(self) -> str:
        return self._name

    @property
    def email(self) -> str:
        return self._email

    @property
    @abstractmethod
    def role(self) -> str:
        """Rôle de l'acteur, déduit de sa classe."""

    def viewTicket(self, ticket: Ticket) -> None:
        """MÉTHODE D'AFFICHAGE : détail d'un ticket, uniquement via ses propriétés."""
        createur = ticket.creator.name if ticket.creator is not None else "aucun"
        assigne = ticket.assignedUser.name if ticket.assignedUser is not None else "aucun"
        commentaires = ticket.comments
        print(f"  Ticket #{ticket.ticketID} : {ticket.title}")
        print(f"    Statut       : {ticket.status.name}")
        print(f"    Priorité     : {ticket.priority.name}")
        print(f"    Créateur     : {createur}")
        print(f"    Assigné      : {assigne}")
        print(f"    Créé le      : {ticket.creationDate} | mis à jour le : {ticket.updateDate}")
        print(f"    Commentaires : {len(commentaires)}")
        for commentaire in commentaires:
            print(f"      - {commentaire.auteur.name} ({commentaire.date}) : {commentaire.texte}")
        print(f"    Éléments de description : {ticket.description.nombreElements}")
