"""Tests de la passerelle HTTP du client (C1), sans serveur de l'API.

Un faux transport rend les exemples de openapi.yaml : on vérifie ce que chaque opération
envoie (méthode, chemin, en-têtes, corps) et ce qu'elle rend. Un mini serveur http.server
vérifie ensuite le vrai transport urllib (en-têtes, erreurs HTTP, délai dépassé, serveur
arrêté). Une fois S2 fusionné, des tests contre le client de test de Flask s'ajouteront.
"""
from __future__ import annotations

import base64
import json
import re
import socket
import threading
import time
import unittest
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from ihm.passerelle.client_api import DELAI_PAR_DEFAUT, EN_TETE_ACTEUR, ClientAPI, ReponseHTTP
from ihm.passerelle.erreurs import (
    EXCEPTIONS_PASSERELLE,
    ActeurNonIdentifie,
    ErreurInterne,
    ErreurServeur,
    MethodeNonPermise,
    ReponseInvalide,
    RequeteInvalide,
    RequeteTropVolumineuse,
    RessourceIntrouvable,
    ServeurInjoignable,
    exceptionDepuisReponse,
)
from modele.enums import Priorite, Statut
from modele.exceptions import (
    AccesRefuseException,
    ArtefactInvalideException,
    SessionIndisponibleException,
    SuppressionInterditeException,
    TransitionInvalideException,
)

if TYPE_CHECKING:
    from collections.abc import Callable

racineDepot = Path(__file__).resolve().parent.parent
URL = "http://serveur.test"

# ------------------------------------------------------------------ exemples de openapi.yaml

EXEMPLE_ACTEURS: list[dict[str, Any]] = [
    {"id": 2, "nom": "Abdoul Razack", "courriel": "abdoul@uqac.ca", "role": "User"},
    {"id": 3, "nom": "T Julien", "courriel": "julien@uqac.ca", "role": "User"},
]
EXEMPLE_ACTEUR: dict[str, Any] = {
    "id": 1, "nom": "Ambroise Fleury", "courriel": "ambroise@uqac.ca", "role": "Admin",
}
EXEMPLE_TICKET_RESUME: dict[str, Any] = {
    "id": 2, "titre": "Erreur d'affichage mobile", "priorite": "MOYENNE", "statut": "ASSIGNE",
    "createur": {"id": 2, "nom": "Abdoul Razack"}, "assigne": {"id": 5, "nom": "Hein Tommy"},
    "dateCreation": "2026-10-20", "dateMiseAJour": "2026-10-20", "dejaAssigne": True,
    "transitionsPermises": ["OUVERT", "ASSIGNE", "VALIDATION", "FERME"],
    "nombreCommentaires": 0,
}
EXEMPLE_TICKET_DETAIL: dict[str, Any] = {
    "id": 1, "titre": "Bug de connexion", "priorite": "HAUTE", "statut": "TERMINE",
    "createur": {"id": 2, "nom": "Abdoul Razack"}, "assigne": {"id": 4, "nom": "Mike Tonny"},
    "dateCreation": "2026-10-20", "dateMiseAJour": "2026-10-20", "dejaAssigne": True,
    "transitionsPermises": [], "nombreCommentaires": 2,
    "commentaires": [
        {"texte": "Le bug se reproduit sur Chrome et Firefox.",
         "auteur": {"id": 2, "nom": "Abdoul Razack"}, "date": "2026-10-20"},
        {"texte": "Capture d'écran jointe à la description.",
         "auteur": {"id": 2, "nom": "Abdoul Razack"}, "date": "2026-10-20"},
    ],
    "description": [
        {"type": "texte_saisi", "nom": "texte saisi",
         "resume": "[Texte] texte saisi (205 caractères)",
         "contenu": "Bug : impossible de se connecter à l'application."},
        {"type": "image", "nom": "demo_connexion.png",
         "resume": "[Image] demo_connexion.png (757 octets)",
         "url": "/ticket/1/image/demo_connexion.png"},
    ],
}
EXEMPLE_BROUILLON: dict[str, Any] = {
    "id": 1, "type": "creation", "libelle": "Session de création",
    "ticket": {"id": 11, "titre": "Paiement refusé", "priorite": "MOYENNE"},
    "proprietaire": {"id": 3, "nom": "T Julien"}, "ouverte": True, "enPause": False,
    "modificationsEnAttente": [], "nombreImages": 0, "texteBrouillon": "",
}
EXEMPLE_MODIFICATIONS: list[str] = [
    "Ajouter l'élément [Image] capture.png (2048 octets) au ticket #11",
    "Ajouter le commentaire « Testé sur Firefox aussi. » au ticket #11",
]
EXEMPLE_RAPPORT_CREATION: dict[str, Any] = {
    "libelle": "Session de création",
    "succes": ["Ajouter l'élément [Texte] texte saisi (43 caractères) au ticket #11"],
    "refus": [], "nombreSucces": 1, "nombreRefus": 0, "ticketId": 11,
}
EXEMPLE_RAPPORT_LOT: dict[str, Any] = {
    "libelle": "Lot administrateur",
    "succes": ["Assigner le ticket #6 à Mike Tonny", "Assigner le ticket #7 à Mike Tonny"],
    "refus": [{"operation": "Assigner le ticket #3 à Mike Tonny",
               "motif": "Transition invalide : impossible de passer de l'état FERME au statut ASSIGNE"}],
    "nombreSucces": 2, "nombreRefus": 1, "ticketId": None,
}
RESULTAT_CREATION: dict[str, Any] = {"ticket": EXEMPLE_TICKET_DETAIL, "rapport": EXEMPLE_RAPPORT_CREATION}
RESULTAT_ANNULATION: dict[str, Any] = {
    "libelleRetire": EXEMPLE_MODIFICATIONS[1], "brouillon": EXEMPLE_BROUILLON,
}
MESSAGE_TRANSITION = (
    "Transition invalide : impossible de passer de l'état TERMINE au statut FERME"
)
OCTETS_PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(16))

