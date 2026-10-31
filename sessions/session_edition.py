from __future__ import annotations

from typing import TYPE_CHECKING

from commandes.commande_ajouter_commentaire import CommandeAjouterCommentaire
from commandes.commande_ajouter_element import CommandeAjouterElement
from description.fabrique_description import FabriqueDescription
from modele.exceptions import AccesRefuseException, SessionIndisponibleException
from sessions.session_operations import SessionOperations

if TYPE_CHECKING:
    from acteurs.user import User
    from commandes.commande import Commande
    from modele.systeme_tickets import SystemeTickets
    from modele.ticket import Ticket
    from sessions.rapport_execution import RapportExecution


class SessionEdition(SessionOperations):
    """Édition d'un ticket par son créateur : rien ne change avant appliquer()."""

    def __init__(self, proprietaire: User, ticket: Ticket, systeme: SystemeTickets) -> None:
        super().__init__(proprietaire, systeme)
        self._ticket: Ticket = ticket
        self._enPause: bool = False
        self._abandonnee: bool = False

    @property
    def libelle(self) -> str:
        return "Session d'édition"

    @property
    def estEnPause(self) -> bool:
        return self._enPause

    @property
    def estOuverte(self) -> bool:
        """Vraie tant que la session n'est ni appliquée ni abandonnée."""
        return not self._appliquee and not self._abandonnee

    @property
    def ticket(self) -> Ticket:
        """Ticket visé par la session (aussi pour SessionCreation)."""
        return self._ticket

    def ajouterCommentaire(self, texte: str) -> None:
        self._ajouter(CommandeAjouterCommentaire(self._ticket, texte, self._proprietaire))

    def ajouterElement(self, type_artefact: str, chemin: str) -> None:
        element = FabriqueDescription.creer(type_artefact, chemin)
        # Traitement immédiat : le chemin est validé dès l'ajout.
        element.traiter()
        self._ajouter(CommandeAjouterElement(self._ticket, element))

    def ajouterTexteSaisi(self, texte: str) -> None:
        element = FabriqueDescription.creerSaisie(texte)
        # Traitement immédiat : un texte vide est refusé dès l'ajout.
        element.traiter()
        self._ajouter(CommandeAjouterElement(self._ticket, element))

    def annulerDerniere(self) -> str:
        """Retire la dernière modification en attente et retourne son libellé."""
        self._refuserSiAbandonnee("annulation")
        if self._appliquee:
            raise SessionIndisponibleException(
                f"{self.libelle} : application déjà effectuée, annulation impossible"
            )
        if self._enPause:
            raise SessionIndisponibleException(
                f"{self.libelle} en pause : annulation impossible"
            )
        if not self._commandes:
            raise SessionIndisponibleException(
                f"{self.libelle} : aucune modification en attente à annuler"
            )
        return self._commandes.pop().libelle

    def mettreEnPause(self) -> None:
        self._refuserSiAbandonnee("mise en pause")
        if self._enPause:
            raise SessionIndisponibleException(f"{self.libelle} déjà en pause")
        if self._appliquee:
            raise SessionIndisponibleException(
                f"{self.libelle} : application déjà effectuée, mise en pause impossible"
            )
        self._enPause = True

    def reprendre(self) -> None:
        self._refuserSiAbandonnee("reprise")
        if not self._enPause:
            raise SessionIndisponibleException(
                f"{self.libelle} non en pause : reprise impossible"
            )
        self._enPause = False

    def abandonner(self) -> None:
        """Renonce à toute la session avant application : le ticket reste inchangé."""
        if self._appliquee:
            raise SessionIndisponibleException(
                f"{self.libelle} : application déjà effectuée, abandon impossible"
            )
        if self._abandonnee:
            raise SessionIndisponibleException(f"{self.libelle} déjà abandonnée")
        # Permis même en pause : la pile est vidée et la pause levée.
        self._commandes.clear()
        self._enPause = False
        self._abandonnee = True

    def _refuserSiAbandonnee(self, operation: str) -> None:
        if self._abandonnee:
            raise SessionIndisponibleException(
                f"{self.libelle} abandonnée : {operation} impossible"
            )

    def _verifierAjout(self, commande: Commande) -> None:
        super()._verifierAjout(commande)
        self._refuserSiAbandonnee("ajout")
        if self._enPause:
            raise SessionIndisponibleException(f"{self.libelle} en pause : ajout impossible")
        if commande.cible is not self._ticket:
            raise AccesRefuseException(
                f"La commande vise le ticket #{commande.cible.ticketID}, "
                f"hors du ticket #{self._ticket.ticketID} de la session"
            )

    def appliquer(self) -> RapportExecution:
        self._refuserSiAbandonnee("application")
        if self._enPause:
            raise SessionIndisponibleException(
                f"{self.libelle} en pause : application impossible"
            )
        if not self._systeme.contient(self._ticket):
            raise SessionIndisponibleException(
                f"Le ticket #{self._ticket.ticketID} a été retiré du dépôt : "
                f"application impossible"
            )
        return super().appliquer()
