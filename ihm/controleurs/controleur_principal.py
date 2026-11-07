"""Contrôleur principal : navigation entre les fenêtres et sessions ouvertes sur le serveur."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
from typing import TYPE_CHECKING, Callable

from ihm.controleurs.controleur_admin import ControleurAdmin
from ihm.controleurs.controleur_edition import ControleurEdition
from ihm.controleurs.controleur_user import ControleurUser
from ihm.passerelle.client_api import URL_PAR_DEFAUT, ClientAPI
from ihm.passerelle.erreurs import EXCEPTIONS_PASSERELLE
from ihm.passerelle.objets_lecture import ActeurLu, BrouillonLu
from ihm.passerelle.source_tickets import SourceTickets
from ihm.vues.vue_connexion import VueConnexion
from ihm.vues.vue_edition import VueEdition
from ihm.vues.vue_liste_admin import VueListeAdmin
from ihm.vues.vue_liste_user import VueListeUser
from ihm.vues.vue_lot import VueLot
from ihm.vues.vue_nouveau_ticket import VueNouveauTicket
from ihm.vues.vue_rapport import VueRapport

if TYPE_CHECKING:
    from ihm.passerelle.client_api import Transport
    from ihm.passerelle.objets_lecture import RapportLu, TicketLu, TicketRefLu
    from modele.enums import Priorite

TITRE_APPLICATION = "Gestion des tickets"

# Rythme du sondage de GET /version : ce qui remplace le patron Observateur entre la GUI
# et le serveur. Une seconde suffit pour voir le changement fait par une autre GUI.
INTERVALLE_SONDAGE_MS = 1000


class ControleurPrincipal:
    """Seul contrôleur qui crée des fenêtres ; ne détient aucune donnée persistante.

    Le dépôt et sa sauvegarde vivent dans le serveur. Chaque session ouverte depuis F1 a sa
    propre ClientAPI (l'en-tête X-Acteur-Id de son acteur) et sa propre SourceTickets, que
    les fenêtres de la session observent. Une seule boucle after() les sonde toutes.

    Les brouillons ne changent pas /version (ils ne sont pas dans le dépôt) : après une
    action de F4 ou F5, signalerBrouillons() prévient les F3 ouvertes, qui les relisent.
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
        # Session ouverte de chaque acteur : F4 et F5 passent par le client et la source de
        # l'utilisateur qui les a ouvertes.
        self._sessions: dict[int, tuple[ClientAPI, SourceTickets]] = {}
        # Un seul ControleurEdition par brouillon : la fenêtre sert à ramener F5 devant (lift).
        self._editions: dict[int, tuple[ControleurEdition, VueEdition]] = {}
        self._ecouteursBrouillons: list[Callable[[], None]] = []
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
        self._sessions[acteur.id] = (client, source)
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

    def ouvrirCreation(self, user: ActeurLu) -> None:
        VueNouveauTicket(self._racine, self, user)

    def commencerCreation(self, user: ActeurLu, titre: str, priorite: Priorite) -> None:
        """Ouvre un brouillon de création (le serveur réserve le numéro du ticket), puis F5."""
        client, source = self._session(user)
        brouillon = BrouillonLu.depuisJSON(client.ouvrirBrouillonCreation(titre, priorite))
        self._afficherEdition(client, source, brouillon)
        self.signalerBrouillons()

    def ouvrirEdition(self, user: ActeurLu, ticket: TicketRefLu) -> None:
        """Reprend le brouillon ouvert sur ce ticket, même en pause, ou en ouvre un, puis F5.

        Le brouillon est cherché sur le serveur : il a pu être mis en pause dans une F5
        fermée depuis. Pour un ticket existant, le serveur refuse un autre que le créateur.
        """
        client, source = self._session(user)
        brouillons = [BrouillonLu.depuisJSON(b) for b in client.listerBrouillons()]
        brouillon = next((b for b in brouillons if b.ticket == ticket), None)
        if brouillon is None:
            brouillon = BrouillonLu.depuisJSON(client.ouvrirBrouillonEdition(ticket.ticketID))
        elif brouillon.estEnPause:
            # Reprise avant d'afficher F5 : si le serveur refuse, aucune F5 ne s'ouvre.
            brouillon = BrouillonLu.depuisJSON(
                client.modifierBrouillon(brouillon.id, enPause=False)
            )
        self._afficherEdition(client, source, brouillon)
        self.signalerBrouillons()

    # Fenêtre pas encore reliée au serveur : F6 (détail, qui télécharge les images).
    # Un message remplace son ouverture.

    def ouvrirDetail(self, tickets: list[TicketLu], index: int) -> None:
        self._fenetreNonReliee("Le détail d'un ticket")

    # ------------------------------------------------------------------ registre des éditions

    def _session(self, user: ActeurLu) -> tuple[ClientAPI, SourceTickets]:
        """Client et source de la session de cet utilisateur, ouverte depuis F1."""
        return self._sessions[user.id]

    def _afficherEdition(
        self, client: ClientAPI, source: SourceTickets, brouillon: BrouillonLu
    ) -> ControleurEdition:
        """Une seule F5 par brouillon : ramenée devant si elle est encore ouverte."""
        self._purgerEditions()
        entree = self._editions.get(brouillon.id)
        if entree is None:
            controleur = ControleurEdition(self, client, brouillon, source)
        else:
            controleur, fenetre = entree
            controleur.actualiser(brouillon)
            if fenetre.winfo_exists():
                fenetre.lift()
                fenetre.focus_set()
                return controleur
        self._editions[brouillon.id] = (controleur, VueEdition(self._racine, controleur))
        return controleur

    def _purgerEditions(self) -> None:
        """Purge paresseuse : oublie les brouillons appliqués ou abandonnés."""
        for brouillonId in [i for i, (c, _) in self._editions.items() if not c.estOuverte]:
            del self._editions[brouillonId]

    # ------------------------------------------------------------------ brouillons et F3

    def ecouterBrouillons(self, rappel: Callable[[], None]) -> None:
        """F3 s'inscrit à son ouverture : elle relit ses brouillons à chaque signal."""
        if rappel not in self._ecouteursBrouillons:
            self._ecouteursBrouillons.append(rappel)

    def oublierBrouillons(self, rappel: Callable[[], None]) -> None:
        if rappel in self._ecouteursBrouillons:
            self._ecouteursBrouillons.remove(rappel)

    def signalerBrouillons(self) -> None:
        """Un brouillon a été ouvert, mis en pause, repris, abandonné ou appliqué."""
        for rappel in list(self._ecouteursBrouillons):
            rappel()

    def _fenetreNonReliee(self, fonction: str) -> None:
        messagebox.showinfo(
            TITRE_APPLICATION, f"{fonction} n'est pas encore reliée au serveur.",
            detail="Cette fenêtre sera branchée sur l'API à une prochaine étape.",
            parent=self._racine,
        )