# ------------------------------------------------------------------ faux transport


def reponseJSON(donnees: Any, code: int = 200) -> ReponseHTTP:
    return ReponseHTTP(code, json.dumps(donnees, ensure_ascii=False).encode("utf-8"))


def reponseErreur(code: int, typeErreur: str, message: str) -> ReponseHTTP:
    return reponseJSON({"erreur": {"type": typeErreur, "message": message}}, code)


REPONSE_VIDE = ReponseHTTP(204, b"")


@dataclass
class RequeteNotee:
    methode: str
    url: str
    entetes: dict[str, str]
    corps: bytes | None
    delai: float

    @property
    def corpsJSON(self) -> Any:
        return None if self.corps is None else json.loads(self.corps.decode("utf-8"))


class FauxTransport:
    """Remplace le réseau : note chaque requête et rend les réponses préparées, dans l'ordre."""

    def __init__(self, *reponses: ReponseHTTP | Exception) -> None:
        self._reponses: list[ReponseHTTP | Exception] = list(reponses)
        self.requetes: list[RequeteNotee] = []

    def __call__(
        self, methode: str, url: str, entetes: dict[str, str], corps: bytes | None, delai: float
    ) -> ReponseHTTP:
        self.requetes.append(RequeteNotee(methode, url, dict(entetes), corps, delai))
        reponse = self._reponses.pop(0)
        if isinstance(reponse, Exception):
            raise reponse
        return reponse

    @property
    def derniere(self) -> RequeteNotee:
        return self.requetes[-1]


def clientEssai(
    *reponses: ReponseHTTP | Exception, acteurId: int | None = 2, delai: float = DELAI_PAR_DEFAUT
) -> tuple[ClientAPI, FauxTransport]:
    transport = FauxTransport(*reponses)
    return ClientAPI(URL, acteurId, transport=transport, delai=delai), transport


