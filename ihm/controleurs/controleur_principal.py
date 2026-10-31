"""Contrôleur principal : navigation entre les fenêtres, chargement et sauvegarde."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
from typing import TYPE_CHECKING, cast

from ihm.controleurs.controleur_admin import ControleurAdmin
from ihm.controleurs.controleur_edition import ControleurEdition
from ihm.controleurs.controleur_user import ControleurUser
from ihm.vues.vue_connexion import VueConnexion
from ihm.vues.vue_detail import VueDetail
from ihm.vues.vue_edition import VueEdition
from ihm.vues.vue_liste_admin import VueListeAdmin
from ihm.vues.vue_liste_user import VueListeUser
from ihm.vues.vue_lot import VueLot
from ihm.vues.vue_nouveau_ticket import VueNouveauTicket
from ihm.vues.vue_rapport import VueRapport
from modele.systeme_tickets import SystemeTickets
from modele.ticket import Ticket
from persistance.depot_json import DepotJSON, PersistanceException
from persistance.stockage_images import StockageImages

if TYPE_CHECKING:
    from acteurs.admin import Admin
    from acteurs.user import User
    from acteurs.utilisateur_systeme import UtilisateurSysteme
    from modele.enums import Priorite
    from sessions.rapport_execution import RapportExecution
    from sessions.session_edition import SessionEdition

CHEMIN_SAUVEGARDE = "donnees/sauvegarde.json"
CHEMIN_DEMO = "donnees/demo.json"
TITRE_APPLICATION = "Gestion des tickets"


class ControleurPrincipal:
    """Seul contrôleur qui crée des fenêtres ; détient le dépôt et le stockage des images."""

    def __init__(self, racine: tk.Tk) -> None:
        self._racine: tk.Tk = racine
        self._systeme: SystemeTickets = SystemeTickets()
        self._stockage: StockageImages = StockageImages()
        self._connexion: VueConnexion | None = None
        # Un seul ControleurEdition par session : il survit à la fermeture de F5 et garde
        # le texte tapé et les copies d'images. La fenêtre sert à la ramener devant (lift).
        self._editions: dict[SessionEdition, tuple[ControleurEdition, VueEdition]] = {}

    @property
    def systeme(self) -> SystemeTickets:
        return self._systeme

    @property
    def stockage(self) -> StockageImages:
        return self._stockage

    # ------------------------------------------------------------------ cycle de vie

    def demarrer(self) -> None:
        """Charge la sauvegarde, ou à défaut la démonstration, puis ouvre la connexion."""
        self._systeme = self._charger()
        self._connexion = VueConnexion(self._racine, self)

    def _charger(self) -> SystemeTickets:
        sauvegarde = DepotJSON(CHEMIN_SAUVEGARDE)
        if sauvegarde.existe():
            try:
                return self._lire(sauvegarde)
            except PersistanceException as erreur:
                messagebox.showerror(
                    TITRE_APPLICATION,
                    f"{erreur}\n\nL'application démarre sur les données de démonstration.",
                    parent=self._racine,
                )
        # Une démonstration illisible n'est pas rattrapée : sans elle, aucun acteur.
        return self._lire(DepotJSON(CHEMIN_DEMO))

    def _lire(self, depot: DepotJSON) -> SystemeTickets:
        """Charge un fichier et signale ses avertissements (artefacts introuvables)."""
        systeme = depot.charger()
        if depot.avertissements:
            messagebox.showwarning(
                TITRE_APPLICATION,
                f"Chargement de {depot.chemin.as_posix()} :\n" + "\n".join(depot.avertissements),
                parent=self._racine,
            )
        return systeme

    def quitter(self) -> None:
        """Avertit des sessions perdues, sauvegarde, puis ferme l'application."""
        parent = self._connexion if self._connexion is not None else self._racine
        ouvertes = sum(len(user.sessionsOuvertes) for user in self.utilisateurs())
        if ouvertes:
            if ouvertes == 1:
                message = "1 session encore ouverte (édition ou création)."
                detail = "Elle n'est pas sauvegardée et sera perdue. Quitter quand même ?"
            else:
                message = f"{ouvertes} sessions encore ouvertes (édition ou création)."
                detail = "Elles ne sont pas sauvegardées et seront perdues. Quitter quand même ?"
            if not messagebox.askyesno(
                TITRE_APPLICATION, message, detail=detail,
                icon="warning", default="no", parent=parent,
            ):
                return
        try:
            DepotJSON(CHEMIN_SAUVEGARDE).sauvegarder(self._systeme)
        except (PersistanceException, OSError) as erreur:
            if not messagebox.askyesno(
                TITRE_APPLICATION, f"Sauvegarde impossible : {erreur}",
                detail="Quitter sans sauvegarder ?",
                icon="error", default="no", parent=parent,
            ):
                return
        self._racine.destroy()

    # ------------------------------------------------------------------ données

    def utilisateurs(self) -> list[User]:
        """Acteurs de rôle User (choix de l'assigné, sessions ouvertes), sans isinstance."""
        return [
            cast("User", acteur) for acteur in self._systeme.utilisateurs
            if acteur.role == "User"
        ]

    def prochainIdentifiant(self) -> int:
        """Plus grand identifiant du dépôt et des brouillons ouverts, plus 1."""
        identifiants = [ticket.ticketID for ticket in self._systeme.tickets]
        for user in self.utilisateurs():
            identifiants += [session.ticket.ticketID for session in user.sessionsOuvertes]
        return max(identifiants, default=0) + 1

    # ------------------------------------------------------------------ navigation

    def ouvrirSession(self, acteur: UtilisateurSysteme) -> None:
        if acteur.role == "Admin":
            self.ouvrirListeAdmin(cast("Admin", acteur))
        elif acteur.role == "User":
            self.ouvrirListeUser(cast("User", acteur))

    def ouvrirListeAdmin(self, admin: Admin) -> None:
        VueListeAdmin(self._racine, ControleurAdmin(self, admin))

    def ouvrirListeUser(self, user: User) -> None:
        VueListeUser(self._racine, ControleurUser(self, user))

    def ouvrirCreation(self, user: User) -> None:
        VueNouveauTicket(self._racine, self, user)

    def commencerCreation(self, user: User, titre: str, priorite: Priorite) -> None:
        """Crée le ticket et sa session de création, hors du dépôt, puis ouvre F5."""
        self._purgerEditions()
        ticket = Ticket(self.prochainIdentifiant(), titre, priorite)
        session = user.ouvrirSessionCreation(ticket)
        self._afficherEdition(session)

    def ouvrirEdition(self, user: User, ticket: Ticket) -> None:
        """Reprend la session en cours, même en pause, ou en ouvre une, puis F5."""
        self._purgerEditions()
        session = user.sessionEnCours(ticket)
        if session is None:
            session = user.ouvrirSessionEdition(ticket)
        if session.estEnPause:
            session.reprendre()
        self._afficherEdition(session)

    def ouvrirDetail(self, tickets: list[Ticket], index: int) -> None:
        VueDetail(self._racine, self._systeme, tickets, index)

    def ouvrirLot(self, controleur: ControleurAdmin, action: str, tickets: list[Ticket]) -> None:
        VueLot(self._racine, controleur, action, tickets)

    def afficherRapport(self, rapport: RapportExecution, libelle: str) -> None:
        VueRapport(self._racine, rapport, libelle)

    # ------------------------------------------------------------------ registre des éditions

    def _afficherEdition(self, session: SessionEdition) -> None:
        """Une seule F5 par session : ramenée devant si elle est encore ouverte."""
        entree = self._editions.get(session)
        if entree is None:
            controleur = ControleurEdition(self, session)
        else:
            controleur, fenetre = entree
            if fenetre.winfo_exists():
                fenetre.lift()
                fenetre.focus_set()
                return
        self._editions[session] = (controleur, VueEdition(self._racine, controleur))

    def _purgerEditions(self) -> None:
        """Purge paresseuse : oublie les sessions appliquées ou abandonnées."""
        for session in [s for s in self._editions if not s.estOuverte]:
            del self._editions[session]
