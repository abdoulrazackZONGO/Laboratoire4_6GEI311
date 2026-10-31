from __future__ import annotations

from typing import TYPE_CHECKING

from commandes.commande import Commande

if TYPE_CHECKING:
    from description.element_description import ElementDescription
    from modele.ticket import Ticket


class CommandeAjouterElement(Commande):
    """Ajoute un élément à la description du ticket cible."""

    def __init__(self, cible: Ticket, element: ElementDescription) -> None:
        super().__init__(cible)
        self._element: ElementDescription = element

    @property
    def libelle(self) -> str:
        return f"Ajouter l'élément {self._element.resume} au ticket #{self.cible.ticketID}"

    def executer(self) -> None:
        # Passe par le ticket pour que l'ajout soit notifié aux observateurs.
        self.cible.ajouterElementDescription(self._element)
