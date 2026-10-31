"""Contrôleur de l'éditeur de description (F5) : sans tkinter, testable sans écran."""
from __future__ import annotations

from typing import TYPE_CHECKING

from modele.exceptions import ArtefactInvalideException

if TYPE_CHECKING:
    from ihm.controleurs.controleur_principal import ControleurPrincipal
    from sessions.session_edition import SessionEdition


class ControleurEdition:
    """Un seul par session (registre du ControleurPrincipal) : survit à la fermeture de F5.

    Il garde le texte tapé pendant la pause et la pile des copies d'images, alignée
    sur la pile de la session : le chemin de la copie pour une image, None pour un
    commentaire. Un undo ou un abandon supprime ainsi la copie devenue inutile.
    """

    def __init__(self, principal: ControleurPrincipal, session: SessionEdition) -> None:
        self._principal: ControleurPrincipal = principal
        self._session: SessionEdition = session
        # Calculé une seule fois : après appliquer(), le ticket entre dans le dépôt
        # et le test basculerait.
        self._estCreation: bool = not principal.systeme.contient(session.ticket)
        self._texteBrouillon: str = ""
        self._copies: list[str | None] = []

    @property
    def session(self) -> SessionEdition:
        return self._session

    @property
    def estCreation(self) -> bool:
        """Vrai pour une session de création : son ticket était hors du dépôt."""
        return self._estCreation

    @property
    def texteBrouillon(self) -> str:
        """Texte tapé dans F5, gardé pendant la pause."""
        return self._texteBrouillon

    @property
    def nombreImages(self) -> int:
        """Images en attente : F5 grise « Créer le ticket » s'il n'y a ni texte ni image."""
        return sum(1 for copie in self._copies if copie is not None)

    def ajouterImages(self, chemins: list[str]) -> list[str]:
        """Agrégat : ajoute chaque image et retourne les messages des images refusées."""
        refus: list[str] = []
        for chemin in chemins:
            copie: str | None = None
            try:
                copie = self._principal.stockage.copier(chemin)
                self._session.ajouterElement("image", copie)
            except ArtefactInvalideException as erreur:
                self._supprimerCopie(copie)
                refus.append(str(erreur))
            except Exception:
                # Session en pause ou fermée : le refus remonte, sans laisser de copie orpheline.
                self._supprimerCopie(copie)
                raise
            else:
                self._copies.append(copie)
        return refus

    def commenter(self, texte: str) -> None:
        self._session.ajouterCommentaire(texte)
        self._copies.append(None)

    def annulerDerniere(self) -> str:
        """Retire la dernière modification en attente et supprime sa copie d'image."""
        libelle = self._session.annulerDerniere()
        self._supprimerCopie(self._copies.pop())
        return libelle

    def mettreEnPause(self, texte: str) -> None:
        """Le texte n'entre pas dans la session : il est gardé jusqu'à la reprise."""
        self._texteBrouillon = texte
        self._session.mettreEnPause()

    def abandonner(self) -> None:
        self._session.abandonner()
        for copie in self._copies:
            self._supprimerCopie(copie)
        self._copies.clear()
        self._texteBrouillon = ""

    def appliquer(self, texte: str) -> None:
        """Ajoute le texte tapé à la description, applique, puis affiche le rapport."""
        texteAjoute = bool(texte.strip())
        if texteAjoute:
            self._session.ajouterTexteSaisi(texte.strip())
        try:
            rapport = self._session.appliquer()
        except Exception:
            # Le texte est retiré pour ne pas être ajouté deux fois au prochain essai.
            if texteAjoute:
                self._session.annulerDerniere()
            raise
        self._copies.clear()
        self._texteBrouillon = ""
        self._principal.afficherRapport(rapport, self._session.libelle)

    def _supprimerCopie(self, copie: str | None) -> None:
        if copie is not None:
            self._principal.stockage.supprimer(copie)
