"""F1 : connexion, choix de l'acteur avec lequel ouvrir une session."""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk
from typing import TYPE_CHECKING

from ihm.vues.fenetre_base import FenetreBase

if TYPE_CHECKING:
    from acteurs.utilisateur_systeme import UtilisateurSysteme
    from ihm.controleurs.controleur_principal import ControleurPrincipal


class VueConnexion(FenetreBase):
    """Liste des acteurs de l'annuaire ; reste ouverte pour ouvrir plusieurs sessions."""

    def __init__(self, parent: tk.Misc, principal: ControleurPrincipal) -> None:
        # Aucun sujet : l'annuaire ne change pas pendant l'exécution.
        super().__init__(parent, "Gestion des tickets — Connexion", [])
        self._principal: ControleurPrincipal = principal
        self._acteurs: dict[str, UtilisateurSysteme] = {}
        # Quitter la connexion, c'est quitter l'application.
        self.protocol("WM_DELETE_WINDOW", principal.quitter)
        self._construire()
        self._remplir()

    def _construire(self) -> None:
        self.resizable(False, False)
        cadre = ttk.Frame(self, padding=20)
        cadre.pack(fill="both", expand=True)

        # La police est gardée en attribut : sans référence, tkinter la supprimerait.
        self._policeTitre = tkfont.nametofont("TkDefaultFont").copy()
        self._policeTitre.configure(size=14, weight="bold")
        ttk.Label(cadre, text="Choisissez votre compte", font=self._policeTitre).pack(anchor="w")
        ttk.Label(
            cadre, text="Sélectionnez l'acteur avec lequel ouvrir une session.",
            foreground="gray40",
        ).pack(anchor="w", pady=(6, 12))

        style = ttk.Style(self)
        style.configure("Connexion.Treeview", rowheight=28)
        self._liste = ttk.Treeview(
            cadre, columns=("nom", "role"), show="", selectmode="browse",
            height=5, style="Connexion.Treeview",
        )
        self._liste.column("nom", anchor="w", width=280)
        self._liste.column("role", anchor="e", width=90)
        self._liste.pack(fill="both", expand=True)
        self._liste.bind("<Double-1>", self._surDoubleClic)

        boutons = ttk.Frame(cadre)
        boutons.pack(fill="x", pady=(14, 0))
        ttk.Button(
            boutons, text="Ouvrir la session", default="active", command=self._ouvrir,
        ).pack(side="right")
        ttk.Button(boutons, text="Quitter", command=self._principal.quitter).pack(
            side="right", padx=(0, 8)
        )
        self.bind("<Return>", lambda _evenement: self._ouvrir())

    def _remplir(self) -> None:
        for acteur in self._principal.systeme.utilisateurs:
            identifiant = self._liste.insert("", "end", values=(acteur.name, acteur.role))
            self._acteurs[identifiant] = acteur
        premier = next(iter(self._acteurs), None)
        if premier is not None:
            self._liste.selection_set(premier)
            self._liste.focus(premier)
        self._liste.focus_set()

    def _surDoubleClic(self, evenement: tk.Event) -> None:
        # Un double-clic hors d'une ligne n'ouvre rien.
        if self._liste.identify_row(evenement.y):
            self._ouvrir()

    def _ouvrir(self) -> None:
        selection = self._liste.selection()
        if selection:
            self.executer(self._principal.ouvrirSession, self._acteurs[selection[0]])
