from __future__ import annotations

from typing import TYPE_CHECKING

from description.description_image import DescriptionImage
from description.description_texte import DescriptionTexte
from description.description_texte_saisi import DescriptionTexteSaisi
from description.description_video import DescriptionVideo
from modele.exceptions import ArtefactInvalideException

if TYPE_CHECKING:
    from description.element_description import ElementDescription


class FabriqueDescription:
    """Fabrique des éléments de description (patron Factory Method)."""

    @staticmethod
    def creer(type_artefact: str, chemin: str) -> ElementDescription:
        """Crée l'élément correspondant au type, sans le charger."""
        if type_artefact == "texte":
            return DescriptionTexte(chemin)
        if type_artefact == "image":
            return DescriptionImage(chemin)
        if type_artefact == "video":
            return DescriptionVideo(chemin)
        raise ArtefactInvalideException(
            f"Type d'artefact inconnu : '{type_artefact}'. "
            "Types acceptés : texte, image, video"
        )

    @staticmethod
    def creerSaisie(texte: str) -> ElementDescription:
        """Crée un élément à partir d'un texte tapé, sans le charger."""
        return DescriptionTexteSaisi(texte)