# ------------------------------------------------------------------ reconstruction des erreurs


class TestReconstructionErreurs(unittest.TestCase):
    """exceptionDepuisReponse : même classe et même message que côté serveur."""

    def erreurServeur(self, erreur: Exception) -> ErreurServeur:
        self.assertIsInstance(erreur, ErreurServeur)
        return cast("ErreurServeur", erreur)

    def test_exceptionsMetierReconstruites(self) -> None:
        cas: list[tuple[int, type[Exception], str]] = [
            (409, TransitionInvalideException, MESSAGE_TRANSITION),
            (409, SessionIndisponibleException, "Session d'édition en pause : ajout impossible"),
            (409, SuppressionInterditeException,
             "Le ticket 2 a déjà été assigné : suppression interdite"),
            (403, AccesRefuseException, "T Julien n'est pas le créateur du ticket 2"),
            (400, ArtefactInvalideException, "Texte saisi vide"),
        ]
        for code, classe, message in cas:
            with self.subTest(classe=classe.__name__):
                erreur = exceptionDepuisReponse(
                    code, reponseErreur(code, classe.__name__, message).corps
                )
                self.assertIs(type(erreur), classe)
                self.assertEqual(str(erreur), message)

    def test_transitionInvalideAttrapeeCommeAuLab3(self) -> None:
        """Option A : le constructeur à deux statuts n'est pas appelé, et except la reconnaît."""
        client, _ = clientEssai(
            reponseErreur(409, "TransitionInvalideException", MESSAGE_TRANSITION)
        )
        with self.assertRaises(TransitionInvalideException) as contexte:
            client.changerStatut(1, Statut.FERME)
        self.assertEqual(str(contexte.exception), MESSAGE_TRANSITION)

    def test_erreursPropresALAPI(self) -> None:
        cas: list[tuple[int, type[ErreurServeur], str]] = [
            (400, RequeteInvalide, "Champ obligatoire manquant : statut"),
            (401, ActeurNonIdentifie, "En-tête X-Acteur-Id absent"),
            (404, RessourceIntrouvable, "Ticket introuvable : 99"),
            (405, MethodeNonPermise, "Méthode GET non permise sur /acteur/1/lots"),
            (413, RequeteTropVolumineuse, "Requête trop volumineuse (8 Mo au plus)"),
            (500, ErreurInterne, "Erreur interne du serveur"),
        ]
        for code, classe, message in cas:
            with self.subTest(classe=classe.__name__):
                erreur = self.erreurServeur(exceptionDepuisReponse(
                    code, reponseErreur(code, classe.__name__, message).corps
                ))
                self.assertIs(type(erreur), classe)
                self.assertEqual(str(erreur), message)
                self.assertEqual(erreur.code, code)
                self.assertEqual(erreur.typeErreur, classe.__name__)

    def test_typeInconnuGardeSonMessage(self) -> None:
        erreur = self.erreurServeur(exceptionDepuisReponse(
            418, reponseErreur(418, "ErreurFuture", "Message lisible").corps
        ))
        self.assertIs(type(erreur), ErreurServeur)
        self.assertEqual(str(erreur), "Message lisible")
        self.assertEqual((erreur.code, erreur.typeErreur), (418, "ErreurFuture"))

    def test_corpsIllisible(self) -> None:
        corps = {
            "page HTML d'un proxy": b"<html>502 Bad Gateway</html>",
            "vide": b"",
            "sans cle erreur": b'{"message": "x"}',
            "liste": b"[1, 2]",
            "type non texte": b'{"erreur": {"type": 3, "message": "x"}}',
            "sans message": b'{"erreur": {"type": "RequeteInvalide"}}',
            "pas de l'UTF-8": b"\xff\xfe\xfd",
        }
        for nom, octets in corps.items():
            with self.subTest(cas=nom):
                erreur = self.erreurServeur(exceptionDepuisReponse(502, octets))
                self.assertIs(type(erreur), ReponseInvalide)
                self.assertEqual(erreur.code, 502)

    def test_exceptionsAffichablesParLaGUI(self) -> None:
        """FenetreBase.executer() ajoutera EXCEPTIONS_PASSERELLE à sa liste (C3)."""
        for classe in (
            ServeurInjoignable, RequeteInvalide, ActeurNonIdentifie, RessourceIntrouvable,
            MethodeNonPermise, RequeteTropVolumineuse, ErreurInterne, ReponseInvalide,
        ):
            with self.subTest(classe=classe.__name__):
                self.assertTrue(issubclass(classe, EXCEPTIONS_PASSERELLE))


