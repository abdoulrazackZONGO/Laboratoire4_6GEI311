"""F6 : détail d'un ticket, commun aux deux rôles ; visualisation des descriptions."""
from __future__ import annotations

import base64
import math
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING

from ihm.passerelle.erreurs import EXCEPTIONS_PASSERELLE, RessourceIntrouvable
from ihm.vues.fenetre_base import EXCEPTIONS_AFFICHEES, FenetreBase, titreErreur

if TYPE_CHECKING:
    from ihm.controleurs.controleur_detail import ControleurDetail
    from ihm.passerelle.objets_lecture import ElementLu, TicketLu

# Au-delà de cette largeur, une image est réduite (subsample) pour tenir dans la fenêtre.
LARGEUR_MAX_IMAGE = 400


class VueDetail(FenetreBase):
    """Lecture seule : la vue n'utilise que les propriétés publiques du ticket et de ses éléments.

    Elle parcourt la liste reçue de F2 ou de F3 avec ‹ Précédent et Suivant ›.
    Abonnée à la source des tickets de la session : si un autre acteur commente ou change le
    statut du ticket affiché, l'affichage suit ; si le ticket est retiré, un message
    l'annonce, puis F6 passe au ticket suivant ou se ferme.

    Le ticket n'est jamais comparé avec `is` : chaque rafraîchissement de la source recrée les
    objets, seul l'identifiant les distingue. Les images sont téléchargées par le contrôleur.
    """

    def __init__(self, parent: tk.Misc, controleur: ControleurDetail) -> None:
        super().__init__(
            parent, f"Gestion des tickets : Ticket #{controleur.identifiantCourant}",
            [controleur.source],
        )
        self._controleur: ControleurDetail = controleur
        # PhotoImage doit rester référencée, sinon tkinter efface l'image affichée.
        self._images: list[tk.PhotoImage] = []
        self._construire()
        self.rafraichir()

    # ------------------------------------------------------------------ construction

    def _construire(self) -> None:
        cadre = ttk.Frame(self, padding=16)
        cadre.pack(fill="both", expand=True)
        # Les polices sont gardées en attribut : sans référence, tkinter les supprimerait.
        base = tkfont.nametofont("TkDefaultFont")
        self._policeGras = base.copy()
        self._policeGras.configure(weight="bold")
        self._policeTitre = base.copy()
        self._policeTitre.configure(size=13, weight="bold")
        self._policePetite = base.copy()
        self._policePetite.configure(size=max(abs(int(base.actual("size"))) - 1, 8))

        navigation = ttk.Frame(cadre)
        navigation.pack(fill="x")
        self._boutonPrecedent = ttk.Button(
            navigation, text="‹ Précédent", command=lambda: self._aller(-1)
        )
        self._boutonPrecedent.pack(side="left")
        self._position = ttk.Label(navigation)
        self._position.pack(side="left", padx=10)
        self._boutonSuivant = ttk.Button(navigation, text="Suivant ›", command=lambda: self._aller(1))
        self._boutonSuivant.pack(side="left")

        self._titre = ttk.Label(cadre, font=self._policeTitre)
        self._titre.pack(anchor="w", pady=(12, 6))

        # Informations : libellé discret au-dessus de la valeur, sur deux lignes de trois.
        bordure = tk.Frame(cadre, highlightthickness=1, highlightbackground="#c8ccd2")
        bordure.pack(fill="x")
        infos = ttk.Frame(bordure, padding=(12, 8))
        infos.pack(fill="x")
        self._valeurs: dict[str, ttk.Label] = {}
        champs = (
            ("statut", "STATUT"), ("priorite", "PRIORITÉ"), ("createur", "CRÉATEUR"),
            ("assigne", "ASSIGNÉ"), ("creation", "CRÉÉ LE"), ("miseAJour", "MIS À JOUR LE"),
        )
        for rang, (cle, libelle) in enumerate(champs):
            ligne, colonne = divmod(rang, 3)
            case = ttk.Frame(infos)
            case.grid(row=ligne, column=colonne, sticky="w", padx=(0, 40), pady=4)
            ttk.Label(case, text=libelle, foreground="gray45", font=self._policePetite).pack(
                anchor="w"
            )
            valeur = ttk.Label(case, font=self._policeGras)
            valeur.pack(anchor="w")
            self._valeurs[cle] = valeur
        for colonne in range(3):
            infos.columnconfigure(colonne, weight=1, uniform="infos")

        # Description et commentaires dans une seule zone défilante, en lecture seule :
        # le texte, les images (image_create) et les commentaires s'y enchaînent.
        zone = ttk.Frame(cadre)
        zone.pack(fill="both", expand=True, pady=(12, 0))
        self._contenu = tk.Text(
            zone, width=80, height=22, wrap="word", font="TkDefaultFont", relief="flat",
            borderwidth=0, highlightthickness=1, highlightbackground="#c8ccd2",
            highlightcolor="#c8ccd2", padx=12, pady=10, cursor="arrow", takefocus=False,
        )
        defilement = ttk.Scrollbar(zone, command=self._contenu.yview)
        self._contenu.configure(yscrollcommand=defilement.set)
        self._contenu.pack(side="left", fill="both", expand=True)
        defilement.pack(side="right", fill="y")
        # Les espacements viennent des styles (spacing1/3), pas de lignes vides.
        self._contenu.tag_configure("section", font=self._policeGras, spacing3=6)
        self._contenu.tag_configure("sectionSuivante", spacing1=16)
        self._contenu.tag_configure(
            "texte", lmargin1=10, lmargin2=10, rmargin=10, spacing1=2, spacing3=2,
            background="#f6f7f9",
        )
        self._contenu.tag_configure("finTexte", spacing3=12)
        self._contenu.tag_configure(
            "legende", foreground="gray45", font=self._policePetite, spacing1=2, spacing3=12
        )
        self._contenu.tag_configure("discret", foreground="gray45", spacing3=8)
        self._contenu.tag_configure("auteur", foreground="gray40", font=self._policePetite, spacing1=6)
        self._contenu.tag_configure("commentaire", lmargin1=10, lmargin2=10, spacing3=4)

        bas = ttk.Frame(cadre)
        bas.pack(fill="x", pady=(12, 0))
        boutonFermer = ttk.Button(bas, text="Fermer", command=self.fermer)
        boutonFermer.pack(side="right")
        boutonFermer.focus_set()
        self.bind("<Escape>", lambda _evenement: self.fermer())
        self.bind("<Alt-Left>", lambda _evenement: self._aller(-1))
        self.bind("<Alt-Right>", lambda _evenement: self._aller(1))

    # ------------------------------------------------------------------ lecture du modèle

    def rafraichir(self) -> None:
        """Redessine le ticket courant, tel que le contrôleur l'a lu, par ses propriétés."""
        ticket = self._controleur.ticket
        self.title(f"Gestion des tickets - Ticket #{ticket.ticketID} : {ticket.title}")
        self._position.configure(
            text=f"Ticket {self._controleur.position} sur {self._controleur.nombre}"
        )
        self._boutonPrecedent.configure(state="normal" if self._controleur.peutReculer else "disabled")
        self._boutonSuivant.configure(state="normal" if self._controleur.peutAvancer else "disabled")
        self._titre.configure(text=f"Ticket #{ticket.ticketID} - {ticket.title}")

        valeurs = {
            "statut": ticket.status.name,
            "priorite": ticket.priority.name,
            "createur": ticket.creator.name if ticket.creator is not None else "-",
            "assigne": ticket.assignedUser.name if ticket.assignedUser is not None else "-",
            "creation": str(ticket.creationDate),
            "miseAJour": str(ticket.updateDate),
        }
        for cle, valeur in valeurs.items():
            self._valeurs[cle].configure(text=valeur)

        contenu = self._contenu
        haut = contenu.yview()[0]
        contenu.configure(state="normal")
        contenu.delete("1.0", "end")
        self._images.clear()

        elements = ticket.description.elements
        pluriel = "s" if len(elements) > 1 else ""
        contenu.insert("end", f"Description ({len(elements)} élément{pluriel})\n", "section")
        if not elements:
            contenu.insert("end", "Aucune description.\n", "discret")
        for element in elements:
            self._afficherElement(element)

        commentaires = ticket.comments
        contenu.insert("end", f"Commentaires ({len(commentaires)})\n", ("section", "sectionSuivante"))
        if not commentaires:
            contenu.insert("end", "Aucun commentaire.\n", "discret")
        for commentaire in commentaires:
            contenu.insert("end", f"{commentaire.auteur.name} · {commentaire.date}\n", "auteur")
            contenu.insert("end", f"{commentaire.texte}\n", "commentaire")

        contenu.delete("end-2c", "end-1c")  # notre dernier saut de ligne (Tk garde le sien)
        contenu.configure(state="disabled")
        contenu.yview_moveto(haut)

    def _afficherElement(self, element: ElementLu) -> None:
        """Texte et image s'affichent ; la vidéo est hors du cadre du Lab 3."""
        contenu = self._contenu
        if element.typeArtefact == "texte":
            # Texte saisi ou texte importé : le serveur envoie le contenu dans les deux cas.
            lignes = (element.contenu or "").strip().split("\n")
            for rang, ligne in enumerate(lignes):
                derniere = rang == len(lignes) - 1
                contenu.insert("end", f"{ligne}\n", ("texte", "finTexte") if derniere else "texte")
        elif element.typeArtefact == "image":
            nom = element.nom
            try:
                octets = self._controleur.octetsImage(element)
            except EXCEPTIONS_PASSERELLE:
                # Une image qui manque ne doit pas empêcher de lire le reste du ticket.
                contenu.insert("end", f"Image indisponible : {nom}\n", "discret")
                return
            try:
                image = tk.PhotoImage(master=self, data=base64.b64encode(octets))
            except tk.TclError:
                contenu.insert("end", f"Image illisible : {nom}\n", "discret")
                return
            largeur, hauteur = image.width(), image.height()
            if largeur > LARGEUR_MAX_IMAGE:
                image = image.subsample(math.ceil(largeur / LARGEUR_MAX_IMAGE))
            self._images.append(image)
            contenu.image_create("end", image=image)
            contenu.insert("end", "\n")
            contenu.insert("end", f"{nom} · {largeur} × {hauteur} px\n", "legende")
        else:
            contenu.insert("end", f"Vidéo non affichée : {element.nom}\n", "discret")

    # ------------------------------------------------------------------ navigation

    def _aller(self, pas: int) -> None:
        if self.executer(self._controleur.aller, pas):
            self._contenu.yview_moveto(0)
            self.rafraichir()

    def fermer(self) -> None:
        self._controleur.fermer()
        super().fermer()

    # ------------------------------------------------------------------ notifications de la source

    def ticketModifie(self, ticket: TicketLu) -> None:
        # Seul le ticket affiché demande un redessin ; les autres seront relus en y arrivant.
        if self._controleur.parcourt(ticket.ticketID) and self._controleur.estCourant(ticket.ticketID):
            self._relire()

    def ticketAjoute(self, ticket: TicketLu) -> None:
        """Un nouveau ticket ne change pas la liste parcourue."""

    def ticketRetire(self, ticket: TicketLu) -> None:
        if not self._controleur.parcourt(ticket.ticketID):
            return
        etaitAffiche = self._controleur.retirer(ticket.ticketID)
        if etaitAffiche:
            messagebox.showinfo(
                "Ticket retiré", f"Le ticket #{ticket.ticketID} « {ticket.title} » "
                "a été retiré du dépôt.", parent=self,
            )
        if self._controleur.estVide:
            self.fermer()
        elif etaitAffiche:
            self._relire()  # F6 passe au ticket qui prend sa place
        else:
            self.rafraichir()  # seul « Ticket i sur n » change

    def _relire(self) -> None:
        """Relit le détail du ticket affiché puis redessine ; l'échec est affiché, pas levé.

        Un ticket supprimé juste avant la lecture est traité comme un ticket retiré : la
        notification de la source arrivera au prochain sondage, mais F6 ne doit pas l'attendre.
        """
        try:
            self._controleur.charger()
        except RessourceIntrouvable:
            return
        except EXCEPTIONS_AFFICHEES as erreur:
            messagebox.showerror(titreErreur(erreur), str(erreur), parent=self)
            return
        self.rafraichir()
