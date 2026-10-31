from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from modele.exceptions import (
    AccesRefuseException,
    SessionIndisponibleException,
    TransitionInvalideException,
)
from sessions.rapport_execution import RapportExecution

if TYPE_CHECKING:
    from acteurs.utilisateur_systeme import UtilisateurSysteme
    from commandes.commande import Commande
    from modele.systeme_tickets import SystemeTickets


class SessionOperations(ABC):
    """Pile de commandes appliquées en une fois, « au mieux »."""

    def __init__(self, proprietaire: UtilisateurSysteme, systeme: SystemeTickets) -> None:
        self._proprietaire: UtilisateurSysteme = proprietaire
        self._systeme: SystemeTickets = systeme
        self._commandes: list[Commande] = []
        self._appliquee: bool = False

    @property
    @abstractmethod
    def libelle(self) -> str:
        """Nom lisible du type de session."""

    @property
    def modificationsEnAttente(self) -> list[str]:
        return [commande.libelle for commande in self._commandes]

    def _ajouter(self, commande: Commande) -> None:
        """PROTÉGÉE : seul point d'entrée des commandes dans la pile."""
        self._verifierAjout(commande)
        self._commandes.append(commande)

    def _verifierAjout(self, commande: Commande) -> None:
        """Par défaut : aucun ajout après application."""
        if self._appliquee:
            raise SessionIndisponibleException(
                f"{self.libelle} : application déjà effectuée, ajout impossible"
            )

    def appliquer(self) -> RapportExecution:
        """Exécute les commandes dans l'ordre ; un refus ne bloque pas les suivantes."""
        if self._appliquee:
            raise SessionIndisponibleException(
                f"{self.libelle} : application déjà effectuée"
            )
        rapport = RapportExecution()
        for commande in self._commandes:
            if not self._systeme.contient(commande.cible):
                rapport.ajouterRefus(commande.libelle, "ticket retiré du dépôt")
                continue
            try:
                commande.executer()
            except (TransitionInvalideException, AccesRefuseException) as erreur:
                rapport.ajouterRefus(commande.libelle, str(erreur))
            else:
                rapport.ajouterSucces(commande.libelle)
        self._appliquee = True
        self._commandes.clear()
        return rapport
