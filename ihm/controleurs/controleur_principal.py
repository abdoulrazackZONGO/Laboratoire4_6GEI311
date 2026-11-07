"""Contrôleur principal : navigation entre les fenêtres et sessions ouvertes sur le serveur."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
from typing import TYPE_CHECKING

from ihm.controleurs.controleur_admin import ControleurAdmin
from ihm.controleurs.controleur_user import ControleurUser
from ihm.passerelle.client_api import URL_PAR_DEFAUT, ClientAPI
from ihm.passerelle.erreurs import EXCEPTIONS_PASSERELLE
from ihm.passerelle.objets_lecture import ActeurLu
from ihm.passerelle.source_tickets import SourceTickets
from ihm.vues.vue_connexion import VueConnexion
from ihm.vues.vue_liste_admin import VueListeAdmin
from ihm.vues.vue_liste_user import VueListeUser
from ihm.vues.vue_lot import VueLot
from ihm.vues.vue_rapport import VueRapport

if TYPE_CHECKING:
    from ihm.passerelle.client_api import Transport
    from ihm.passerelle.objets_lecture import RapportLu, TicketLu, TicketRefLu

TITRE_APPLICATION = "Gestion des tickets"

# Rythme du sondage de GET /version : ce qui remplace le patron Observateur entre la GUI
# et le serveur. Une seconde suffit pour voir le changement fait par une autre GUI.
INTERVALLE_SONDAGE_MS = 1000


class ControleurPrincipal:
    """Seul contrôleur qui crée des fenêtres ; ne détient aucune donnée persistante.

    Le dépôt et sa sauvegarde vivent dans le serveur. Chaque session ouverte depuis F1 a sa
    propre ClientAPI (l'en-tête X-Acteur-Id de son acteur) et sa propre SourceTickets, que
    les fenêtres de la session observent. Une seule boucle after() les sonde toutes.
    """

    def __init__(
        self, racine: tk.Tk, url: str = URL_PAR_DEFAUT, *, transport: Transport | None = None
    ) -> None:
        self._racine: tk.Tk = racine
        self._url: str = url
        self._transport: Transport | None = transport
        # Sans acteur : seules les routes publiques (annuaire) lui sont permises.
        self._annuaire: ClientAPI = ClientAPI(url, transport=transport)
        self._acteurs: list[ActeurLu] = []
        self._sources: list[SourceTickets] = []
        self._connexion: VueConnexion | None = None
        self._sondage: str | None = None
        # Vrai après un sondage raté : on ne prévient qu'une fois, pas chaque seconde.
        self._serveurPerdu: bool = False

    @property
    def url(self) -> str:
        return self._url

    @property
    def acteurs(self) -> list[ActeurLu]:
        """Annuaire lu au démarrage (GET /acteurs) : il ne change pas pendant l'exécution."""
        return list(self._acteurs)

    # ------------------------------------------------------------------ cycle de vie

    def demarrer(self) -> bool:
        """Lit l'annuaire du serveur puis ouvre F1 ; sans serveur, propose de réessayer.

        Rend faux si l'utilisateur renonce : l'application est alors déjà fermée.
        """
        while True:
            try:
                self._acteurs = [ActeurLu.depuisJSON(a) for a in self._annuaire.listerActeurs()]
                break
            except EXCEPTIONS_PASSERELLE as erreur:
                if not messagebox.askretrycancel(
                    TITRE_APPLICATION, str(erreur),
                    detail=f"Lancez le serveur (python serveur.py), puis réessayez.\n"
                           f"Adresse utilisée : {self._url}",
                    icon="error", parent=self._racine,
                ):
                    self._racine.destroy()
                    return False
        self._connexion = VueConnexion(self._racine, self)
        return True

    def quitter(self) -> None:
        """Arrête le sondage et ferme l'application.

        Rien à sauvegarder : chaque action a déjà été enregistrée par le serveur.
        """
        if self._sondage is not None:
            self._racine.after_cancel(self._sondage)
            self._sondage = None
        self._racine.destroy()

    # ------------------------------------------------------------------ données

    def utilisateurs(self) -> list[ActeurLu]:
        """Acteurs de rôle User (choix de l'assigné dans F7)."""
        return [acteur for acteur in self._acteurs if acteur.role == "User"]

    # ------------------------------------------------------------------ sessions et sondage

    def ouvrirSession(self, acteur: ActeurLu) -> None:
        """Crée la ClientAPI et la SourceTickets de l'acteur, puis ouvre sa liste (F2 ou F3).

        La source est chargée avant d'ouvrir la fenêtre : si le serveur ne répond pas,
        F1 affiche l'erreur et aucune fenêtre vide ne reste ouverte.
        """
        client = ClientAPI(self._url, acteur.id, transport=self._transport)
        source = SourceTickets(client)
        source.rafraichir()
        if acteur.role == "Admin":
            VueListeAdmin(self._racine, ControleurAdmin(self, acteur, client, source))
        elif acteur.role == "User":
            VueListeUser(self._racine, ControleurUser(self, acteur, client, source))
        else:
            return
        self._sources.append(source)
        self._demarrerSondage()

    def _demarrerSondage(self) -> None:
        if self._sondage is None:
            self._sondage = self._racine.after(INTERVALLE_SONDAGE_MS, self._sonder)

    def _sonder(self) -> None:
        """Chaque source encore observée relit /version, et les tickets s'il a changé.

        Une source dont toutes les fenêtres sont fermées n'a plus d'abonné : elle est oubliée,
        et la boucle s'arrête quand il n'en reste aucune. Le tour suivant est planifié avant
        de sonder, pour qu'une erreur n'arrête pas la boucle.
        """
        self._sondage = None
        self._sources = [source for source in self._sources if source.nombreObservateurs > 0]
        if not self._sources:
            return
        self._demarrerSondage()
        try:
            for source in list(self._sources):
                source.verifierVersion()
        except EXCEPTIONS_PASSERELLE as erreur:
            if not self._serveurPerdu:
                self._serveurPerdu = True
                messagebox.showerror(
                    TITRE_APPLICATION, str(erreur),
                    detail="Les listes ne sont plus à jour. Elles se mettront à jour "
                           "d'elles-mêmes dès que le serveur répondra de nouveau.",
                    parent=self._racine,
                )
            return
        self._serveurPerdu = False

    # ------------------------------------------------------------------ navigation

    def ouvrirLot(self, controleur: ControleurAdmin, action: str, tickets: list[TicketLu]) -> None:
        VueLot(self._racine, controleur, action, tickets)

    def afficherRapport(self, rapport: RapportLu, libelle: str) -> None:
        VueRapport(self._racine, rapport, libelle)

    # Fenêtres pas encore reliées au serveur : F4 et F5 (création et édition par brouillons)
    # et F6 (détail, qui télécharge les images). Un message remplace leur ouverture.

    def ouvrirCreation(self, user: ActeurLu) -> None:
        self._fenetreNonReliee("La création d'un ticket")

    def ouvrirEdition(self, user: ActeurLu, ticket: TicketRefLu) -> None:
        self._fenetreNonReliee("L'édition d'un ticket")

    def ouvrirDetail(self, tickets: list[TicketLu], index: int) -> None:
        self._fenetreNonReliee("Le détail d'un ticket")

    def _fenetreNonReliee(self, fonction: str) -> None:
        messagebox.showinfo(
            TITRE_APPLICATION, f"{fonction} n'est pas encore reliée au serveur.",
            detail="Cette fenêtre sera branchée sur l'API à une prochaine étape.",
            parent=self._racine,
        )
