"""F3 : tickets créés, tickets assignés et brouillons d'un utilisateur."""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING

from ihm.vues.fenetre_base import FenetreBase

if TYPE_CHECKING:
    from ihm.controleurs.controleur_user import ControleurUser
    from modele.ticket import Ticket
    from sessions.session_edition import SessionEdition

# Onglets : (identifiant, texte, sans le nombre de lignes).
ONGLETS: tuple[tuple[str, str], ...] = (
    ("crees", "Créés par moi"),
    ("assignes", "Assignés à moi"),
    ("brouillons", "Brouillons"),
)

# Colonnes des trois tableaux : (identifiant, titre, largeur, étirable).
COLONNES: tuple[tuple[str, str, int, bool], ...] = (
    ("numero", "#", 50, False),
    ("titre", "Titre", 260, True),
    ("priorite", "Priorité", 95, False),
    ("statut", "Statut", 105, False),
    ("assigne", "Assigné", 140, False),
    ("edition", "Édition", 90, False),
)

# Les sessions ne sont pas des sujets observables : la fenêtre relit leur état à ce rythme
# pour voir aussitôt un brouillon mis en pause ou repris depuis F5.
INTERVALLE_SESSIONS_MS = 500


class VueListeUser(FenetreBase):
    """Seulement les tickets qui concernent l'utilisateur, en trois onglets.

    Abonnée au dépôt (Observer) : un ticket créé, modifié ou retiré, par cet
    utilisateur ou par un autre acteur, apparaît aussitôt. Les boutons suivent
    les règles du contrôleur ; ils sont grisés quand le modèle refuserait.
    """

    def __init__(self, parent: tk.Misc, controleur: ControleurUser) -> None:
        super().__init__(
            parent, f"Gestion des tickets — {controleur.user.name} (User)",
            [controleur.principal.systeme],
        )
        self._controleur: ControleurUser = controleur
        self._listes: dict[str, ttk.Treeview] = {}
        self._cadres: dict[str, ttk.Frame] = {}
        self._tickets: dict[str, dict[str, Ticket]] = {onglet: {} for onglet, _ in ONGLETS}
        self._signatureSessions: tuple[tuple[int, bool], ...] = ()
        self._surveillance: str | None = None
        self._construire()
        self.rafraichir()
        self._surveillerSessions()

    # ------------------------------------------------------------------ construction

    def _construire(self) -> None:
        cadre = ttk.Frame(self, padding=16)
        cadre.pack(fill="both", expand=True)

        # Hauteur des lignes calculée sur la police : lisible aussi avec une mise à l'échelle Windows.
        hauteurLigne = tkfont.nametofont("TkDefaultFont").metrics("linespace") + 8
        ttk.Style(self).configure("Liste.Treeview", rowheight=hauteurLigne)
        self._onglets = ttk.Notebook(cadre)
        self._onglets.pack(fill="both", expand=True)
        for onglet, texte in ONGLETS:
            page = ttk.Frame(self._onglets, padding=(0, 8, 0, 0))
            self._onglets.add(page, text=texte)
            self._cadres[onglet] = page
            liste = ttk.Treeview(
                page, columns=[colonne[0] for colonne in COLONNES], show="headings",
                selectmode="browse", height=10, style="Liste.Treeview",
            )
            for identifiant, titre, largeur, etirable in COLONNES:
                liste.heading(identifiant, text=titre, anchor="w")
                liste.column(identifiant, width=largeur, minwidth=40, anchor="w", stretch=etirable)
            defilement = ttk.Scrollbar(page, command=liste.yview)
            liste.configure(yscrollcommand=defilement.set)
            liste.pack(side="left", fill="both", expand=True)
            defilement.pack(side="right", fill="y")
            liste.bind("<<TreeviewSelect>>", lambda _evenement: self._actualiserBoutons())
            liste.bind("<Double-1>", self._surDoubleClic)
            liste.bind("<Return>", lambda _evenement: self._actionParDefaut())
            self._listes[onglet] = liste
        self._onglets.bind("<<NotebookTabChanged>>", lambda _evenement: self._actualiserBoutons())

        bas = ttk.Frame(cadre)
        bas.pack(fill="x", pady=(12, 0))
        ttk.Button(bas, text="Nouveau ticket", command=self._nouveauTicket).pack(side="left")
        self._boutonSoumettre = ttk.Button(
            bas, text="Soumettre à validation", command=self._soumettre
        )
        self._boutonSoumettre.pack(side="right")
        self._boutonSupprimer = ttk.Button(bas, text="Supprimer", command=self._supprimer)
        self._boutonSupprimer.pack(side="right", padx=(0, 8))
        # Largeur fixe : le texte alterne entre « Éditer » et « Reprendre l'édition ».
        self._boutonEditer = ttk.Button(
            bas, text="Reprendre l'édition", width=20, command=self._editer
        )
        self._boutonEditer.pack(side="right", padx=(0, 8))
        self._boutonDetail = ttk.Button(bas, text="Voir le détail", command=self._voirDetail)
        self._boutonDetail.pack(side="right", padx=(0, 8))

        self.update_idletasks()
        self.minsize(self.winfo_reqwidth(), self.winfo_reqheight())

    # ------------------------------------------------------------------ lecture du modèle

    def rafraichir(self) -> None:
        """Relit les trois onglets ; la sélection de chaque onglet est conservée par numéro."""
        controleur = self._controleur
        lignes: dict[str, list[tuple[Ticket, str, str]]] = {
            "crees": [(t, t.status.name, controleur.etatEdition(t)) for t in controleur.ticketsCrees()],
            "assignes": [
                (t, t.status.name, controleur.etatEdition(t)) for t in controleur.ticketsAssignes()
            ],
            "brouillons": [
                (session.ticket, "BROUILLON", self._etatSession(session))
                for session in controleur.brouillons()
            ],
        }
        for onglet, texte in ONGLETS:
            liste = self._listes[onglet]
            selectionnes = set(liste.selection())
            haut = liste.yview()[0]
            liste.delete(*liste.get_children())
            tickets = self._tickets[onglet]
            tickets.clear()
            for ticket, statut, edition in lignes[onglet]:
                identifiant = str(ticket.ticketID)
                assigne = ticket.assignedUser.name if ticket.assignedUser is not None else "—"
                liste.insert(
                    "", "end", iid=identifiant,
                    values=(
                        ticket.ticketID, ticket.title, ticket.priority.name,
                        statut, assigne, edition or "—",
                    ),
                )
                tickets[identifiant] = ticket
            liste.selection_set([i for i in selectionnes if i in tickets])
            liste.yview_moveto(haut)
            self._onglets.tab(self._cadres[onglet], text=f"{texte} ({len(tickets)})")
        self._signatureSessions = self._lireSessions()
        self._actualiserBoutons()

    @staticmethod
    def _etatSession(session: SessionEdition) -> str:
        return "en pause" if session.estEnPause else "en cours"

    def _ongletCourant(self) -> str:
        page = self._onglets.select()
        return next(onglet for onglet, cadre in self._cadres.items() if str(cadre) == page)

    def _ticketsDeLOnglet(self) -> list[Ticket]:
        onglet = self._ongletCourant()
        return [self._tickets[onglet][i] for i in self._listes[onglet].get_children()]

    def _selection(self) -> Ticket | None:
        onglet = self._ongletCourant()
        selection = self._listes[onglet].selection()
        return self._tickets[onglet].get(selection[0]) if selection else None

    def _actualiserBoutons(self) -> None:
        ticket = self._selection()
        brouillon = self._ongletCourant() == "brouillons"
        controleur = self._controleur
        if ticket is not None and controleur.etatEdition(ticket) == "en pause":
            self._boutonEditer.configure(text="Reprendre l'édition")
        else:
            self._boutonEditer.configure(text="Éditer")
        actifs = {
            self._boutonDetail: ticket is not None and not brouillon,
            self._boutonEditer: ticket is not None and controleur.peutEditer(ticket),
            self._boutonSupprimer: ticket is not None and controleur.peutSupprimer(ticket),
            self._boutonSoumettre: ticket is not None and controleur.peutSoumettre(ticket),
        }
        for bouton, actif in actifs.items():
            bouton.configure(state="normal" if actif else "disabled")

    # ------------------------------------------------------------------ surveillance des sessions

    def _lireSessions(self) -> tuple[tuple[int, bool], ...]:
        """État des sessions ouvertes de l'utilisateur : (numéro du ticket, en pause)."""
        return tuple(
            sorted((s.ticket.ticketID, s.estEnPause) for s in self._controleur.user.sessionsOuvertes)
        )

    def _surveillerSessions(self) -> None:
        if self._lireSessions() != self._signatureSessions:
            self.rafraichir()
        self._surveillance = self.after(INTERVALLE_SESSIONS_MS, self._surveillerSessions)

    def fermer(self) -> None:
        if self._surveillance is not None:
            self.after_cancel(self._surveillance)
            self._surveillance = None
        super().fermer()

    # ------------------------------------------------------------------ actions

    def _surDoubleClic(self, evenement: tk.Event) -> None:
        # Un double-clic hors d'une ligne (en-tête, zone vide) n'ouvre rien.
        if self._listes[self._ongletCourant()].identify_row(evenement.y):
            self._actionParDefaut()

    def _actionParDefaut(self) -> None:
        """Double-clic ou Entrée : le détail, ou la reprise pour un brouillon."""
        if self._ongletCourant() == "brouillons":
            self._editer()
        else:
            self._voirDetail()

    def _nouveauTicket(self) -> None:
        self.executer(self._controleur.nouveauTicket)

    def _voirDetail(self) -> None:
        ticket = self._selection()
        if ticket is None or self._ongletCourant() == "brouillons":
            return
        # F6 parcourt les tickets de l'onglet avec ‹ Précédent / Suivant ›, à partir de la ligne choisie.
        tickets = self._ticketsDeLOnglet()
        self.executer(self._controleur.principal.ouvrirDetail, tickets, tickets.index(ticket))

    def _editer(self) -> None:
        ticket = self._selection()
        if ticket is not None and self._controleur.peutEditer(ticket):
            self.executer(self._controleur.editer, ticket)
            self.rafraichir()

    def _supprimer(self) -> None:
        ticket = self._selection()
        if ticket is None or not self._controleur.peutSupprimer(ticket):
            return
        if messagebox.askyesno(
            "Supprimer le ticket", f"Supprimer le ticket #{ticket.ticketID} « {ticket.title} » ?",
            detail="Le ticket sera retiré du dépôt. Cette action ne peut pas être annulée.",
            icon="warning", default="no", parent=self,
        ):
            # La liste se met à jour par le dépôt (ticketRetire), comme F2 et F6.
            self.executer(self._controleur.supprimer, ticket)

    def _soumettre(self) -> None:
        ticket = self._selection()
        if ticket is not None and self._controleur.peutSoumettre(ticket):
            self.executer(self._controleur.soumettre, ticket)
