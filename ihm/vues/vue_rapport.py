"""F8 : rapport d'exécution d'un lot de l'Admin ou d'une session d'édition."""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk
from typing import TYPE_CHECKING

from ihm.vues.fenetre_base import FenetreBase

if TYPE_CHECKING:
    from sessions.rapport_execution import RapportExecution

VERT_FOND, VERT_TEXTE = "#dcfce7", "#166534"
ROUGE_FOND, ROUGE_TEXTE = "#fee2e2", "#b42318"


class VueRapport(FenetreBase):
    """Bilan, puis chaque succès et chaque refus avec son motif ; lecture seule.

    Aucun sujet observé : le rapport décrit une application passée. Les listes
    F2, F3 et F6 ont déjà été prévenues par le dépôt (Observer).
    """

    def __init__(self, parent: tk.Misc, rapport: RapportExecution, libelle: str) -> None:
        super().__init__(parent, f"Gestion des tickets — Rapport : {libelle}", [])
        self._rapport: RapportExecution = rapport
        self._libelle: str = libelle
        self._construire()

    def _construire(self) -> None:
        self.resizable(False, False)
        cadre = ttk.Frame(self, padding=20)
        cadre.pack(fill="both", expand=True)
        # Les polices sont gardées en attribut : sans référence, tkinter les supprimerait.
        self._policeGras = tkfont.nametofont("TkDefaultFont").copy()
        self._policeGras.configure(weight="bold")
        self._policeMotif = tkfont.nametofont("TkDefaultFont").copy()
        self._policeMotif.configure(size=max(self._policeMotif.actual("size") - 1, 8))

        rapport = self._rapport
        ttk.Label(cadre, text=f"Rapport d'exécution — {self._libelle}", font=self._policeGras).pack(
            anchor="w"
        )
        bilan = ttk.Frame(cadre)
        bilan.pack(anchor="w", pady=(10, 0))
        self._badge(bilan, f"{rapport.nombreSucces} succès", VERT_FOND, VERT_TEXTE).pack(side="left")
        self._badge(bilan, f"{rapport.nombreRefus} refus", ROUGE_FOND, ROUGE_TEXTE).pack(
            side="left", padx=(8, 0)
        )

        ttk.Label(cadre, text="Succès").pack(anchor="w", pady=(14, 4))
        succes = self._zone(cadre, max(rapport.nombreSucces, 1))
        for libelle in rapport.succes:
            succes.insert("end", " OK ", "ok")
            succes.insert("end", f"  {libelle}\n")
        if not rapport.succes:
            succes.insert("end", "(aucun)\n", "vide")
        self._figer(succes)

        ttk.Label(cadre, text="Refus").pack(anchor="w", pady=(14, 4))
        refus = self._zone(cadre, max(2 * rapport.nombreRefus, 1))
        for libelle, motif in rapport.refus:
            refus.insert("end", " REFUS ", "refus")
            refus.insert("end", f"  {libelle}\n")
            refus.insert("end", f"Motif : {motif}\n", "motif")
        if not rapport.refus:
            refus.insert("end", "(aucun)\n", "vide")
        self._figer(refus)

        boutons = ttk.Frame(cadre)
        boutons.pack(fill="x", pady=(16, 0))
        boutonOk = ttk.Button(boutons, text="OK", default="active", command=self.fermer)
        boutonOk.pack(side="right")
        boutonOk.focus_set()
        self.bind("<Return>", lambda _evenement: self.fermer())
        self.bind("<Escape>", lambda _evenement: self.fermer())

    @staticmethod
    def _badge(parent: tk.Misc, texte: str, fond: str, couleur: str) -> tk.Label:
        return tk.Label(parent, text=texte, background=fond, foreground=couleur, padx=8, pady=2)

    def _zone(self, parent: tk.Misc, lignes: int) -> tk.Text:
        """Zone de texte en lecture seule, avec défilement au-delà de 8 lignes."""
        cadre = ttk.Frame(parent)
        cadre.pack(fill="x")
        zone = tk.Text(
            cadre, width=64, height=min(lignes, 8), wrap="word", font="TkDefaultFont",
            relief="solid", borderwidth=1, padx=8, pady=6, takefocus=False, cursor="arrow",
        )
        zone.tag_configure("ok", background=VERT_FOND, foreground=VERT_TEXTE, font=self._policeGras)
        zone.tag_configure(
            "refus", background=ROUGE_FOND, foreground=ROUGE_TEXTE, font=self._policeGras
        )
        zone.tag_configure(
            "motif", foreground="gray35", font=self._policeMotif, lmargin1=16, lmargin2=16,
            spacing3=4,
        )
        zone.tag_configure("vide", foreground="gray40")
        zone.pack(side="left", fill="x", expand=True)
        if lignes > 8:
            defilement = ttk.Scrollbar(cadre, command=zone.yview)
            zone.configure(yscrollcommand=defilement.set)
            defilement.pack(side="right", fill="y")
        return zone

    @staticmethod
    def _figer(zone: tk.Text) -> None:
        zone.delete("end-2c", "end-1c")  # notre dernier saut de ligne (Tk garde le sien)
        zone.configure(state="disabled")
