"""Copie des images jointes dans le dossier de l'application."""
from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path, PureWindowsPath

from modele.exceptions import ArtefactInvalideException


class StockageImages:
    """Copie les images jointes aux tickets dans le dossier de l'application.

    La description garde le chemin de la copie : l'image reste disponible même si
    l'utilisateur déplace ou supprime son fichier d'origine.
    """

    _EXTENSIONS: tuple[str, ...] = (".png", ".gif")
    # Interdits dans un nom de fichier sous Windows, plus les surrogates isolés, que ni le
    # disque ni le JSON ne savent écrire en UTF-8.
    _CARACTERES_INTERDITS: re.Pattern[str] = re.compile(r'[<>:"/\\|?*\x00-\x1f\ud800-\udfff]')
    _LONGUEUR_NOM_MAX: int = 100

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

    def enregistrer(self, nomFichier: str, octets: bytes) -> str:
        """Écrit des octets reçus sous un nom unique et retourne le chemin de la copie.

        Mêmes contrôles et même forme de chemin que copier(). Mais ce nom vient d'un client,
        pas d'un fichier qui existe : il est d'abord ramené à un nom sûr pour le disque.
        """
        nom = self._nomSur(nomFichier)
        if Path(nom).suffix.lower() not in self._EXTENSIONS:
            raise ArtefactInvalideException(
                f"Format d'image non pris en charge : '{nom}'. Formats acceptés : .png, .gif"
            )
        self._dossier.mkdir(parents=True, exist_ok=True)
        # Préfixe aléatoire : deux envois du même fichier ne s'écrasent jamais.
        copie = self._dossier / f"{uuid.uuid4().hex[:8]}_{nom}"
        while copie.exists():
            copie = self._dossier / f"{uuid.uuid4().hex[:8]}_{nom}"
        copie.write_bytes(octets)
        return copie.as_posix()

    def _nomSur(self, nomFichier: str) -> str:
        """Dernier segment du nom, sans caractère interdit, à l'extension conservée.

        PureWindowsPath coupe aussi sur / et sur « C: », quel que soit le système du serveur :
        ../../x.png, ..\\..\\x.png et a:b.png ne peuvent pas sortir du dossier de stockage.
        """
        nom = self._CARACTERES_INTERDITS.sub("_", PureWindowsPath(nomFichier).name)
        if len(nom) <= self._LONGUEUR_NOM_MAX:
            return nom
        suffixe = Path(nom).suffix
        return nom[: self._LONGUEUR_NOM_MAX - len(suffixe)] + suffixe

    def supprimer(self, chemin: str) -> None:
        """Supprime une copie du dossier de stockage, jamais une image d'origine.

        Sans effet si le fichier n'existe pas ou s'il est hors du dossier de stockage.
        """
        cible = Path(chemin).resolve()
        if cible.is_file() and cible.is_relative_to(self._dossier.resolve()):
            cible.unlink()
