from __future__ import annotations

from description.description_texte import DescriptionTexte
from modele.exceptions import ArtefactInvalideException


class DescriptionTexteSaisi(DescriptionTexte):
    """Texte tapé par l'utilisateur, sans fichier : typeArtefact et contenu sont hérités."""

    def __init__(self, texte: str) -> None:
        # Pas de fichier : chemin vide.
        super().__init__("")
        self._texte: str = texte

    def validerChemin(self) -> None:
        """Faute de fichier, c'est le texte saisi qui doit être non vide."""
        if not self._texte.strip():
            raise ArtefactInvalideException("Texte saisi vide")

    def charger(self) -> None:
        self._contenu = self._texte

    def preparerAffichage(self) -> None:
        self._nom = "texte saisi"
