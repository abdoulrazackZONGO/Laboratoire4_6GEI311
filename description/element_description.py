from __future__ import annotations

import os
import typing
from abc import ABC, abstractmethod

from modele.exceptions import ArtefactInvalideException


class ElementDescription(ABC):
    """Élément de description d'un ticket (patron Template Method)."""

    def __init__(self, chemin: str) -> None:
        self._chemin: str = chemin

    @property
    def chemin(self) -> str:
        return self._chemin

    @typing.final
    def traiter(self) -> None:
        """Méthode patron : l'ordre des étapes est fixe."""
        self.validerChemin()
        self.charger()
        self.preparerAffichage()

    def validerChemin(self) -> None:
        """Étape commune : le fichier doit exister."""
        if not os.path.isfile(self._chemin):
            raise ArtefactInvalideException(f"Fichier introuvable : {self._chemin}")

    @abstractmethod
    def charger(self) -> None:
        """Seule étape de traitement qui varie selon le type d'artefact."""

    def preparerAffichage(self) -> None:
        """Étape par défaut : mémorise le nom du fichier pour l'affichage."""
        self._nom: str = os.path.basename(self._chemin)

    @property
    @abstractmethod
    def typeArtefact(self) -> str:
        """Type d'artefact : "texte", "image" ou "video", comme dans FabriqueDescription.creer()."""

    @property
    @abstractmethod
    def resume(self) -> str:
        """Résumé lisible de l'élément."""
