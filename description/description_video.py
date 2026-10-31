from __future__ import annotations

import os

from description.element_description import ElementDescription


class DescriptionVideo(ElementDescription):
    """Artefact vidéo à chargement différé : seules les métadonnées sont lues au chargement."""

    def charger(self) -> None:
        # Chargement différé : on ne lit que la taille, le contenu reste None.
        self._taille: int = os.path.getsize(self.chemin)
        self._contenu: bytes | None = None

    def chargerContenuReel(self) -> None:
        """Lit réellement le contenu binaire de la vidéo."""
        with open(self.chemin, "rb") as fichier:
            self._contenu = fichier.read()

    @property
    def estCharge(self) -> bool:
        return self._contenu is not None

    @property
    def typeArtefact(self) -> str:
        return "video"

    @property
    def resume(self) -> str:
        charge = "oui" if self.estCharge else "non"
        return f"[Vidéo] {self._nom} ({self._taille} octets, contenu chargé : {charge})"
