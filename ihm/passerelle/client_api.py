"""Passerelle HTTP du client : le seul module de la GUI qui fait des requêtes.

ClientAPI envoie et reçoit du JSON, ajoute l'en-tête X-Acteur-Id et relève en exceptions
les erreurs de l'API (voir erreurs.py). Ses méthodes d'opération portent le nom de
l'operationId correspondant dans openapi.yaml et rendent le JSON tel quel : les objets de
lecture (C2) le transforment ensuite pour les vues.

Le transport, c'est-à-dire l'envoi réel d'une requête, est remplaçable : urllib en
fonctionnement normal, un faux transport dans les tests, et plus tard le client de test de
Flask, sans rien changer à ClientAPI.
"""
from __future__ import annotations

import base64
import http.client
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol

from ihm.passerelle.erreurs import ReponseInvalide, ServeurInjoignable, exceptionDepuisReponse

if TYPE_CHECKING:
    from modele.enums import Priorite, Statut

URL_PAR_DEFAUT = "http://127.0.0.1:5000"
# Délai court : la GUI attend la réponse, elle ne doit pas rester figée longtemps.
DELAI_PAR_DEFAUT = 2.0
EN_TETE_ACTEUR = "X-Acteur-Id"

# Un objet JSON de l'API, tel que json.loads le rend.
ObjetJSON = dict[str, Any]


@dataclass(frozen=True)
class ReponseHTTP:
    """Ce qu'un transport rend : le code HTTP et le corps brut."""

    code: int
    corps: bytes


class Transport(Protocol):
    """Envoi d'une requête. Rend la réponse, même d'erreur (4xx, 5xx), et lève
    ServeurInjoignable quand le serveur ne répond pas."""

    def __call__(
        self, methode: str, url: str, entetes: dict[str, str], corps: bytes | None, delai: float
    ) -> ReponseHTTP: ...


# Aucun proxy : le serveur est sur ce poste ou sur le réseau local. Un proxy système
# (variable HTTP_PROXY, réglages de Windows) pourrait sinon intercepter 127.0.0.1.
_OUVREUR = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def transportUrllib(
    methode: str, url: str, entetes: dict[str, str], corps: bytes | None, delai: float
) -> ReponseHTTP:
    """Transport réel, par urllib : bibliothèque standard, aucune dépendance pour la GUI."""
    requete = urllib.request.Request(url, data=corps, headers=entetes, method=methode)
    try:
        try:
            with _OUVREUR.open(requete, timeout=delai) as reponse:
                return ReponseHTTP(reponse.status, reponse.read())
        except urllib.error.HTTPError as erreur:
            # Un code 4xx ou 5xx est une réponse du serveur, pas une panne : on la rend.
            try:
                return ReponseHTTP(erreur.code, erreur.read())
            finally:
                erreur.close()
    except (OSError, http.client.HTTPException) as erreur:
        raise ServeurInjoignable(url, _motif(erreur, delai)) from erreur


def _motif(erreur: BaseException, delai: float) -> str:
    """Motif lisible d'une panne réseau, pour la boîte d'erreur de la GUI."""
    cause: object = erreur.reason if isinstance(erreur, urllib.error.URLError) else erreur
    if isinstance(cause, TimeoutError):
        return f"pas de réponse en {delai:g} s"
    if isinstance(cause, ConnectionRefusedError):
        return "connexion refusée (le serveur est-il lancé ?)"
    return str(cause) or type(cause).__name__


