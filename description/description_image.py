from __future__ import annotations

from description.element_description import ElementDescription


class DescriptionImage(ElementDescription):
    """Artefact image : les octets sont lus en entier au chargement."""

    def charger(self) -> None:
        with open(self.chemin, "rb") as fichier:
            self._octets: bytes = fichier.read()

    @property
    def typeArtefact(self) -> str:
        return "image"

    @property
    def resume(self) -> str:
        return f"[Image] {self._nom} ({len(self._octets)} octets)"
