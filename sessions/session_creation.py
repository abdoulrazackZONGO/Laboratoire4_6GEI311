from __future__ import annotations

from typing import TYPE_CHECKING

from modele.exceptions import SessionIndisponibleException
from sessions.session_edition import SessionEdition

if TYPE_CHECKING:
    from acteurs.user import User
    from sessions.rapport_execution import RapportExecution


class SessionCreation(SessionEdition):
    """Création d'un ticket : il n'entre dans le dépôt qu'à appliquer()."""

    # Restreint le type du propriétaire hérité : une création appartient toujours à un User.
    _proprietaire: User

    @property
    def libelle(self) -> str:
        return "Session de création"

    def appliquer(self) -> RapportExecution:
        """Vérifie tout d'abord, puis crée le ticket et applique sa description."""
        # Toutes les vérifications avant createTicket() : un refus laisse le ticket hors du dépôt.
        if self._appliquee:
            raise SessionIndisponibleException(
                f"{self.libelle} : application déjà effectuée"
            )
        self._refuserSiAbandonnee("application")
        if self._enPause:
            raise SessionIndisponibleException(
                f"{self.libelle} en pause : application impossible"
            )
        self._proprietaire.createTicket(self._ticket)
        return super().appliquer()