class ClientAPI:
    """Client de l'API au nom d'un acteur.

    acteurId vaut None avant la connexion (fenêtre F1) : seules les opérations sans
    identification (listerActeurs, lireActeur, lireImage, lireVersion) sont alors utiles.
    Les brouillons et les lots sont rangés sous /acteur/{acteurId} : sans acteur, leurs
    méthodes lèvent ValueError avant d'envoyer quoi que ce soit (c'est un bug d'appel).

    Chaque méthode d'opération porte le nom de son operationId dans openapi.yaml. Deux
    opérations à plusieurs formes sont découpées pour rester simples à appeler :
    ouvrirBrouillon (ouvrirBrouillonCreation, ouvrirBrouillonEdition) et
    ajouterModification (ajouterCommentaire, ajouterTexte, ajouterImage).
    """

    def __init__(
        self,
        url: str = URL_PAR_DEFAUT,
        acteurId: int | None = None,
        *,
        transport: Transport | None = None,
        delai: float = DELAI_PAR_DEFAUT,
    ) -> None:
        self._url: str = url.rstrip("/")
        self._acteurId: int | None = acteurId
        self._transport: Transport = transport if transport is not None else transportUrllib
        self._delai: float = delai

    @property
    def url(self) -> str:
        return self._url

    @property
    def acteurId(self) -> int | None:
        return self._acteurId

    @property
    def delai(self) -> float:
        return self._delai

    # ------------------------------------------------------------------ requêtes génériques

    def get(self, chemin: str, parametres: dict[str, object] | None = None) -> Any:
        """GET ; les paramètres valant None sont omis, les enums passent par leur nom."""
        return self._requeteJSON("GET", chemin, parametres=parametres)

    def post(self, chemin: str, corps: object | None = None) -> Any:
        return self._requeteJSON("POST", chemin, corps=corps)

    def patch(self, chemin: str, corps: object) -> Any:
        return self._requeteJSON("PATCH", chemin, corps=corps)

    def delete(self, chemin: str) -> Any:
        return self._requeteJSON("DELETE", chemin)

    def lireOctets(self, chemin: str) -> bytes:
        """GET d'une ressource binaire : les octets tels quels.

        Sert aux images ; chemin peut être le champ url d'un élément de description
        (/ticket/{ticketId}/image/{nomImage}).
        """
        return self._envoyer("GET", chemin).corps

    # ------------------------------------------------------------------ acteurs (sans identification)

    def listerActeurs(self, role: str | None = None) -> list[ObjetJSON]:
        """F1 (connexion) ; role="User" pour le choix de l'assigné dans F7."""
        return self.get("/acteurs", {"role": role})

    def lireActeur(self, acteurId: int) -> ObjetJSON:
        return self.get(f"/acteur/{_segment(acteurId)}")

    # ------------------------------------------------------------------ tickets

    def listerTickets(
        self,
        statut: Statut | None = None,
        createur: int | None = None,
        assigne: int | None = None,
    ) -> list[ObjetJSON]:
        """Résumés des tickets ; les filtres donnés se combinent (ET)."""
        return self.get(
            "/tickets", {"statut": statut, "createur": createur, "assigne": assigne}
        )

    def creerTicket(self, titre: str, priorite: Priorite, texte: str) -> ObjetJSON:
        """Création en une requête, sans image ni pause ; rend {"ticket", "rapport"}."""
        return self.post(
            "/tickets", {"titre": titre, "priorite": priorite.name, "texte": texte}
        )

    def lireTicket(self, ticketId: int) -> ObjetJSON:
        """Détail complet : résumé, commentaires et description (F6)."""
        return self.get(f"/ticket/{_segment(ticketId)}")

    def changerStatut(
        self, ticketId: int, statut: Statut, assigneId: int | None = None
    ) -> ObjetJSON:
        """PATCH du statut ; assigneId seulement pour ASSIGNE. Rend le ticket à jour."""
        corps: dict[str, object] = {"statut": statut.name}
        if assigneId is not None:
            corps["assigneId"] = assigneId
        return self.patch(f"/ticket/{_segment(ticketId)}", corps)

    def supprimerTicket(self, ticketId: int) -> None:
        self.delete(f"/ticket/{_segment(ticketId)}")

    def listerCommentaires(self, ticketId: int) -> list[ObjetJSON]:
        return self.get(f"/ticket/{_segment(ticketId)}/commentaires")

    def lireDescription(self, ticketId: int) -> list[ObjetJSON]:
        return self.get(f"/ticket/{_segment(ticketId)}/description")

    def lireImage(self, ticketId: int, nomImage: str) -> bytes:
        """Octets d'une image de la description ; le nom est échappé (pas de ../ possible)."""
        return self.lireOctets(f"/ticket/{_segment(ticketId)}/image/{_segment(nomImage)}")

    # ------------------------------------------------------------------ brouillons (User)

    def listerBrouillons(self) -> list[ObjetJSON]:
        """Brouillons ouverts de l'acteur, de création et d'édition, en pause ou non."""
        return self.get(f"{self._cheminActeur()}/brouillons")

    def ouvrirBrouillonCreation(self, titre: str, priorite: Priorite) -> ObjetJSON:
        """ouvrirBrouillon, forme creation : le numéro du ticket est donné par le serveur."""
        return self.post(
            f"{self._cheminActeur()}/brouillons",
            {"type": "creation", "titre": titre, "priorite": priorite.name},
        )

    def ouvrirBrouillonEdition(self, ticketId: int) -> ObjetJSON:
        """ouvrirBrouillon, forme edition : 409 si un brouillon est déjà ouvert sur ce ticket."""
        return self.post(
            f"{self._cheminActeur()}/brouillons", {"type": "edition", "ticketId": ticketId}
        )

    def lireBrouillon(self, brouillonId: int) -> ObjetJSON:
        return self.get(self._cheminBrouillon(brouillonId))

    def modifierBrouillon(
        self,
        brouillonId: int,
        *,
        enPause: bool | None = None,
        texteBrouillon: str | None = None,
    ) -> ObjetJSON:
        """Pause (enPause=True, avec le texte tapé à garder) ou reprise (enPause=False)."""
        corps: dict[str, object] = {}
        if enPause is not None:
            corps["enPause"] = enPause
        if texteBrouillon is not None:
            corps["texteBrouillon"] = texteBrouillon
        if not corps:
            raise ValueError("modifierBrouillon : enPause ou texteBrouillon est obligatoire")
        return self.patch(self._cheminBrouillon(brouillonId), corps)

    def abandonnerBrouillon(self, brouillonId: int) -> None:
        self.delete(self._cheminBrouillon(brouillonId))

    def listerModifications(self, brouillonId: int) -> list[str]:
        """Libellés des modifications en attente, dans l'ordre d'ajout."""
        return self.get(f"{self._cheminBrouillon(brouillonId)}/modifications")

    def ajouterCommentaire(self, brouillonId: int, texte: str) -> ObjetJSON:
        """ajouterModification, type commentaire ; rend le brouillon à jour."""
        return self._ajouterModification(brouillonId, {"type": "commentaire", "texte": texte})

    def ajouterTexte(self, brouillonId: int, texte: str) -> ObjetJSON:
        """ajouterModification, type texte (texte saisi) ; rend le brouillon à jour."""
        return self._ajouterModification(brouillonId, {"type": "texte", "texte": texte})

    def ajouterImage(self, brouillonId: int, nomFichier: str, octets: bytes) -> ObjetJSON:
        """ajouterModification, type image : les octets voyagent en base64 dans le JSON.

        Le contrôle du format (.png ou .gif) reste au serveur, qui répond 400 sinon.
        """
        contenu = base64.b64encode(octets).decode("ascii")
        return self._ajouterModification(
            brouillonId, {"type": "image", "nomFichier": nomFichier, "contenuBase64": contenu}
        )

    def annulerDerniereModification(self, brouillonId: int) -> ObjetJSON:
        """Undo ; rend {"libelleRetire", "brouillon"}."""
        return self.delete(f"{self._cheminBrouillon(brouillonId)}/modification/derniere")

    def appliquerBrouillon(self, brouillonId: int, texte: str | None = None) -> ObjetJSON:
        """Applique le brouillon, après y avoir ajouté le texte tapé s'il y en a un.

        Rend le rapport d'exécution ; son ticketId désigne le ticket créé, s'il y en a un.
        """
        corps: dict[str, object] = {} if texte is None else {"texte": texte}
        return self.post(f"{self._cheminBrouillon(brouillonId)}/application", corps)

    # ------------------------------------------------------------------ lots (Admin)

    def appliquerLot(
        self, action: str, ticketIds: list[int], assigneId: int | None = None
    ) -> ObjetJSON:
        """action : assigner, desassigner, valider ou fermer. Rend le rapport d'exécution."""
        corps: dict[str, object] = {"action": action, "ticketIds": list(ticketIds)}
        if assigneId is not None:
            corps["assigneId"] = assigneId
        return self.post(f"{self._cheminActeur()}/lots", corps)

    # ------------------------------------------------------------------ système

    def lireVersion(self) -> int:
        """Compteur de modifications du dépôt, interrogé environ toutes les secondes (C2)."""
        donnees = self.get("/version")
        version = donnees.get("version") if isinstance(donnees, dict) else None
        # bool est une sous-classe de int en Python : on l'écarte explicitement.
        if not isinstance(version, int) or isinstance(version, bool):
            raise ReponseInvalide("Réponse de /version sans compteur entier", 200)
        return version

    # ------------------------------------------------------------------ mécanique

    def _ajouterModification(self, brouillonId: int, corps: dict[str, object]) -> ObjetJSON:
        return self.post(f"{self._cheminBrouillon(brouillonId)}/modifications", corps)

    def _cheminActeur(self) -> str:
        """/acteur/{acteurId} de l'acteur connecté : brouillons et lots sont rangés sous lui."""
        if self._acteurId is None:
            raise ValueError("Opération réservée à un acteur connecté : ClientAPI sans acteurId")
        return f"/acteur/{_segment(self._acteurId)}"

    def _cheminBrouillon(self, brouillonId: int) -> str:
        return f"{self._cheminActeur()}/brouillon/{_segment(brouillonId)}"

    def _requeteJSON(
        self,
        methode: str,
        chemin: str,
        *,
        parametres: dict[str, object] | None = None,
        corps: object | None = None,
    ) -> Any:
        """Envoie la requête et décode le JSON ; None pour une réponse sans corps (204)."""
        reponse = self._envoyer(methode, chemin, parametres=parametres, corps=corps)
        if reponse.code == 204 or not reponse.corps:
            return None
        try:
            return json.loads(reponse.corps.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise ReponseInvalide(
                f"Réponse illisible du serveur pour {methode} {chemin}", reponse.code
            ) from None

    def _envoyer(
        self,
        methode: str,
        chemin: str,
        *,
        parametres: dict[str, object] | None = None,
        corps: object | None = None,
    ) -> ReponseHTTP:
        """Construit la requête, la confie au transport et relève les réponses d'erreur."""
        url = self._url + chemin
        chaine = _chaineRequete(parametres)
        if chaine:
            url += "?" + chaine
        entetes: dict[str, str] = {}
        if self._acteurId is not None:
            entetes[EN_TETE_ACTEUR] = str(self._acteurId)
        donnees: bytes | None = None
        if corps is not None:
            donnees = json.dumps(corps, ensure_ascii=False).encode("utf-8")
            entetes["Content-Type"] = "application/json"
        reponse = self._transport(methode, url, entetes, donnees, self._delai)
        if reponse.code >= 400:
            raise exceptionDepuisReponse(reponse.code, reponse.corps)
        return reponse


def _segment(valeur: object) -> str:
    """Segment de chemin échappé : un nom comme ../x ne peut pas changer de chemin."""
    return urllib.parse.quote(str(valeur), safe="")


def _chaineRequete(parametres: dict[str, object] | None) -> str:
    """Chaîne de requête ; les paramètres None sont omis."""
    if not parametres:
        return ""
    retenus = {nom: _texte(valeur) for nom, valeur in parametres.items() if valeur is not None}
    return urllib.parse.urlencode(retenus)


def _texte(valeur: object) -> str:
    """Valeur d'un paramètre de requête : les enums par leur nom, comme dans le JSON."""
    return valeur.name if isinstance(valeur, Enum) else str(valeur)
