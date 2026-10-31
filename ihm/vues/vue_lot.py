"""F7 : confirmation d'un lot d'opérations de l'Admin, avant toute modification."""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk
from typing import TYPE_CHECKING

from ihm.vues.fenetre_base import FenetreBase

if TYPE_CHECKING:
    from acteurs.user import User
    from ihm.controleurs.controleur_admin import ControleurAdmin
    from modele.ticket import Ticket
    from sessions.lot_admin import LotAdmin

VERBES: dict[str, str] = {
    "assigner": "Assigner",
    "desassigner": "Désassigner",
    "valider": "Valider",
    "fermer": "Fermer",
}
AVERTISSEMENT_FERMETURE = "Action définitive : un ticket fermé ne peut plus changer d'état."


class VueLot(FenetreBase):
    """Montre exactement ce qui sera appliqué (modificationsEnAttente) ; rien ne change avant « Appliquer ».

    « Annuler » ferme la fenêtre sans appeler appliquer() : le lot est simplement
    oublié. Pour « Fermer », action définitive, un avertissement s'affiche et le
    focus est sur « Annuler » : la touche Entrée ne ferme aucun ticket.
    """

    def __init__(
        self, parent: tk.Misc, controleur: ControleurAdmin, action: str, tickets: list[Ticket]
    ) -> None:
        super().__init__(
            parent, "Gestion des tickets — Confirmation du lot", [controleur.principal.systeme]
        )
        self._controleur: ControleurAdmin = controleur
        self._action: str = action
        self._tickets: list[Ticket] = list(tickets)
        self._lot: LotAdmin | None = None
        self._utilisateurs: list[User] = []
        self._choixUtilisateur = tk.StringVar(self)
        self._construire()
        if action != "assigner":
            self._lot = controleur.preparerLot(action, self._tickets)
        self._actualiser()

    # ------------------------------------------------------------------ construction

    def _construire(self) -> None:
        self.resizable(False, False)
        cadre = ttk.Frame(self, padding=20)
        cadre.pack(fill="both", expand=True)
        definitive = self._action == "fermer"

        # Les polices sont gardées en attribut : sans référence, tkinter les supprimerait.
        self._policeTitre = tkfont.nametofont("TkDefaultFont").copy()
        self._policeTitre.configure(size=13, weight="bold")
        self._policeGras = tkfont.nametofont("TkDefaultFont").copy()
        self._policeGras.configure(weight="bold")

        n = len(self._tickets)
        ttk.Label(
            cadre, text=f"{VERBES[self._action]} {n} ticket{'s' if n > 1 else ''}",
            font=self._policeTitre,
        ).pack(anchor="w")

        if definitive:
            bandeau = tk.Frame(cadre, background="#fde8e8", highlightthickness=1,
                               highlightbackground="#f5b5b5")
            bandeau.pack(fill="x", pady=(12, 0))
            tk.Label(
                bandeau, text=f"⚠  {AVERTISSEMENT_FERMETURE}", background="#fde8e8",
                foreground="#b42318", font=self._policeGras, padx=10, pady=8,
            ).pack(anchor="w")

        if self._action == "assigner":
            ligne = ttk.Frame(cadre)
            ligne.pack(fill="x", pady=(12, 0))
            ttk.Label(ligne, text="Assigner à :").pack(side="left")
            self._utilisateurs = self._controleur.principal.utilisateurs()
            choix = ttk.Combobox(
                ligne, textvariable=self._choixUtilisateur, state="readonly", width=28,
                values=[user.name for user in self._utilisateurs],
            )
            choix.pack(side="left", padx=(6, 0))
            # Aucun choix par défaut : l'Admin désigne lui-même l'assigné (prévention d'erreur).
            choix.bind("<<ComboboxSelected>>", lambda _evenement: self._surChoixUtilisateur())

        self._titreAttente = ttk.Label(cadre)
        self._titreAttente.pack(anchor="w", pady=(14, 4))
        zone = ttk.Frame(cadre)
        zone.pack(fill="x")
        self._attente = tk.Text(
            zone, width=58, height=min(max(n, 2), 8), wrap="word", font="TkDefaultFont",
            background="#f6f7f9", relief="solid", borderwidth=1, takefocus=False,
            padx=8, pady=6,
        )
        defilement = ttk.Scrollbar(zone, command=self._attente.yview)
        self._attente.configure(yscrollcommand=defilement.set, state="disabled")
        self._attente.pack(side="left", fill="x", expand=True)
        if n > 8:
            defilement.pack(side="right", fill="y")

        ttk.Label(
            cadre, foreground="gray40", wraplength=470, justify="left",
            text="Application « au mieux » : un refus ne bloque pas les opérations suivantes. "
                 "Aucun retour en arrière une fois appliqué.",
        ).pack(anchor="w", pady=(8, 0))

        boutons = ttk.Frame(cadre)
        boutons.pack(fill="x", pady=(16, 0))
        if definitive:
            ttk.Style(self).configure("Danger.TButton", foreground="#b42318")
            texte = f"Fermer définitivement ({n})"
        else:
            texte = f"Appliquer ({n})"
        self._boutonAppliquer = ttk.Button(
            boutons, text=texte, command=self._appliquer,
            style="Danger.TButton" if definitive else "TButton",
            default="normal" if definitive else "active",
        )
        self._boutonAppliquer.pack(side="right")
        boutonAnnuler = ttk.Button(
            boutons, text="Annuler", command=self.fermer,
            default="active" if definitive else "normal",
        )
        boutonAnnuler.pack(side="right", padx=(0, 8))

        # Entrée active le bouton qui a le focus ; Échap annule toujours.
        self.bind("<Return>", self._surEntree)
        self.bind("<Escape>", lambda _evenement: self.fermer())
        (boutonAnnuler if definitive else self._boutonAppliquer).focus_set()

    # ------------------------------------------------------------------ lecture du lot

    def _surChoixUtilisateur(self) -> None:
        nom = self._choixUtilisateur.get()
        user = next((u for u in self._utilisateurs if u.name == nom), None)
        if user is not None:
            # LotAdmin n'a ni retrait ni annulation : un nouveau choix donne un nouveau lot.
            self._lot = self._controleur.preparerLot("assigner", self._tickets, user)
        self._actualiser()
        self._boutonAppliquer.focus_set()

    def _actualiser(self) -> None:
        """Affiche les opérations du lot ; « Appliquer » reste grisé tant qu'il n'y en a pas."""
        if self._lot is None:
            lignes = ["Choisissez d'abord l'utilisateur à qui assigner les tickets."]
            nombre = 0
        else:
            attente = self._lot.modificationsEnAttente
            lignes = [f"{numero}. {libelle}" for numero, libelle in enumerate(attente, start=1)]
            nombre = len(attente)
        self._titreAttente.configure(text=f"Opérations en attente ({nombre})")
        self._attente.configure(state="normal")
        self._attente.delete("1.0", "end")
        self._attente.insert("1.0", "\n".join(lignes))
        self._attente.configure(state="disabled")
        self._boutonAppliquer.configure(state="normal" if nombre else "disabled")

    # ------------------------------------------------------------------ actions

    def _surEntree(self, _evenement: tk.Event) -> None:
        widget = self.focus_get() or self.focus_lastfor()
        if isinstance(widget, ttk.Button) and str(widget.cget("state")) != "disabled":
            widget.invoke()

    def _appliquer(self) -> None:
        if self._lot is None:
            return
        lot, self._lot = self._lot, None  # un lot ne s'applique qu'une fois
        # appliquerLot() ouvre F8 ; F2 se met à jour seule, par le patron Observer.
        self.executer(self._controleur.appliquerLot, lot)
        self.fermer()
