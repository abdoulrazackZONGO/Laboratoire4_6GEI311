"""Fenêtre de base : observatrice de la source des tickets et affichage des refus."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
from typing import TYPE_CHECKING, Any, Callable, TypeVar

from ihm.passerelle.erreurs import EXCEPTIONS_PASSERELLE, ServeurInjoignable
from modele.exceptions import (
    AccesRefuseException,
    ArtefactInvalideException,
    SessionIndisponibleException,
    SuppressionInterditeException,
    TransitionInvalideException,
)
from modele.observateur import ObservateurTickets

if TYPE_CHECKING:
    from ihm.passerelle.objets_lecture import TicketLu
    from modele.observateur import SujetTickets

R = TypeVar("R")

# Les cinq exceptions métier, reconstruites par la passerelle à partir de la réponse du
# serveur : un refus normal, affiché à l'utilisateur.
EXCEPTIONS_METIER: tuple[type[Exception], ...] = (
    TransitionInvalideException,
    SessionIndisponibleException,
    AccesRefuseException,
    SuppressionInterditeException,
    ArtefactInvalideException,
)
# S'y ajoutent les erreurs de la passerelle : serveur injoignable, et erreurs propres à l'API
# (requête invalide, ressource introuvable, panne du serveur).
EXCEPTIONS_AFFICHEES: tuple[type[Exception], ...] = EXCEPTIONS_METIER + EXCEPTIONS_PASSERELLE


def titreErreur(erreur: Exception) -> str:
    """Titre de la boîte d'erreur : refus métier, serveur arrêté ou autre erreur de l'API."""
    if isinstance(erreur, EXCEPTIONS_METIER):
        return "Opération refusée"
    if isinstance(erreur, ServeurInjoignable):
        return "Serveur injoignable"
    return "Erreur du serveur"


class FenetreBase(tk.Toplevel, ObservateurTickets):
    """Fenêtre abonnée à ses sujets de l'ouverture à la fermeture (patron Observateur).

    Le sujet est la SourceTickets de la session : elle notifie quand le serveur a changé.
    Sans désabonnement, la source notifierait une fenêtre détruite et tkinter lèverait
    TclError : fermer() se désabonne donc avant de détruire.
    """

    def __init__(self, parent: tk.Misc, titre: str, sujets: list[SujetTickets]) -> None:
        super().__init__(parent)
        self.title(titre)
        self._sujets: list[SujetTickets] = list(sujets)
        for sujet in self._sujets:
            sujet.abonner(self)
        self.protocol("WM_DELETE_WINDOW", self.fermer)

    def ticketModifie(self, ticket: TicketLu) -> None:  # type: ignore[override]
        self.rafraichir()

    def ticketAjoute(self, ticket: TicketLu) -> None:  # type: ignore[override]
        self.rafraichir()

    def ticketRetire(self, ticket: TicketLu) -> None:  # type: ignore[override]
        self.rafraichir()

    def rafraichir(self) -> None:
        """À redéfinir : relit les données et met l'affichage à jour."""

    def fermer(self) -> None:
        """Se désabonne de tous ses sujets, puis détruit la fenêtre."""
        for sujet in self._sujets:
            sujet.desabonner(self)
        self.destroy()

    def executer(self, fonction: Callable[..., R], *args: Any) -> R | None:
        """Appelle fonction(*args) ; un refus ou une erreur du serveur est affiché et donne None.

        Toute autre exception est un bogue du client : elle reste visible dans la console.
        """
        try:
            return fonction(*args)
        except EXCEPTIONS_AFFICHEES as erreur:
            messagebox.showerror(titreErreur(erreur), str(erreur), parent=self)
            return None

