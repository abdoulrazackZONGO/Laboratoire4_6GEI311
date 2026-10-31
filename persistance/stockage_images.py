"""Copie des images jointes dans le dossier de l'application."""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from modele.exceptions import ArtefactInvalideException


class StockageImages:
    """Copie les images jointes aux tickets dans le dossier de l'application.

    La description garde le chemin de la copie : l'image reste disponible même si
    l'utilisateur déplace ou supprime son fichier d'origine.
    """

    _EXTENSIONS: tuple[str, ...] = (".png", ".gif")

    def __init__(self, dossier: str = "donnees/images") -> None:
        self._dossier: Path = Path(dossier)

    def copier(self, chemin: str) -> str:
        """Copie une image .png ou .gif sous un nom unique et retourne le chemin de la copie.

        Le chemin retourné est en notation POSIX, relatif comme le dossier de stockage
        (cas par défaut), et utilisable tel quel par session.ajouterElement("image", ...).
        """
        source = Path(chemin)
        if not source.is_file():
            raise ArtefactInvalideException(f"Image introuvable : {chemin}")
        if source.suffix.lower() not in self._EXTENSIONS:
            raise ArtefactInvalideException(
                f"Format d'image non pris en charge : '{source.name}'. Formats acceptés : .png, .gif"
            )
        self._dossier.mkdir(parents=True, exist_ok=True)
        # Préfixe aléatoire : deux copies du même fichier ne s'écrasent jamais.
        copie = self._dossier / f"{uuid.uuid4().hex[:8]}_{source.name}"
        while copie.exists():
            copie = self._dossier / f"{uuid.uuid4().hex[:8]}_{source.name}"
        shutil.copy2(source, copie)
        return copie.as_posix()

    def supprimer(self, chemin: str) -> None:
        """Supprime une copie du dossier de stockage, jamais une image d'origine.

        Sans effet si le fichier n'existe pas ou s'il est hors du dossier de stockage.
        """
        cible = Path(chemin).resolve()
        if cible.is_file() and cible.is_relative_to(self._dossier.resolve()):
            cible.unlink()
