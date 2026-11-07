"""Contrôleur de l'éditeur de description (F5) : sans tkinter, testable sans écran."""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

from ihm.passerelle.erreurs import ReponseInvalide, RequeteInvalide, RequeteTropVolumineuse
from ihm.passerelle.objets_lecture import BrouillonLu, RapportLu
from modele.exceptions import ArtefactInvalideException

if TYPE_CHECKING:
    from ihm.controleurs.controleur_principal import ControleurPrincipal
    from ihm.passerelle.client_api import ClientAPI
    from ihm.passerelle.objets_lecture import TicketRefLu
    from ihm.passerelle.source_tickets import SourceTickets

# Refus propres à une image : les autres images de la même sélection sont quand même ajoutées.
# ArtefactInvalideException : format refusé par le modèle ; RequeteInvalide : contenu illisible ;
# RequeteTropVolumineuse : plus de 5 Mo.
REFUS_IMAGE: tuple[type[Exception], ...] = (
    ArtefactInvalideException,
    RequeteInvalide,
    RequeteTropVolumineuse,
)


class ControleurEdition:
    """Un seul par brouillon (registre du ControleurPrincipal) : survit à la fermeture de F5.

    Le brouillon vit sur le serveur : sa pile de modifications, le texte gardé pendant la
    pause et les copies d'images. Le contrôleur n'en garde que la dernière représentation
    reçue, que chaque route du brouillon renvoie à jour. Après l'abandon ou l'application,
    le brouillon n'existe plus sur le serveur : le contrôleur le marque fermé.
    """

    def __init__(
        self,
        principal: ControleurPrincipal,
        client: ClientAPI,
        brouillon: BrouillonLu,
        source: SourceTickets,
    ) -> None:
        self._principal: ControleurPrincipal = principal
        self._client: ClientAPI = client
        self._brouillon: BrouillonLu = brouillon
        self._source: SourceTickets = source
        self._ferme: bool = False

    # ------------------------------------------------------------------ lecture du brouillon

    @property
    def brouillon(self) -> BrouillonLu:
        """Dernière représentation reçue du serveur."""
        return self._brouillon

    @property
    def brouillonId(self) -> int:
        return self._brouillon.id

    @property
    def ticket(self) -> TicketRefLu:
        """Ticket visé : numéro, titre et priorité (pour une création, pas encore dans le dépôt)."""
        return self._brouillon.ticket

    @property
    def estCreation(self) -> bool:
        """Vrai pour un brouillon de création : il reste vrai après l'application."""
        return self._brouillon.estCreation

    @property
    def libelle(self) -> str:
        return self._brouillon.libelle

    @property
    def estOuverte(self) -> bool:
        return not self._ferme and self._brouillon.estOuverte

    @property
    def estEnPause(self) -> bool:
        return self._brouillon.estEnPause

    @property
    def modificationsEnAttente(self) -> list[str]:
        return [] if self._ferme else self._brouillon.modificationsEnAttente

    @property
    def texteBrouillon(self) -> str:
        """Texte tapé dans F5, gardé par le serveur pendant la pause."""
        return "" if self._ferme else self._brouillon.texteBrouillon

    @property
    def nombreImages(self) -> int:
        """Images en attente : F5 grise « Créer le ticket » s'il n'y a ni texte ni image."""
        return 0 if self._ferme else self._brouillon.nombreImages

    def actualiser(self, brouillon: BrouillonLu) -> None:
        """Remplace la représentation gardée : la reprise depuis F3 la relit sur le serveur."""
        self._brouillon = brouillon
        self._ferme = False

    # ------------------------------------------------------------------ ajouts et undo

    def ajouterImages(self, chemins: list[str]) -> list[str]:
        """Agrégat : envoie chaque image et retourne les messages des images refusées.

        Une image illisible ou refusée par le serveur n'empêche pas les suivantes. Un autre
        refus (brouillon en pause ou fermé, serveur injoignable) arrête la sélection : les
        images déjà envoyées restent dans le brouillon.
        """
        refus: list[str] = []
        for chemin in chemins:
            nom = os.path.basename(chemin)
            try:
                with open(chemin, "rb") as fichier:
                    octets = fichier.read()
            except OSError as erreur:
                refus.append(f"{nom} : fichier illisible ({erreur.strerror or erreur})")
                continue
            try:
                self._recevoir(self._client.ajouterImage(self.brouillonId, nom, octets))
            except REFUS_IMAGE as erreur:
                refus.append(f"{nom} : {erreur}")
        return refus

    def commenter(self, texte: str) -> None:
        self._recevoir(self._client.ajouterCommentaire(self.brouillonId, texte))

    def annulerDerniere(self) -> str:
        """Retire la dernière modification en attente ; le serveur supprime la copie d'image."""
        reponse = self._client.annulerDerniereModification(self.brouillonId)
        if not isinstance(reponse, dict) or not isinstance(reponse.get("libelleRetire"), str):
            raise ReponseInvalide("Réponse de l'annulation sans libelleRetire", 200)
        self._recevoir(reponse.get("brouillon"))
        return reponse["libelleRetire"]

    # ------------------------------------------------------------------ cycle de vie

    def mettreEnPause(self, texte: str) -> None:
        """Le texte tapé n'entre pas dans la description : le serveur le garde jusqu'à la reprise."""
        self._recevoir(
            self._client.modifierBrouillon(self.brouillonId, enPause=True, texteBrouillon=texte)
        )
        self._principal.signalerBrouillons()

    def abandonner(self) -> None:
        """Le serveur supprime le brouillon et ses copies d'images ; le ticket reste inchangé."""
        self._client.abandonnerBrouillon(self.brouillonId)
        self._ferme = True
        self._principal.signalerBrouillons()

    def appliquer(self, texte: str) -> RapportLu:
        """Le texte tapé est ajouté à la description, puis le brouillon est appliqué au mieux.

        En cas de refus, le serveur retire le texte qu'il venait d'ajouter : un nouvel essai
        ne le doublera pas. Après le succès, la source est relue (le ticket créé ou modifié
        apparaît aussitôt dans F2 et F3) et le rapport s'affiche.
        """
        texteAjoute = texte.strip()
        rapport = RapportLu.depuisJSON(
            self._client.appliquerBrouillon(self.brouillonId, texteAjoute or None)
        )
        self._ferme = True
        self._source.rafraichir()
        self._principal.signalerBrouillons()
        self._principal.afficherRapport(rapport, rapport.libelle)
        return rapport

    def _recevoir(self, donnees: object) -> None:
        """Chaque route du brouillon renvoie sa représentation à jour : on la garde."""
        self._brouillon = BrouillonLu.depuisJSON(donnees)  # type: ignore[arg-type]