# ------------------------------------------------------------------ requêtes génériques


class TestRequetes(unittest.TestCase):
    """Ce que ClientAPI confie au transport, et comment il lit la réponse."""

    def test_enTeteActeur(self) -> None:
        client, transport = clientEssai(reponseJSON([]), acteurId=3)
        client.listerTickets()
        self.assertEqual(transport.derniere.entetes[EN_TETE_ACTEUR], "3")

    def test_sansActeurPasDEnTete(self) -> None:
        client, transport = clientEssai(reponseJSON(EXEMPLE_ACTEURS), acteurId=None)
        self.assertEqual(client.listerActeurs(), EXEMPLE_ACTEURS)
        self.assertNotIn(EN_TETE_ACTEUR, transport.derniere.entetes)

    def test_urlSansBarreFinaleEtFiltresOmis(self) -> None:
        transport = FauxTransport(reponseJSON([EXEMPLE_TICKET_RESUME]))
        client = ClientAPI(URL + "/", 2, transport=transport)
        client.listerTickets(statut=Statut.ASSIGNE, createur=2)
        self.assertEqual(transport.derniere.url, URL + "/tickets?statut=ASSIGNE&createur=2")

    def test_corpsJSONEnUTF8(self) -> None:
        client, transport = clientEssai(reponseJSON(RESULTAT_CREATION, 201))
        client.creerTicket("Paiement refusé", Priorite.HAUTE, "Carte refusée « sans message ».")
        requete = transport.derniere
        self.assertEqual(requete.entetes["Content-Type"], "application/json")
        assert requete.corps is not None
        # ensure_ascii=False : les accents voyagent en UTF-8, pas en é.
        self.assertIn("Paiement refusé".encode("utf-8"), requete.corps)
        self.assertEqual(requete.corpsJSON["texte"], "Carte refusée « sans message ».")

    def test_getSansCorps(self) -> None:
        client, transport = clientEssai(reponseJSON(EXEMPLE_TICKET_DETAIL))
        client.lireTicket(1)
        self.assertIsNone(transport.derniere.corps)
        self.assertNotIn("Content-Type", transport.derniere.entetes)

    def test_delai(self) -> None:
        self.assertEqual(DELAI_PAR_DEFAUT, 2.0)
        client, transport = clientEssai(reponseJSON({"version": 1}))
        client.lireVersion()
        self.assertEqual(transport.derniere.delai, 2.0)
        client, transport = clientEssai(reponseJSON({"version": 1}), delai=0.5)
        client.lireVersion()
        self.assertEqual(transport.derniere.delai, 0.5)

    def test_reponseSansCorps(self) -> None:
        client, _ = clientEssai(REPONSE_VIDE)
        self.assertIsNone(client.delete("/ticket/6"))

    def test_reponseNonJSON(self) -> None:
        client, _ = clientEssai(ReponseHTTP(200, b"<html>ok</html>"))
        with self.assertRaises(ReponseInvalide):
            client.lireTicket(1)

    def test_erreurRelevee(self) -> None:
        client, _ = clientEssai(reponseErreur(404, "RessourceIntrouvable", "Ticket introuvable : 99"))
        with self.assertRaises(RessourceIntrouvable) as contexte:
            client.lireTicket(99)
        self.assertEqual(str(contexte.exception), "Ticket introuvable : 99")

    def test_serveurInjoignableTransmis(self) -> None:
        client, _ = clientEssai(ServeurInjoignable(URL, "connexion refusée"))
        with self.assertRaises(ServeurInjoignable):
            client.lireVersion()

    def test_segmentsEchappes(self) -> None:
        client, transport = clientEssai(ReponseHTTP(200, OCTETS_PNG))
        client.lireImage(1, "../donnees/sauvegarde.json")
        self.assertEqual(
            transport.derniere.url, URL + "/ticket/1/image/..%2Fdonnees%2Fsauvegarde.json"
        )


