"""Patron Observateur : les vues sont prévenues quand un ticket change."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from modele.ticket import Ticket


class ObservateurTickets:
    """Interface des observateurs de tickets (les vues, typiquement).

    Les trois méthodes ne font rien par défaut : un observateur ne redéfinit
    que les notifications qui l'intéressent. Une fenêtre de détail n'écoute
    que ticketModifie ; une liste écoute aussi les ajouts et les retraits.
    """

    def ticketModifie(self, ticket: Ticket) -> None:
        """Le ticket a changé : état, assigné, commentaires ou description."""

    def ticketAjoute(self, ticket: Ticket) -> None:
        """Un ticket vient d'entrer dans le dépôt."""

    def ticketRetire(self, ticket: Ticket) -> None:
        """Un ticket vient de sortir du dépôt."""


class SujetTickets:
    """Sujet observable : tient la liste des abonnés et les notifie.

    Un observateur doit se désabonner quand il disparaît (fenêtre fermée) ;
    sinon il continue d'être appelé et reste en mémoire. C'est le compromis
    classique du patron Observateur.
    """

    def __init__(self) -> None:
        self._observateurs: list[ObservateurTickets] = []

    @property
    def nombreObservateurs(self) -> int:
        return len(self._observateurs)

    def abonner(self, observateur: ObservateurTickets) -> None:
        """Abonnement idempotent : un même observateur n'est notifié qu'une fois."""
        if observateur not in self._observateurs:
            self._observateurs.append(observateur)

    def desabonner(self, observateur: ObservateurTickets) -> None:
        """Sans effet si l'observateur n'est pas abonné."""
        if observateur in self._observateurs:
            self._observateurs.remove(observateur)

    # Les notifications parcourent une copie de la liste : un observateur
    # peut ainsi se désabonner pendant qu'il est notifié.

    def _notifierModification(self, ticket: Ticket) -> None:
        for observateur in list(self._observateurs):
            observateur.ticketModifie(ticket)

    def _notifierAjout(self, ticket: Ticket) -> None:
        for observateur in list(self._observateurs):
            observateur.ticketAjoute(ticket)

    def _notifierRetrait(self, ticket: Ticket) -> None:
        for observateur in list(self._observateurs):
            observateur.ticketRetire(ticket)
