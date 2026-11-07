"""F3 : tickets créés, tickets assignés et brouillons d'un utilisateur."""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING

from ihm.vues.fenetre_base import FenetreBase

if TYPE_CHECKING:
    from ihm.controleurs.controleur_user import ControleurUser
    from ihm.passerelle.objets_lecture import BrouillonLu, TicketLu, TicketRefLu

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


class VueListeUser(FenetreBase):
    """Seulement les tickets qui concernent l'utilisateur, en trois onglets.

    Abonnée à la source de la session (Observer) : un ticket créé, modifié ou retiré, par
    cet utilisateur ou par un autre acteur, dans cette GUI ou dans une autre, apparaît en
    une seconde au plus. Les boutons suivent les règles du contrôleur ; ils sont grisés
    quand le serveur refuserait.
    """

    def __init__(self, parent: tk.Misc, controleur: ControleurUser) -> None:
        super().__init__(
            parent, f"Gestion des tickets — {controleur.user.name} (User)",
            [controleur.source],
        )
        self._controleur: ControleurUser = controleur
        self._listes: dict[str, ttk.Treeview] = {}
        self._cadres: dict[str, ttk.Frame] = {}
        self._tickets: dict[str, dict[str, TicketRefLu]] = {onglet: {} for onglet, _ in ONGLETS}
        self._construire()
        self.rafraichir()

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
        """Relit les trois onglets sur le serveur ; la sélection de chaque onglet est conservée
        par numéro."""
        controleur = self._controleur
        controleur.chargerBrouillons()
        lignes: dict[str, list[tuple[TicketRefLu, str, str, str]]] = {
            onglet: [
                (t, t.status.name, self._nomAssigne(t), controleur.etatEdition(t))
                for t in tickets
            ]
            for onglet, tickets in (
                ("crees", controleur.ticketsCrees()),
                ("assignes", controleur.ticketsAssignes()),
            )
        }
        # Le ticket d'un brouillon de création n'est pas encore dans le dépôt : ni statut
        # ni assigné.
        lignes["brouillons"] = [
            (brouillon.ticket, "BROUILLON", "—", self._etatBrouillon(brouillon))
            for brouillon in controleur.brouillons()
        ]
        for onglet, texte in ONGLETS:
            liste = self._listes[onglet]
            selectionnes = set(liste.selection())
            haut = liste.yview()[0]
            liste.delete(*liste.get_children())
            tickets = self._tickets[onglet]
            tickets.clear()
            for ticket, statut, assigne, edition in lignes[onglet]:
                identifiant = str(ticket.ticketID)
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
        self._actualiserBoutons()

    @staticmethod
    def _nomAssigne(ticket: TicketLu) -> str:
        return ticket.assignedUser.name if ticket.assignedUser is not None else "—"

    @staticmethod
    def _etatBrouillon(brouillon: BrouillonLu) -> str:
        return "en pause" if brouillon.estEnPause else "en cours"

    def _ongletCourant(self) -> str:
        page = self._onglets.select()
        return next(onglet for onglet, cadre in self._cadres.items() if str(cadre) == page)

    def _ticketsDeLOnglet(self) -> list[TicketRefLu]:
        onglet = self._ongletCourant()
        return [self._tickets[onglet][i] for i in self._listes[onglet].get_children()]

    def _selection(self) -> TicketRefLu | None:
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
            # La liste se met à jour par la source (ticketRetire), comme F2.
            self.executer(self._controleur.supprimer, ticket)

    def _soumettre(self) -> None:
        ticket = self._selection()
        if ticket is not None and self._controleur.peutSoumettre(ticket):
            self.executer(self._controleur.soumettre, ticket)