# ------------------------------------------------------------------ opérations du contrat

# (operationId et variante, appel, méthode, chemin attendu, corps attendu, réponse, résultat)
CAS_OPERATIONS: list[tuple[str, Callable[[ClientAPI], Any], str, str, Any, ReponseHTTP, Any]] = [
    ("listerActeurs", lambda c: c.listerActeurs(), "GET", "/acteurs", None,
     reponseJSON(EXEMPLE_ACTEURS), EXEMPLE_ACTEURS),
    ("listerActeurs (role)", lambda c: c.listerActeurs(role="User"), "GET", "/acteurs?role=User",
     None, reponseJSON(EXEMPLE_ACTEURS), EXEMPLE_ACTEURS),
    ("lireActeur", lambda c: c.lireActeur(1), "GET", "/acteur/1", None,
     reponseJSON(EXEMPLE_ACTEUR), EXEMPLE_ACTEUR),
    ("listerTickets", lambda c: c.listerTickets(statut=Statut.ASSIGNE, createur=2), "GET",
     "/tickets?statut=ASSIGNE&createur=2", None,
     reponseJSON([EXEMPLE_TICKET_RESUME]), [EXEMPLE_TICKET_RESUME]),
    ("listerTickets (assigne)", lambda c: c.listerTickets(assigne=5), "GET",
     "/tickets?assigne=5", None, reponseJSON([EXEMPLE_TICKET_RESUME]), [EXEMPLE_TICKET_RESUME]),
    ("creerTicket",
     lambda c: c.creerTicket("Paiement refusé", Priorite.HAUTE, "La carte est refusée sans message."),
     "POST", "/tickets",
     {"titre": "Paiement refusé", "priorite": "HAUTE", "texte": "La carte est refusée sans message."},
     reponseJSON(RESULTAT_CREATION, 201), RESULTAT_CREATION),
    ("lireTicket", lambda c: c.lireTicket(1), "GET", "/ticket/1", None,
     reponseJSON(EXEMPLE_TICKET_DETAIL), EXEMPLE_TICKET_DETAIL),
    ("changerStatut (assigner)", lambda c: c.changerStatut(6, Statut.ASSIGNE, assigneId=3),
     "PATCH", "/ticket/6", {"statut": "ASSIGNE", "assigneId": 3},
     reponseJSON(EXEMPLE_TICKET_DETAIL), EXEMPLE_TICKET_DETAIL),
    ("changerStatut (soumettre)", lambda c: c.changerStatut(6, Statut.VALIDATION),
     "PATCH", "/ticket/6", {"statut": "VALIDATION"},
     reponseJSON(EXEMPLE_TICKET_DETAIL), EXEMPLE_TICKET_DETAIL),
    ("supprimerTicket", lambda c: c.supprimerTicket(6), "DELETE", "/ticket/6", None,
     REPONSE_VIDE, None),
    ("listerCommentaires", lambda c: c.listerCommentaires(1), "GET", "/ticket/1/commentaires",
     None, reponseJSON(EXEMPLE_TICKET_DETAIL["commentaires"]),
     EXEMPLE_TICKET_DETAIL["commentaires"]),
    ("lireDescription", lambda c: c.lireDescription(1), "GET", "/ticket/1/description", None,
     reponseJSON(EXEMPLE_TICKET_DETAIL["description"]), EXEMPLE_TICKET_DETAIL["description"]),
    ("lireImage", lambda c: c.lireImage(1, "demo_connexion.png"), "GET",
     "/ticket/1/image/demo_connexion.png", None, ReponseHTTP(200, OCTETS_PNG), OCTETS_PNG),
    ("listerBrouillons", lambda c: c.listerBrouillons(), "GET", "/acteur/2/brouillons", None,
     reponseJSON([EXEMPLE_BROUILLON]), [EXEMPLE_BROUILLON]),
    ("ouvrirBrouillon (creation)",
     lambda c: c.ouvrirBrouillonCreation("Paiement refusé", Priorite.MOYENNE),
     "POST", "/acteur/2/brouillons",
     {"type": "creation", "titre": "Paiement refusé", "priorite": "MOYENNE"},
     reponseJSON(EXEMPLE_BROUILLON, 201), EXEMPLE_BROUILLON),
    ("ouvrirBrouillon (edition)", lambda c: c.ouvrirBrouillonEdition(6),
     "POST", "/acteur/2/brouillons", {"type": "edition", "ticketId": 6},
     reponseJSON(EXEMPLE_BROUILLON, 201), EXEMPLE_BROUILLON),
    ("lireBrouillon", lambda c: c.lireBrouillon(1), "GET", "/acteur/2/brouillon/1", None,
     reponseJSON(EXEMPLE_BROUILLON), EXEMPLE_BROUILLON),
    ("modifierBrouillon (pause)",
     lambda c: c.modifierBrouillon(1, enPause=True, texteBrouillon="Le paiement échoue depuis lundi."),
     "PATCH", "/acteur/2/brouillon/1",
     {"enPause": True, "texteBrouillon": "Le paiement échoue depuis lundi."},
     reponseJSON(EXEMPLE_BROUILLON), EXEMPLE_BROUILLON),
    ("modifierBrouillon (reprise)", lambda c: c.modifierBrouillon(1, enPause=False),
     "PATCH", "/acteur/2/brouillon/1", {"enPause": False},
     reponseJSON(EXEMPLE_BROUILLON), EXEMPLE_BROUILLON),
    ("abandonnerBrouillon", lambda c: c.abandonnerBrouillon(1), "DELETE",
     "/acteur/2/brouillon/1", None, REPONSE_VIDE, None),
    ("listerModifications", lambda c: c.listerModifications(1), "GET",
     "/acteur/2/brouillon/1/modifications", None,
     reponseJSON(EXEMPLE_MODIFICATIONS), EXEMPLE_MODIFICATIONS),
    ("ajouterModification (commentaire)",
     lambda c: c.ajouterCommentaire(1, "Testé sur Firefox aussi."),
     "POST", "/acteur/2/brouillon/1/modifications",
     {"type": "commentaire", "texte": "Testé sur Firefox aussi."},
     reponseJSON(EXEMPLE_BROUILLON, 201), EXEMPLE_BROUILLON),
    ("ajouterModification (texte)",
     lambda c: c.ajouterTexte(1, "La carte est refusée sans message d'erreur."),
     "POST", "/acteur/2/brouillon/1/modifications",
     {"type": "texte", "texte": "La carte est refusée sans message d'erreur."},
     reponseJSON(EXEMPLE_BROUILLON, 201), EXEMPLE_BROUILLON),
    ("ajouterModification (image)", lambda c: c.ajouterImage(1, "capture.png", OCTETS_PNG),
     "POST", "/acteur/2/brouillon/1/modifications",
     {"type": "image", "nomFichier": "capture.png",
      "contenuBase64": base64.b64encode(OCTETS_PNG).decode("ascii")},
     reponseJSON(EXEMPLE_BROUILLON, 201), EXEMPLE_BROUILLON),
    ("annulerDerniereModification", lambda c: c.annulerDerniereModification(1), "DELETE",
     "/acteur/2/brouillon/1/modification/derniere", None,
     reponseJSON(RESULTAT_ANNULATION), RESULTAT_ANNULATION),
    ("appliquerBrouillon", lambda c: c.appliquerBrouillon(1), "POST",
     "/acteur/2/brouillon/1/application", {},
     reponseJSON(EXEMPLE_RAPPORT_CREATION, 201), EXEMPLE_RAPPORT_CREATION),
    ("appliquerBrouillon (texte)",
     lambda c: c.appliquerBrouillon(1, texte="La carte est refusée sans message d'erreur."),
     "POST", "/acteur/2/brouillon/1/application",
     {"texte": "La carte est refusée sans message d'erreur."},
     reponseJSON(EXEMPLE_RAPPORT_CREATION, 201), EXEMPLE_RAPPORT_CREATION),
    ("appliquerLot (assigner)", lambda c: c.appliquerLot("assigner", [6, 7, 3], assigneId=4),
     "POST", "/acteur/2/lots", {"action": "assigner", "ticketIds": [6, 7, 3], "assigneId": 4},
     reponseJSON(EXEMPLE_RAPPORT_LOT), EXEMPLE_RAPPORT_LOT),
    ("appliquerLot (fermer)", lambda c: c.appliquerLot("fermer", [6]),
     "POST", "/acteur/2/lots", {"action": "fermer", "ticketIds": [6]},
     reponseJSON(EXEMPLE_RAPPORT_LOT), EXEMPLE_RAPPORT_LOT),
    ("lireVersion", lambda c: c.lireVersion(), "GET", "/version", None,
     reponseJSON({"version": 42}), 42),
]


