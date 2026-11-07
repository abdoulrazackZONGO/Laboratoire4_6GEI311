"""Registre des brouillons : ce que ControleurEdition gardait pour chaque session, côté serveur.

Un brouillon de l'API est une session du modèle, plus ce que la session ne garde pas : son
identifiant, son propriétaire, le texte tapé pendant la pause et la pile des copies d'images.
Le registre ne décide rien : ce qui est permis reste l'affaire de la session, qui lève ses
exceptions. Il ne connaît ni Flask ni les fichiers. Il s'utilise sous le verrou du contexte.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from acteurs.user import User
    from sessions.session_edition import SessionEdition


class EntreeBrouillon:
    """Une session ouverte et ce qui l'accompagne.

    La pile des copies est alignée sur la pile de la session : le chemin de la copie pour
    une image, None pour un commentaire ou un texte. Un undo ou un abandon sait ainsi
    quelle copie est devenue inutile.
    """

    def __init__(
        self, id: int, session: SessionEdition, proprietaire: User, estCreation: bool
    ) -> None:
        self._id: int = id
        self._session: SessionEdition = session
        self._proprietaire: User = proprietaire
        self._estCreation: bool = estCreation
        self._texteBrouillon: str = ""
        self._copies: list[str | None] = []

    @property
    def id(self) -> int:
        return self._id

    @property
    def session(self) -> SessionEdition:
        return self._session

    @property
    def proprietaire(self) -> User:
        return self._proprietaire

    @property
    def estCreation(self) -> bool:
        """Fixé à l'ouverture : après application, le ticket est dans le dépôt, comme en édition."""
        return self._estCreation

    @property
    def texteBrouillon(self) -> str:
        """Texte tapé et gardé pendant la pause ; ce n'est pas encore une modification."""
        return self._texteBrouillon

    @property
    def copies(self) -> list[str | None]:
        return list(self._copies)

    @property
    def nombreImages(self) -> int:
        """Images en attente : F5 grise « Créer le ticket » s'il n'y a ni texte ni image."""
        return sum(1 for copie in self._copies if copie is not None)

    def garderTexte(self, texte: str) -> None:
        self._texteBrouillon = texte

    def empilerCopie(self, copie: str | None) -> None:
        """À appeler après un ajout accepté par la session ; None s'il n'y a pas d'image."""
        self._copies.append(copie)

    def depilerCopie(self) -> str | None:
        """À appeler après session.annulerDerniere(), qui refuse d'abord une pile vide."""
        return self._copies.pop()

    def viderCopies(self) -> list[str]:
        """Vide la pile et rend les copies qu'elle citait : à supprimer après un abandon."""
        copies = [copie for copie in self._copies if copie is not None]
        self._copies.clear()
        return copies


class RegistreBrouillons:
    """brouillonId -> session : les brouillons ouverts de tous les acteurs.

    Les identifiants croissent et ne servent qu'une fois, pour qu'un client qui garde un
    ancien identifiant reçoive 404 au lieu de tomber sur un autre brouillon. Ils repartent
    de 1 au redémarrage du serveur : les brouillons ne sont pas sauvegardés (voir DepotJSON).
    """

    def __init__(self) -> None:
        self._dernierId: int = 0
        self._entrees: dict[int, EntreeBrouillon] = {}

    def ouvrir(
        self, session: SessionEdition, proprietaire: User, estCreation: bool
    ) -> EntreeBrouillon:
        """Inscrit une session que le modèle vient d'ouvrir."""
        self._oublierFermees()
        self._dernierId += 1
        entree = EntreeBrouillon(self._dernierId, session, proprietaire, estCreation)
        self._entrees[entree.id] = entree
        return entree

    def trouver(self, acteurId: int, brouillonId: int) -> EntreeBrouillon | None:
        """Brouillon ouvert de cet acteur ; celui d'un autre acteur n'existe pas pour lui."""
        self._oublierFermees()
        entree = self._entrees.get(brouillonId)
        if entree is None or entree.proprietaire.id != acteurId:
            return None
        return entree

    def brouillonsDe(self, acteurId: int) -> list[EntreeBrouillon]:
        """Brouillons ouverts de cet acteur, en pause ou non, dans l'ordre d'ouverture."""
        self._oublierFermees()
        return [e for e in self._entrees.values() if e.proprietaire.id == acteurId]

    def _oublierFermees(self) -> None:
        """Purge paresseuse, comme ControleurPrincipal : la session sait si elle est ouverte."""
        for brouillonId in [i for i, e in self._entrees.items() if not e.session.estOuverte]:
            del self._entrees[brouillonId]
