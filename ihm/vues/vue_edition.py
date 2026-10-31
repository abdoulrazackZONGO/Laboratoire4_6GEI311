"""F5 : éditeur de la description d'un ticket, en création ou en édition."""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont
from typing import TYPE_CHECKING, Callable

from ihm.vues.fenetre_base import FenetreBase

if TYPE_CHECKING:
    from ihm.controleurs.controleur_edition import ControleurEdition


class VueEdition(FenetreBase):
    """Toute action passe par le ControleurEdition ; un refus s'affiche et F5 reste ouverte."""

    def __init__(self, parent: tk.Misc, controleur: ControleurEdition) -> None:
        ticket = controleur.session.ticket
        if controleur.estCreation:
            titre = f"Nouveau ticket #{ticket.ticketID} — {ticket.title}"
        else:
            titre = f"Édition du ticket #{ticket.ticketID} — {ticket.title}"
        super().__init__(parent, titre, [])
        self._controleur: ControleurEdition = controleur
        self._commentaire = tk.StringVar(self)
        # La croix met en pause, comme « Mettre en pause » : rien n'est perdu.
        self.protocol("WM_DELETE_WINDOW", self._mettreEnPause)
        self._construire()
        self._commentaire.trace_add("write", lambda *_: self._actualiser())
        self._actualiser()
        self.update_idletasks()
        self.minsize(self.winfo_reqwidth(), self.winfo_reqheight())

    # ------------------------------------------------------------------ construction

    def _construire(self) -> None:
        creation = self._controleur.estCreation
        cadre = ttk.Frame(self, padding=16)
        cadre.pack(fill="both", expand=True)
        # La police est gardée en attribut : sans référence, tkinter la supprimerait.
        self._policeSection = tkfont.nametofont("TkDefaultFont").copy()
        self._policeSection.configure(weight="bold")
        ttk.Style(self).configure(
            "Badge.TLabel", background="#dbeafe", foreground="#1e40af", padding=(8, 2)
        )

        ligneMode = ttk.Frame(cadre)
        ligneMode.pack(fill="x")
        ttk.Label(
            ligneMode, text="Mode création" if creation else "Mode édition", style="Badge.TLabel"
        ).pack(side="left")
        self._statut = ttk.Label(ligneMode, foreground="gray40")
        self._statut.pack(side="left", padx=(10, 0))

        self._section(cadre, "Texte de la description")
        self._texte = self._zoneTexte(
            cadre, width=80, height=5, font="TkDefaultFont", undo=True, maxundo=-1
        )
        self._texte.insert("1.0", self._controleur.texteBrouillon)
        # Le texte repris après une pause n'est pas une frappe à annuler.
        self._texte.edit_reset()
        self._texte.edit_modified(False)
        for touche in ("<Control-z>", "<Control-Z>"):
            self._texte.bind(touche, self._annulerFrappe)
        for touche in ("<Control-y>", "<Control-Y>"):
            self._texte.bind(touche, self._retablirFrappe)
        self._texte.bind("<<Modified>>", self._surFrappe)
        moment = "de créer le ticket" if creation else "d'appliquer"
        ttk.Label(
            cadre, foreground="gray40",
            text="Ctrl+Z / Ctrl+Y : annuler ou rétablir la frappe. "
                 f"Le texte entre dans la description au moment {moment}.",
        ).pack(anchor="w", pady=(4, 0))

        self._section(cadre, "Images (PNG ou GIF)")
        ligneImages = ttk.Frame(cadre)
        ligneImages.pack(fill="x")
        ttk.Button(ligneImages, text="Ajouter des images…", command=self._ajouterImages).pack(
            side="left"
        )
        self._boutonAnnulerAjout = ttk.Button(
            ligneImages, text="Annuler le dernier ajout", command=self._annulerDernierAjout
        )
        self._boutonAnnulerAjout.pack(side="left", padx=(8, 0))

        self._section(cadre, "Commentaire")
        ligneCommentaire = ttk.Frame(cadre)
        ligneCommentaire.pack(fill="x")
        champ = ttk.Entry(ligneCommentaire, textvariable=self._commentaire)
        champ.pack(side="left", fill="x", expand=True)
        champ.bind("<Return>", lambda _evenement: self._commenter())
        self._boutonCommenter = ttk.Button(
            ligneCommentaire, text="Ajouter", command=self._commenter
        )
        self._boutonCommenter.pack(side="left", padx=(8, 0))

        self._titreAttente = self._section(cadre, "")
        self._attente = self._zoneTexte(
            cadre, width=90, height=4, font="TkFixedFont", background="#f6f7f9", takefocus=False
        )
        self._attente.configure(state="disabled")

        ligneBas = ttk.Frame(cadre)
        ligneBas.pack(fill="x", pady=(14, 0))
        ttk.Button(ligneBas, text="Mettre en pause", command=self._mettreEnPause).pack(
            side="left"
        )
        self._boutonAppliquer = ttk.Button(
            ligneBas, text="Créer le ticket" if creation else "Appliquer",
            default="active", command=self._appliquer,
        )
        self._boutonAppliquer.pack(side="right")
        ttk.Button(ligneBas, text="Abandonner", command=self._abandonner).pack(
            side="right", padx=(0, 8)
        )

        self._texte.focus_set()
        self._texte.mark_set("insert", "end-1c")

    def _section(self, parent: ttk.Frame, texte: str) -> ttk.Label:
        etiquette = ttk.Label(parent, text=texte, font=self._policeSection)
        etiquette.pack(anchor="w", pady=(12, 4))
        return etiquette

    def _zoneTexte(self, parent: ttk.Frame, **options: object) -> tk.Text:
        """Zone de texte avec barre de défilement verticale."""
        cadre = ttk.Frame(parent)
        cadre.pack(fill="both", expand=True)
        zone = tk.Text(cadre, wrap="word", **options)
        defilement = ttk.Scrollbar(cadre, command=zone.yview)
        zone.configure(yscrollcommand=defilement.set)
        zone.pack(side="left", fill="both", expand=True)
        defilement.pack(side="right", fill="y")
        return zone

    # ------------------------------------------------------------------ lecture du modèle

    def _texteTape(self) -> str:
        return self._texte.get("1.0", "end-1c")

    def _actualiser(self) -> None:
        """Relit la session : compteur, liste en attente et boutons grisés."""
        session = self._controleur.session
        attente = session.modificationsEnAttente
        n = len(attente)
        pluriel = "s" if n > 1 else ""
        self._statut.configure(
            text=f"{session.libelle} active · {n} modification{pluriel} en attente"
        )
        self._titreAttente.configure(text=f"Modifications en attente ({n})")
        lignes = [f"{numero}. {libelle}" for numero, libelle in enumerate(attente, start=1)]
        self._attente.configure(state="normal")
        self._attente.delete("1.0", "end")
        self._attente.insert("1.0", "\n".join(lignes))
        self._attente.configure(state="disabled")

        self._activer(self._boutonAnnulerAjout, n > 0)
        self._activer(self._boutonCommenter, bool(self._commentaire.get().strip()))
        texte = bool(self._texteTape().strip())
        if self._controleur.estCreation:
            self._activer(self._boutonAppliquer, texte or self._controleur.nombreImages > 0)
        else:
            self._activer(self._boutonAppliquer, texte or n > 0)

    @staticmethod
    def _activer(bouton: ttk.Button, actif: bool) -> None:
        bouton.configure(state="normal" if actif else "disabled")

    # ------------------------------------------------------------------ frappe (undo du texte)

    def _annulerFrappe(self, _evenement: tk.Event) -> str:
        try:
            self._texte.edit_undo()
        except tk.TclError:
            pass  # rien à annuler
        return "break"

    def _retablirFrappe(self, _evenement: tk.Event) -> str:
        try:
            self._texte.edit_redo()
        except tk.TclError:
            pass  # rien à rétablir
        return "break"

    def _surFrappe(self, _evenement: tk.Event) -> None:
        # <<Modified>> n'est émis qu'au passage du drapeau à vrai : on le remet à faux.
        if self._texte.edit_modified():
            self._texte.edit_modified(False)
            self._actualiser()

    # ------------------------------------------------------------------ actions

    def _tenter(self, fonction: Callable[..., object], *args: object) -> bool:
        """Appelle fonction par executer() ; vrai si aucun refus n'a été affiché."""
        def appel() -> bool:
            fonction(*args)
            return True

        return self.executer(appel) is True

    def _ajouterImages(self) -> None:
        chemins = filedialog.askopenfilenames(
            parent=self, title="Ajouter des images",
            filetypes=[("Images PNG ou GIF", "*.png *.gif")],
        )
        if not chemins:
            return
        refus = self.executer(self._controleur.ajouterImages, list(chemins))
        if refus:
            pluriel = "s" if len(refus) > 1 else ""
            messagebox.showwarning(
                "Images refusées",
                f"{len(refus)} image{pluriel} refusée{pluriel} ; les autres sont ajoutées.",
                detail="\n".join(refus), parent=self,
            )
        self._actualiser()

    def _annulerDernierAjout(self) -> None:
        self.executer(self._controleur.annulerDerniere)
        self._actualiser()

    def _commenter(self) -> None:
        texte = self._commentaire.get().strip()
        if not texte:
            return
        if self._tenter(self._controleur.commenter, texte):
            self._commentaire.set("")
        self._actualiser()

    def _mettreEnPause(self) -> None:
        session = self._controleur.session
        # Une session déjà appliquée, abandonnée ou en pause n'est pas remise en pause.
        if not session.estOuverte or session.estEnPause:
            self.fermer()
            return
        if self._tenter(self._controleur.mettreEnPause, self._texteTape()):
            self.fermer()

    def _abandonner(self) -> None:
        session = self._controleur.session
        if self._texteTape().strip() or session.modificationsEnAttente:
            consequence = (
                "le ticket ne sera pas créé" if self._controleur.estCreation
                else "le ticket reste inchangé"
            )
            if not messagebox.askyesno(
                "Abandonner la session", "Abandonner cette session ?",
                detail="Le texte tapé et les modifications en attente seront perdus ; "
                       f"{consequence}.",
                icon="warning", default="no", parent=self,
            ):
                return
        if self._tenter(self._controleur.abandonner):
            self.fermer()

    def _appliquer(self) -> None:
        if self._tenter(self._controleur.appliquer, self._texteTape()):
            self.fermer()
        else:
            self._actualiser()