class TestOperations(unittest.TestCase):
    """Chaque opération suit openapi.yaml : méthode, chemin et corps, et rend le JSON reçu."""

    def test_chaqueOperation(self) -> None:
        for nom, appel, methode, chemin, corps, reponse, attendu in CAS_OPERATIONS:
            with self.subTest(operation=nom):
                client, transport = clientEssai(reponse, acteurId=2)
                self.assertEqual(appel(client), attendu)
                requete = transport.derniere
                self.assertEqual((requete.methode, requete.url), (methode, URL + chemin))
                self.assertEqual(requete.corpsJSON, corps)
                self.assertEqual(requete.entetes.get(EN_TETE_ACTEUR), "2")

    def test_toutesLesOperationsDuContratSontCouvertes(self) -> None:
        """Une operationId ajoutée à openapi.yaml sans méthode ni cas ici fait échouer ce test."""
        texte = (racineDepot / "openapi.yaml").read_text(encoding="utf-8")
        contrat = set(re.findall(r"operationId:\s*(\w+)", texte))
        couvertes = {nom.split()[0] for nom, *_ in CAS_OPERATIONS}
        self.assertEqual(couvertes, contrat)

    def test_lireVersionInvalide(self) -> None:
        for donnees in ({}, {"version": "42"}, [42], {"version": True}):
            with self.subTest(donnees=donnees):
                client, _ = clientEssai(reponseJSON(donnees))
                with self.assertRaises(ReponseInvalide):
                    client.lireVersion()

    def test_modifierBrouillonSansChamp(self) -> None:
        client, transport = clientEssai()
        with self.assertRaises(ValueError):
            client.modifierBrouillon(1)
        self.assertEqual(transport.requetes, [])

    def test_operationsDActeurSansActeur(self) -> None:
        """Brouillons et lots sont rangés sous /acteur/{acteurId} : rien n'est envoyé sans acteur."""
        appels: dict[str, Callable[[ClientAPI], Any]] = {
            "listerBrouillons": lambda c: c.listerBrouillons(),
            "ouvrirBrouillonEdition": lambda c: c.ouvrirBrouillonEdition(6),
            "appliquerLot": lambda c: c.appliquerLot("fermer", [6]),
        }
        for nom, appel in appels.items():
            with self.subTest(operation=nom):
                client, transport = clientEssai(acteurId=None)
                with self.assertRaises(ValueError):
                    appel(client)
                self.assertEqual(transport.requetes, [])


