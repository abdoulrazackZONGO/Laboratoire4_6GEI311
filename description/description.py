from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from description.element_description import ElementDescription


class Description:
    """Description d'un ticket : liste ordonnée d'éléments."""

    def __init__(self) -> None:
        self._elements: list[ElementDescription] = []

    def ajouterElement(self, element: ElementDescription) -> None:
        self._elements.append(element)

    @property
    def elements(self) -> list[ElementDescription]:
        return list(self._elements)

    @property
    def nombreElements(self) -> int:
        return len(self._elements)

    def afficher(self) -> None:
        """MÉTHODE D'AFFICHAGE : résumé numéroté de chaque élément."""
        for numero, element in enumerate(self._elements, start=1):
            print(f"  {numero}. {element.resume}")
