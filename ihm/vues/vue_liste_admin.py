"""F2 : liste de tous les tickets pour l'Admin, avec filtre, sélection multiple et actions."""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk
from typing import TYPE_CHECKING

from ihm.vues.fenetre_base import FenetreBase
from modele.enums import Statut

if TYPE_CHECKING:
    from ihm.controleurs.controleur_admin import ControleurAdmin
    from modele.ticket import Ticket

TOUS = "Tous"

# Boutons d'action, dans l'ordre de la maquette : (action du contrôleur, texte).
ACTIONS: tuple[tuple[str, str], ...] = (
    ("assigner", "Assigner…"),
    ("desassigner", "Désassigner"),
    ("valider", "Valider"),
    ("fermer", "Fermer"),
)

# Colonnes du tableau : (identifiant, titre, largeur, étirable).
COLONNES: tuple[tuple[str, str, int, bool], ...] = (
    ("numero", "#", 50, False),
    ("titre", "Titre", 260, True),
    ("priorite", "Priorité", 95, False),
    ("statut", "Statut", 105, False),
    ("createur", "Créateur", 140, False),
    ("assigne", "Assigné", 140, False),
)


class VueListeAdmin(FenetreBase):
    """Tout le dépôt ; abonnée au dépôt, elle se redessine à chaque notification (Observer).

    La vue ne modifie jamais un ticket : les boutons suivent actionsPossibles() du
    contrôleur, et chaque action ouvre F7, qui demande confirmation avant d'appliquer.
    """

    def __init__(self, parent: tk.Misc, controleur: ControleurAdmin) -> None:
        super().__init__(
            parent, f"Gestion des tickets — {controleur.admin.name} (Admin)",
            [controleur.principal.systeme],
        )
        self._controleur: ControleurAdmin = controleur
        self._filtre = tk.StringVar(self, value=TOUS)
        self._tickets: dict[str, Ticket] = {}  # identifiant de ligne -> ticket
        self._boutons: dict[str, ttk.Button] = {}
        self._construire()
        self.rafraichir()

    # ------------------------------------------------------------------ construction

    def _construire(self) -> None:
        cadre = ttk.Frame(self, padding=16)
        cadre.pack(fill="both", expand=True)

        haut = ttk.Frame(cadre)
        haut.pack(fill="x")
        ttk.Label(haut, text="Statut :").pack(side="left")
        filtre = ttk.Combobox(
            haut, textvariable=self._filtre, state="readonly", width=14,
            values=[TOUS] + [statut.name for statut in Statut],
        )
        filtre.pack(side="left", padx=(6, 0))
        filtre.bind("<<ComboboxSelected>>", lambda _evenement: self.rafraichir())
        self._resumeSelection = ttk.Label(haut, foreground="gray40")
        self._resumeSelection.pack(side="right")

        # Hauteur des lignes calculée sur la police : lisible aussi avec une mise à l'échelle Windows.
        hauteurLigne = tkfont.nametofont("TkDefaultFont").metrics("linespace") + 8
        ttk.Style(self).configure("Liste.Treeview", rowheight=hauteurLigne)
        tableau = ttk.Frame(cadre)
        tableau.pack(fill="both", expand=True, pady=(10, 0))
        self._liste = ttk.Treeview(
            tableau, columns=[colonne[0] for colonne in COLONNES], show="headings",
            selectmode="extended", height=12, style="Liste.Treeview",
        )
        for identifiant, titre, largeur, etirable in COLONNES:
            self._liste.heading(identifiant, text=titre, anchor="w")
            self._liste.column(identifiant, width=largeur, minwidth=40, anchor="w", stretch=etirable)
        defilement = ttk.Scrollbar(tableau, command=self._liste.yview)
        self._liste.configure(yscrollcommand=defilement.set)
        self._liste.pack(side="left", fill="both", expand=True)
        defilement.pack(side="right", fill="y")
        self._liste.bind("<<TreeviewSelect>>", lambda _evenement: self._actualiserBoutons())
        self._liste.bind("<Double-1>", self._surDoubleClic)
        self._liste.bind("<Return>", lambda _evenement: self._voirDetail())

        bas = ttk.Frame(cadre)
        bas.pack(fill="x", pady=(12, 0))
        self._boutonDetail = ttk.Button(bas, text="Voir le détail", command=self._voirDetail)
        self._boutonDetail.pack(side="left")
        for action, texte in reversed(ACTIONS):
            bouton = ttk.Button(bas, text=texte, command=lambda a=action: self._ouvrirLot(a))
            bouton.pack(side="right", padx=(8, 0))
            self._boutons[action] = bouton

        self._liste.focus_set()
        self.update_idletasks()
        self.minsize(self.winfo_reqwidth(), self.winfo_reqheight())

    # ------------------------------------------------------------------ lecture du modèle

    def rafraichir(self) -> None:
        """Relit les tickets du filtre ; la sélection est conservée par numéro de ticket."""
        selectionnes = set(self._liste.selection())
        focus = self._liste.focus()
        haut = self._liste.yview()[0]

        nom = self._filtre.get()
        statut = None if nom == TOUS else Statut[nom]
        self._liste.delete(*self._liste.get_children())
        self._tickets.clear()
        for ticket in self._controleur.tickets(statut):
            identifiant = str(ticket.ticketID)
            createur = ticket.creator.name if ticket.creator is not None else "—"
            assigne = ticket.assignedUser.name if ticket.assignedUser is not None else "—"
            self._liste.insert(
                "", "end", iid=identifiant,
                values=(
                    ticket.ticketID, ticket.title, ticket.priority.name,
                    ticket.status.name, createur, assigne,
                ),
            )
            self._tickets[identifiant] = ticket

        self._liste.selection_set([i for i in selectionnes if i in self._tickets])
        if focus in self._tickets:
            self._liste.focus(focus)
        self._liste.yview_moveto(haut)
        self._actualiserBoutons()

    def _selection(self) -> list[Ticket]:
        """Tickets sélectionnés, dans l'ordre du tableau."""
        choisis = set(self._liste.selection())
        return [self._tickets[i] for i in self._liste.get_children() if i in choisis]

    def _actualiserBoutons(self) -> None:
        selection = self._selection()
        possibles = self._controleur.actionsPossibles(selection)
        for action, bouton in self._boutons.items():
            bouton.configure(state="normal" if possibles[action] else "disabled")
        self._boutonDetail.configure(state="normal" if selection else "disabled")

        n = len(selection)
        if n == 0:
            resume = "Aucun ticket sélectionné"
        elif n == 1:
            resume = "1 ticket sélectionné"
        else:
            resume = f"{n} tickets sélectionnés"
        self._resumeSelection.configure(text=f"{resume} · Ctrl+clic pour en ajouter")

    # ------------------------------------------------------------------ actions

    def _surDoubleClic(self, evenement: tk.Event) -> None:
        # Un double-clic hors d'une ligne (en-tête, zone vide) n'ouvre rien.
        if self._liste.identify_row(evenement.y):
            self._voirDetail()

    def _voirDetail(self) -> None:
        selection = self._selection()
        if not selection:
            return
        # F6 parcourt toute la sélection avec ‹ Précédent / Suivant ›, en partant du ticket actif.
        actif = self._tickets.get(self._liste.focus())
        index = selection.index(actif) if actif in selection else 0
        self.executer(self._controleur.principal.ouvrirDetail, selection, index)

    def _ouvrirLot(self, action: str) -> None:
        selection = self._selection()
        if selection and self._controleur.actionsPossibles(selection)[action]:
            self.executer(self._controleur.principal.ouvrirLot, self._controleur, action, selection)
