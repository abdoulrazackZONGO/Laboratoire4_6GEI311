from __future__ import annotations

from description.element_description import ElementDescription


class DescriptionTexte(ElementDescription):
    """Artefact texte : le contenu est lu en entier au chargement."""

    def charger(self) -> None:
        with open(self.chemin, encoding="utf-8") as fichier:
            self._contenu: str = fichier.read()

    @property
    def typeArtefact(self) -> str:
        return "texte"

    @property
    def contenu(self) -> str:
        """Texte chargé, disponible après traiter()."""
        return self._contenu

    @property
    def resume(self) -> str:
        return f"[Texte] {self._nom} ({len(self._contenu)} caractères)"
