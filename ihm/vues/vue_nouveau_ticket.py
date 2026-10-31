"""F4 : titre et priorité d'un nouveau ticket, avant l'éditeur de description."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from ihm.vues.fenetre_base import FenetreBase
from modele.enums import Priorite

if TYPE_CHECKING:
    from acteurs.user import User
    from ihm.controleurs.controleur_principal import ControleurPrincipal


class VueNouveauTicket(FenetreBase):
    """Formulaire seul : « Continuer » délègue la création au contrôleur principal."""

    def __init__(self, parent: tk.Misc, principal: ControleurPrincipal, user: User) -> None:
        super().__init__(parent, "Nouveau ticket", [])
        self._principal: ControleurPrincipal = principal
        self._user: User = user
        self._titre = tk.StringVar(self)
        self._priorite = tk.StringVar(self, value=Priorite.MOYENNE.name)
        self._construire()
        self._titre.trace_add("write", lambda *_: self._actualiser())
        self._actualiser()

    def _construire(self) -> None:
        self.resizable(False, False)
        cadre = ttk.Frame(self, padding=20)
        cadre.pack(fill="both", expand=True)

        ttk.Label(cadre, text="Titre").pack(anchor="w")
        champTitre = ttk.Entry(cadre, textvariable=self._titre, width=55)
        champTitre.pack(fill="x", pady=(4, 12))
        champTitre.focus_set()

        ttk.Label(cadre, text="Priorité").pack(anchor="w")
        ttk.Combobox(
            cadre, textvariable=self._priorite, state="readonly", width=20,
            values=[priorite.name for priorite in Priorite],
        ).pack(anchor="w", pady=(4, 12))

        ttk.Label(
            cadre, foreground="gray40",
            text="La description (texte, images) et les commentaires "
                 "se rédigent à l'étape suivante.",
        ).pack(anchor="w")

        boutons = ttk.Frame(cadre)
        boutons.pack(fill="x", pady=(14, 0))
        self._boutonContinuer = ttk.Button(
            boutons, text="Continuer", default="active", command=self._continuer
        )
        self._boutonContinuer.pack(side="right")
        ttk.Button(boutons, text="Annuler", command=self.fermer).pack(side="right", padx=(0, 8))

        self.bind("<Return>", lambda _evenement: self._continuer())
        self.bind("<Escape>", lambda _evenement: self.fermer())

    def _actualiser(self) -> None:
        etat = "normal" if self._titre.get().strip() else "disabled"
        self._boutonContinuer.configure(state=etat)

    def _continuer(self) -> None:
        titre = self._titre.get().strip()
        if not titre:
            return
        priorite = Priorite[self._priorite.get()]

        def creer() -> bool:
            self._principal.commencerCreation(self._user, titre, priorite)
            return True

        # executer() retourne None après un refus : F4 reste alors ouverte.
        if self.executer(creer):
            self.fermer()