# ------------------------------------------------------------------ vrai transport (urllib)

DUREE_LENTE = 0.6


class _ServeurEssai(ThreadingHTTPServer):
    """Mini serveur HTTP local ; ses erreurs (client parti avant la réponse) sont tues."""

    def handle_error(self, request: Any, client_address: Any) -> None:
        pass


class _GestionnaireEssai(BaseHTTPRequestHandler):
    """Renvoie en JSON ce qu'il a reçu ; /conflit, /vide et /lent simulent les autres cas."""

    def do_GET(self) -> None:
        self._repondre()

    do_POST = do_GET
    do_PATCH = do_GET
    do_DELETE = do_GET

    def _repondre(self) -> None:
        longueur = int(self.headers.get("Content-Length") or 0)
        corps = self.rfile.read(longueur).decode("utf-8")
        if self.path == "/lent":
            time.sleep(DUREE_LENTE)
        if self.path == "/vide":
            self.send_response(204)
            self.end_headers()
            return
        if self.path == "/conflit":
            self._envoyerJSON(409, {"erreur": {
                "type": "TransitionInvalideException", "message": MESSAGE_TRANSITION,
            }})
            return
        self._envoyerJSON(200, {
            "methode": self.command,
            "chemin": self.path,
            "acteur": self.headers.get(EN_TETE_ACTEUR),
            "typeContenu": self.headers.get("Content-Type"),
            "corps": corps,
        })

    def _envoyerJSON(self, code: int, donnees: object) -> None:
        octets = json.dumps(donnees, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(octets)))
        self.end_headers()
        self.wfile.write(octets)

    def log_message(self, *args: Any) -> None:
        """Pas de journal dans la sortie des tests."""


