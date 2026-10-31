from __future__ import annotations

from typing import TYPE_CHECKING

from commandes.commande import Commande

if TYPE_CHECKING:
    from acteurs.utilisateur_systeme import UtilisateurSysteme
    from modele.ticket import Ticket


class CommandeAjouterCommentaire(Commande):
    """Ajoute un commentaire au ticket cible."""

    def __init__(self, cible: Ticket, texte: str, auteur: UtilisateurSysteme) -> None:
        super().__init__(cible)
        self._texte: str = texte
        self._auteur: UtilisateurSysteme = auteur

    @property
    def libelle(self) -> str:
        return f"Ajouter le commentaire « {self._texte} » au ticket #{self.cible.ticketID}"

    def executer(self) -> None:
        self.cible.addComment(self._texte, self._auteur)
