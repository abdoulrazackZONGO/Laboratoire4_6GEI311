"""Fenêtre de base : observatrice du modèle et affichage des refus métier."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
from typing import TYPE_CHECKING, Any, Callable, TypeVar

from modele.exceptions import (
    AccesRefuseException,
    ArtefactInvalideException,
    SessionIndisponibleException,
    SuppressionInterditeException,
    TransitionInvalideException,
)
from modele.observateur import ObservateurTickets

if TYPE_CHECKING:
    from modele.observateur import SujetTickets
    from modele.ticket import Ticket

R = TypeVar("R")

# Les cinq exceptions métier : un refus normal, affiché à l'utilisateur.
# Toute autre exception est un bug et doit rester visible dans la console.
EXCEPTIONS_METIER: tuple[type[Exception], ...] = (
    TransitionInvalideException,
    SessionIndisponibleException,
    AccesRefuseException,
    SuppressionInterditeException,
    ArtefactInvalideException,
)


class FenetreBase(tk.Toplevel, ObservateurTickets):
    """Fenêtre abonnée à ses sujets de l'ouverture à la fermeture (patron Observateur).

    Sans désabonnement, un sujet notifierait une fenêtre détruite et tkinter
    lèverait TclError : fermer() se désabonne donc avant de détruire.
    """

    def __init__(self, parent: tk.Misc, titre: str, sujets: list[SujetTickets]) -> None:
        super().__init__(parent)
        self.title(titre)
        self._sujets: list[SujetTickets] = list(sujets)
        for sujet in self._sujets:
            sujet.abonner(self)
        self.protocol("WM_DELETE_WINDOW", self.fermer)

    def ticketModifie(self, ticket: Ticket) -> None:
        self.rafraichir()

    def ticketAjoute(self, ticket: Ticket) -> None:
        self.rafraichir()

    def ticketRetire(self, ticket: Ticket) -> None:
        self.rafraichir()

    def rafraichir(self) -> None:
        """À redéfinir : relit le modèle et met l'affichage à jour."""

    def fermer(self) -> None:
        """Se désabonne de tous ses sujets, puis détruit la fenêtre."""
        for sujet in self._sujets:
            sujet.desabonner(self)
        self.destroy()

    def executer(self, fonction: Callable[..., R], *args: Any) -> R | None:
        """Appelle fonction(*args) ; un refus métier est affiché et donne None."""
        try:
            return fonction(*args)
        except EXCEPTIONS_METIER as erreur:
            messagebox.showerror("Opération refusée", str(erreur), parent=self)
            return None