class TestTransportUrllib(unittest.TestCase):
    """Le vrai transport contre un mini serveur local : ni Flask, ni réseau extérieur."""

    serveur: _ServeurEssai
    url: str

    @classmethod
    def setUpClass(cls) -> None:
        cls.serveur = _ServeurEssai(("127.0.0.1", 0), _GestionnaireEssai)
        threading.Thread(target=cls.serveur.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.serveur.server_address[1]}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.serveur.shutdown()
        cls.serveur.server_close()

    def test_envoiEtLectureJSON(self) -> None:
        reponse = ClientAPI(self.url, 7).post("/echo", {"titre": "Paiement refusé"})
        self.assertEqual(reponse["methode"], "POST")
        self.assertEqual(reponse["acteur"], "7")
        self.assertEqual(reponse["typeContenu"], "application/json")
        self.assertEqual(json.loads(reponse["corps"]), {"titre": "Paiement refusé"})

    def test_parametresEtPatch(self) -> None:
        client = ClientAPI(self.url, 7)
        self.assertEqual(client.get("/tickets", {"statut": Statut.FERME})["chemin"],
                         "/tickets?statut=FERME")
        self.assertEqual(client.patch("/ticket/3", {"statut": "FERME"})["methode"], "PATCH")

    def test_erreurHTTPReconstruite(self) -> None:
        with self.assertRaises(TransitionInvalideException) as contexte:
            ClientAPI(self.url, 7).get("/conflit")
        self.assertEqual(str(contexte.exception), MESSAGE_TRANSITION)

    def test_reponse204(self) -> None:
        self.assertIsNone(ClientAPI(self.url, 7).delete("/vide"))

    def test_delaiDepasse(self) -> None:
        with self.assertRaises(ServeurInjoignable) as contexte:
            ClientAPI(self.url, 7, delai=0.2).get("/lent")
        self.assertIn("0.2 s", str(contexte.exception))

    def test_serveurArrete(self) -> None:
        with socket.socket() as sonde:
            sonde.bind(("127.0.0.1", 0))
            port = sonde.getsockname()[1]
        # Le port vient d'être libéré : personne n'y écoute.
        with self.assertRaises(ServeurInjoignable):
            ClientAPI(f"http://127.0.0.1:{port}", delai=1.0).lireVersion()


if __name__ == "__main__":
    unittest.main()
