"""Tests de S4 : brouillons de création et d'édition, opération par opération, puis en parcours.

Lancer depuis la racine du dépôt :  python -m unittest discover -s tests -t . -v
"""
from __future__ import annotations

import base64
import io
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from typing import Any
from unittest import mock

from api import creerApplication
from api.contexte import ContexteServeur
from api.routes_brouillons import TAILLE_MAXIMALE_IMAGE
from modele.enums import Statut
from tests.test_api_tickets import ABDOUL, ADMIN, IMAGE_SOURCE, JULIEN, MIKE, TestEcriture

IMAGE = IMAGE_SOURCE.read_bytes()
CHAMPS_BROUILLON = {
    "id", "type", "libelle", "ticket", "proprietaire", "ouverte", "enPause",
    "modificationsEnAttente", "nombreImages", "texteBrouillon",
}


def corpsImage(nomFichier: str = "capture.png", octets: bytes = IMAGE) -> dict[str, str]:
    contenu = base64.b64encode(octets).decode("ascii")
    return {"type": "image", "nomFichier": nomFichier, "contenuBase64": contenu}


class TestBrouillons(TestEcriture):
    """T Julien (3) a créé les tickets 3, 6 et 9 de la démonstration, dont le 6 jamais assigné."""

    def chemin(self, brouillonId: int, suite: str = "", acteurId: int = JULIEN) -> str:
        return f"/acteur/{acteurId}/brouillon/{brouillonId}{suite}"

    def ouvrir(self, acteurId: int = JULIEN, **corps: Any):
        return self.requete("POST", f"/acteur/{acteurId}/brouillons", acteurId, corps)

    def ouvrirCreation(self, acteurId: int = JULIEN) -> int:
        reponse = self.ouvrir(acteurId, type="creation", titre="Paiement", priorite="HAUTE")
        self.assertEqual(reponse.status_code, 201, reponse.get_data(as_text=True))
        return reponse.get_json()["id"]

    def ouvrirEdition(self, ticketId: int = 6, acteurId: int = JULIEN) -> int:
        reponse = self.ouvrir(acteurId, type="edition", ticketId=ticketId)
        self.assertEqual(reponse.status_code, 201, reponse.get_data(as_text=True))
        return reponse.get_json()["id"]

    def lire(self, brouillonId: int, acteurId: int = JULIEN) -> dict[str, Any]:
        return self.requete("GET", self.chemin(brouillonId, acteurId=acteurId), acteurId).get_json()

    def ajouter(self, brouillonId: int, acteurId: int = JULIEN, **corps: Any):
        chemin = self.chemin(brouillonId, "/modifications", acteurId)
        return self.requete("POST", chemin, acteurId, corps)

    def commenter(self, brouillonId: int, texte: str = "Un commentaire") -> None:
        reponse = self.ajouter(brouillonId, type="commentaire", texte=texte)
        self.assertEqual(reponse.status_code, 201, reponse.get_data(as_text=True))

    def mettreEnPause(self, brouillonId: int) -> None:
        reponse = self.requete("PATCH", self.chemin(brouillonId), JULIEN, {"enPause": True})
        self.assertEqual(reponse.status_code, 200, reponse.get_data(as_text=True))

    def annuler(self, brouillonId: int):
        return self.requete("DELETE", self.chemin(brouillonId, "/modification/derniere"), JULIEN)

    def abandonner(self, brouillonId: int, acteurId: int = JULIEN):
        return self.requete("DELETE", self.chemin(brouillonId, acteurId=acteurId), acteurId)

    def appliquer(self, brouillonId: int, corps: dict[str, Any] | None = None):
        return self.requete("POST", self.chemin(brouillonId, "/application"), JULIEN, corps)

    def fichiers(self) -> list[Path]:
        return sorted(self.images.iterdir()) if self.images.exists() else []


class TestOuvrir(TestBrouillons):
    def test_creation(self) -> None:
        """L'exemple BrouillonCreation de openapi.yaml, et le ticket reste hors du dépôt."""
        version = self.contexte.version
        reponse = self.ouvrir(type="creation", titre="Paiement refusé", priorite="MOYENNE")
        self.assertEqual(reponse.status_code, 201)
        self.assertEqual(reponse.headers["Location"], "/acteur/3/brouillon/1")
        self.assertEqual(
            reponse.get_json(),
            {
                "id": 1,
                "type": "creation",
                "libelle": "Session de création",
                "ticket": {"id": 11, "titre": "Paiement refusé", "priorite": "MOYENNE"},
                "proprietaire": {"id": 3, "nom": "T Julien"},
                "ouverte": True,
                "enPause": False,
                "modificationsEnAttente": [],
                "nombreImages": 0,
                "texteBrouillon": "",
            },
        )
        self.verifierErreur(self.requete("GET", "/ticket/11", ADMIN), 404, "RessourceIntrouvable")
        self.verifierRienEcrit(version)

    def test_edition(self) -> None:
        version = self.contexte.version
        reponse = self.ouvrir(type="edition", ticketId=6)
        self.assertEqual(reponse.status_code, 201)
        brouillon = reponse.get_json()
        self.assertEqual(set(brouillon), CHAMPS_BROUILLON)
        self.assertEqual(brouillon["type"], "edition")
        self.assertEqual(brouillon["libelle"], "Session d'édition")
        self.assertEqual(brouillon["ticket"]["id"], 6)
        self.verifierRienEcrit(version)

    def test_titre_sans_espaces_de_bord(self) -> None:
        reponse = self.ouvrir(type="creation", titre="  Bug  ", priorite="BASSE")
        self.assertEqual(reponse.get_json()["ticket"]["titre"], "Bug")

    def test_identifiant_reserve_distinct_de_post_tickets(self) -> None:
        brouillon = self.ouvrir(type="creation", titre="A", priorite="BASSE").get_json()
        corps = {"titre": "B", "priorite": "BASSE", "texte": "x"}
        ticket = self.requete("POST", "/tickets", JULIEN, corps).get_json()["ticket"]
        self.assertEqual(brouillon["ticket"]["id"], 11)
        self.assertEqual(ticket["id"], 12)

    def test_format_du_corps(self) -> None:
        for corps in (
            {},
            {"type": "autre"},
            {"type": "creation"},
            {"type": "creation", "titre": "x"},
            {"type": "creation", "priorite": "BASSE"},
            {"type": "creation", "titre": "  ", "priorite": "BASSE"},
            {"type": "creation", "titre": "x", "priorite": "haute"},
            {"type": "creation", "titre": "x", "priorite": "BASSE", "ticketId": 6},
            {"type": "edition"},
            {"type": "edition", "ticketId": "6"},
            {"type": "edition", "ticketId": 6, "titre": "x"},
        ):
            with self.subTest(corps=corps):
                self.verifierErreur(self.ouvrir(**corps), 400, "RequeteInvalide")
        # Aucun refus n'a consommé d'identifiant de ticket ni de brouillon.
        reponse = self.ouvrir(type="creation", titre="x", priorite="BASSE").get_json()
        self.assertEqual((reponse["id"], reponse["ticket"]["id"]), (1, 11))

    def test_ticket_inconnu(self) -> None:
        self.verifierErreur(self.ouvrir(type="edition", ticketId=999), 404, "RessourceIntrouvable")

    def test_edition_par_un_autre_que_le_createur(self) -> None:
        reponse = self.ouvrir(ABDOUL, type="edition", ticketId=6)
        self.verifierErreur(reponse, 403, "AccesRefuseException")

    def test_deuxieme_session_sur_le_meme_ticket(self) -> None:
        self.ouvrirEdition(6)
        reponse = self.ouvrir(type="edition", ticketId=6)
        self.verifierErreur(reponse, 409, "SessionIndisponibleException")
        self.assertEqual(len(self.requete("GET", "/acteur/3/brouillons", JULIEN).get_json()), 1)

    def test_edition_possible_apres_abandon_et_application(self) -> None:
        self.abandonner(self.ouvrirEdition(6))
        self.assertEqual(self.appliquer(self.ouvrirEdition(6)).status_code, 200)
        self.ouvrirEdition(6)


class TestReglesAcces(TestBrouillons):
    def operations(self, acteurId: int, brouillonId: int = 1) -> list[tuple[str, str]]:
        base = f"/acteur/{acteurId}/brouillon/{brouillonId}"
        return [
            ("GET", f"/acteur/{acteurId}/brouillons"),
            ("POST", f"/acteur/{acteurId}/brouillons"),
            ("GET", base),
            ("PATCH", base),
            ("DELETE", base),
            ("GET", f"{base}/modifications"),
            ("POST", f"{base}/modifications"),
            ("DELETE", f"{base}/modification/derniere"),
            ("POST", f"{base}/application"),
        ]

    def test_acteur_non_identifie(self) -> None:
        for methode, chemin in self.operations(JULIEN):
            for acteur in (None, 99):
                with self.subTest(methode=methode, chemin=chemin, acteur=acteur):
                    reponse = self.requete(methode, chemin, acteur)
                    self.verifierErreur(reponse, 401, "ActeurNonIdentifie")

    def test_admin_refuse(self) -> None:
        for methode, chemin in self.operations(ADMIN):
            with self.subTest(methode=methode, chemin=chemin):
                reponse = self.requete(methode, chemin, ADMIN)
                self.verifierErreur(reponse, 403, "AccesRefuseException")

    def test_acteur_du_chemin_different(self) -> None:
        brouillonId = self.ouvrirCreation()
        for methode, chemin in self.operations(JULIEN, brouillonId):
            with self.subTest(methode=methode, chemin=chemin):
                reponse = self.requete(methode, chemin, MIKE, {})
                self.verifierErreur(reponse, 403, "AccesRefuseException")
        self.assertTrue(self.lire(brouillonId)["ouverte"])

    def test_brouillon_d_un_autre_user_introuvable(self) -> None:
        """Sur son propre chemin, Mike reçoit 404 : le brouillon de Julien n'existe pas pour lui."""
        brouillonId = self.ouvrirCreation()
        self.commenter(brouillonId)
        for methode, chemin, corps in (
            ("GET", self.chemin(brouillonId, acteurId=MIKE), None),
            ("PATCH", self.chemin(brouillonId, acteurId=MIKE), {"enPause": True}),
            ("DELETE", self.chemin(brouillonId, acteurId=MIKE), None),
            ("GET", self.chemin(brouillonId, "/modifications", MIKE), None),
            ("POST", self.chemin(brouillonId, "/modifications", MIKE),
             {"type": "commentaire", "texte": "x"}),
            ("DELETE", self.chemin(brouillonId, "/modification/derniere", MIKE), None),
            ("POST", self.chemin(brouillonId, "/application", MIKE), None),
        ):
            with self.subTest(methode=methode, chemin=chemin):
                reponse = self.requete(methode, chemin, MIKE, corps)
                self.verifierErreur(reponse, 404, "RessourceIntrouvable")
        brouillon = self.lire(brouillonId)
        self.assertFalse(brouillon["enPause"])
        self.assertEqual(len(brouillon["modificationsEnAttente"]), 1)

    def test_brouillon_inconnu(self) -> None:
        for methode, chemin in self.operations(JULIEN, 99):
            if chemin.endswith("/brouillons"):
                continue
            corps = None
            if methode == "PATCH":
                corps = {"enPause": True}
            elif chemin.endswith("/modifications") and methode == "POST":
                corps = {"type": "commentaire", "texte": "x"}
            with self.subTest(methode=methode, chemin=chemin):
                reponse = self.requete(methode, chemin, JULIEN, corps)
                self.verifierErreur(reponse, 404, "RessourceIntrouvable")

    def test_ordre_des_controles(self) -> None:
        """401, le chemin, le rôle (403), le format (400), 404, puis le métier."""
        chemin = self.chemin(99, "/modifications")
        duAdmin = self.chemin(99, "/modifications", ADMIN)
        invalide: dict[str, Any] = {"type": "autre"}
        valide = {"type": "commentaire", "texte": "x"}
        for acteur, cible, corps, code, typeErreur in (
            (None, chemin, invalide, 401, "ActeurNonIdentifie"),
            (MIKE, chemin, invalide, 403, "AccesRefuseException"),
            (ADMIN, duAdmin, invalide, 403, "AccesRefuseException"),
            (JULIEN, chemin, invalide, 400, "RequeteInvalide"),
            (JULIEN, chemin, valide, 404, "RessourceIntrouvable"),
        ):
            with self.subTest(acteur=acteur, code=code):
                self.verifierErreur(self.requete("POST", cible, acteur, corps), code, typeErreur)

    def test_methode_absente(self) -> None:
        for methode, chemin in (
            ("PUT", "/acteur/3/brouillons"),
            ("POST", "/acteur/3/brouillon/1"),
            ("GET", "/acteur/3/brouillon/1/application"),
            ("GET", "/acteur/3/brouillon/1/modification/derniere"),
        ):
            with self.subTest(methode=methode, chemin=chemin):
                reponse = self.requete(methode, chemin, JULIEN)
                self.verifierErreur(reponse, 405, "MethodeNonPermise")


class TestLire(TestBrouillons):
    def test_lister_ouverts_de_l_acteur(self) -> None:
        creation = self.ouvrirCreation()
        self.ouvrirCreation(MIKE)
        edition = self.ouvrirEdition(6)
        self.mettreEnPause(edition)
        brouillons = self.requete("GET", "/acteur/3/brouillons", JULIEN).get_json()
        self.assertEqual([b["id"] for b in brouillons], [creation, edition])
        self.assertEqual([b["type"] for b in brouillons], ["creation", "edition"])
        self.assertEqual([b["enPause"] for b in brouillons], [False, True])

    def test_aucun_brouillon(self) -> None:
        self.assertEqual(self.requete("GET", "/acteur/3/brouillons", JULIEN).get_json(), [])

    def test_lire_un_brouillon(self) -> None:
        brouillonId = self.ouvrirCreation()
        reponse = self.requete("GET", self.chemin(brouillonId), JULIEN)
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(set(reponse.get_json()), CHAMPS_BROUILLON)

    def test_modifications_dans_l_ordre_d_ajout(self) -> None:
        brouillonId = self.ouvrirCreation()
        self.ajouter(brouillonId, type="commentaire", texte="Testé sur Firefox")
        self.ajouter(brouillonId, **corpsImage())
        modifications = self.requete(
            "GET", self.chemin(brouillonId, "/modifications"), JULIEN
        ).get_json()
        self.assertEqual(len(modifications), 2)
        self.assertIn("Testé sur Firefox", modifications[0])
        self.assertIn("[Image]", modifications[1])
        self.assertIn("_capture.png", modifications[1])


class TestModifierBrouillon(TestBrouillons):
    def modifier(self, brouillonId: int, **corps: Any):
        return self.requete("PATCH", self.chemin(brouillonId), JULIEN, corps)

    def test_pause_et_texte(self) -> None:
        brouillonId = self.ouvrirCreation()
        reponse = self.modifier(brouillonId, enPause=True, texteBrouillon="Le paiement échoue")
        self.assertEqual(reponse.status_code, 200)
        brouillon = reponse.get_json()
        self.assertTrue(brouillon["enPause"])
        self.assertEqual(brouillon["texteBrouillon"], "Le paiement échoue")
        self.assertEqual(brouillon["modificationsEnAttente"], [])

    def test_reprise_garde_le_texte(self) -> None:
        brouillonId = self.ouvrirCreation()
        self.modifier(brouillonId, enPause=True, texteBrouillon="Gardé")
        brouillon = self.modifier(brouillonId, enPause=False).get_json()
        self.assertFalse(brouillon["enPause"])
        self.assertEqual(brouillon["texteBrouillon"], "Gardé")

    def test_texte_seul(self) -> None:
        brouillonId = self.ouvrirCreation()
        brouillon = self.modifier(brouillonId, texteBrouillon="Brouillon").get_json()
        self.assertEqual(brouillon["texteBrouillon"], "Brouillon")
        self.assertFalse(brouillon["enPause"])
        brouillon = self.modifier(brouillonId, texteBrouillon="").get_json()
        self.assertEqual(brouillon["texteBrouillon"], "")

    def test_etat_deja_en_vigueur_refuse_par_le_modele(self) -> None:
        brouillonId = self.ouvrirCreation()
        reponse = self.modifier(brouillonId, enPause=False)
        self.verifierErreur(reponse, 409, "SessionIndisponibleException")
        self.mettreEnPause(brouillonId)
        reponse = self.modifier(brouillonId, enPause=True)
        self.verifierErreur(reponse, 409, "SessionIndisponibleException")

    def test_texte_garde_meme_si_la_pause_est_refusee(self) -> None:
        """Le contrat enregistre le texte d'abord, comme ControleurEdition.mettreEnPause()."""
        brouillonId = self.ouvrirCreation()
        self.mettreEnPause(brouillonId)
        reponse = self.modifier(brouillonId, enPause=True, texteBrouillon="Changé")
        self.verifierErreur(reponse, 409, "SessionIndisponibleException")
        self.assertEqual(self.lire(brouillonId)["texteBrouillon"], "Changé")

    def test_format_du_corps(self) -> None:
        brouillonId = self.ouvrirCreation()
        for corps in (
            {},
            {"enPause": "oui"},
            {"enPause": 1},
            {"texteBrouillon": 5},
            {"enPause": True, "autre": 1},
        ):
            with self.subTest(corps=corps):
                reponse = self.requete("PATCH", self.chemin(brouillonId), JULIEN, corps)
                self.verifierErreur(reponse, 400, "RequeteInvalide")
        self.assertFalse(self.lire(brouillonId)["enPause"])

    def test_ne_touche_pas_au_depot(self) -> None:
        version = self.contexte.version
        brouillonId = self.ouvrirEdition(6)
        self.modifier(brouillonId, enPause=True, texteBrouillon="x")
        self.modifier(brouillonId, enPause=False)
        self.verifierRienEcrit(version)


class TestAjouterTexte(TestBrouillons):
    def test_commentaire(self) -> None:
        brouillonId = self.ouvrirEdition(6)
        version = self.contexte.version
        reponse = self.ajouter(brouillonId, type="commentaire", texte="  Testé  ")
        self.assertEqual(reponse.status_code, 201)
        brouillon = reponse.get_json()
        self.assertEqual(set(brouillon), CHAMPS_BROUILLON)
        self.assertEqual(
            brouillon["modificationsEnAttente"], ["Ajouter le commentaire « Testé » au ticket #6"]
        )
        self.assertEqual(brouillon["nombreImages"], 0)
        # Rien ne change dans le dépôt avant l'application.
        self.assertEqual(self.ticket(6).comments, [])
        self.verifierRienEcrit(version)

    def test_texte_saisi(self) -> None:
        brouillonId = self.ouvrirEdition(6)
        brouillon = self.ajouter(brouillonId, type="texte", texte="  La carte  ").get_json()
        self.assertEqual(len(brouillon["modificationsEnAttente"]), 1)
        self.assertIn("texte saisi (8 caractères)", brouillon["modificationsEnAttente"][0])

    def test_texte_vide_refuse_par_le_modele(self) -> None:
        brouillonId = self.ouvrirCreation()
        for texte in ("", "   "):
            with self.subTest(texte=texte):
                reponse = self.ajouter(brouillonId, type="texte", texte=texte)
                self.verifierErreur(reponse, 400, "ArtefactInvalideException")
        self.assertEqual(self.lire(brouillonId)["modificationsEnAttente"], [])

    def test_commentaire_vide_refuse_comme_erreur_de_format(self) -> None:
        """Aucune règle dans le modèle pour ce cas : seule la GUI le bloquait."""
        brouillonId = self.ouvrirCreation()
        for texte in ("", "   "):
            with self.subTest(texte=texte):
                reponse = self.ajouter(brouillonId, type="commentaire", texte=texte)
                self.verifierErreur(reponse, 400, "RequeteInvalide")
        self.assertEqual(self.lire(brouillonId)["modificationsEnAttente"], [])

    def test_format_du_corps(self) -> None:
        brouillonId = self.ouvrirCreation()
        for corps in (
            {},
            {"type": "autre", "texte": "x"},
            {"type": "commentaire"},
            {"type": "texte"},
            {"type": "commentaire", "texte": 5},
            {"type": "texte", "texte": None},
            {"type": "commentaire", "texte": "x", "nomFichier": "a.png"},
        ):
            with self.subTest(corps=corps):
                self.verifierErreur(self.ajouter(brouillonId, **corps), 400, "RequeteInvalide")

    def test_refus_en_pause(self) -> None:
        brouillonId = self.ouvrirCreation()
        self.mettreEnPause(brouillonId)
        for corps in ({"type": "commentaire", "texte": "x"}, {"type": "texte", "texte": "x"}):
            with self.subTest(corps=corps):
                reponse = self.ajouter(brouillonId, **corps)
                self.verifierErreur(reponse, 409, "SessionIndisponibleException")
        self.assertEqual(self.lire(brouillonId)["modificationsEnAttente"], [])


class TestAjouterImage(TestBrouillons):
    def test_image(self) -> None:
        brouillonId = self.ouvrirCreation()
        reponse = self.ajouter(brouillonId, **corpsImage())
        self.assertEqual(reponse.status_code, 201, reponse.get_data(as_text=True))
        self.assertEqual(reponse.get_json()["nombreImages"], 1)
        fichiers = self.fichiers()
        self.assertEqual(len(fichiers), 1)
        self.assertRegex(fichiers[0].name, r"^[0-9a-f]{8}_capture\.png$")
        self.assertEqual(fichiers[0].read_bytes(), IMAGE)

    def test_chemin_disque_jamais_expose(self) -> None:
        brouillonId = self.ouvrirCreation()
        texte = self.ajouter(brouillonId, **corpsImage()).get_data(as_text=True)
        self.assertNotIn(self.images.name, texte)
        self.assertNotIn("donnees", texte)

    def test_autre_format_sans_copie(self) -> None:
        brouillonId = self.ouvrirCreation()
        for nom in ("photo.jpg", "page.html", "sans_extension", ""):
            with self.subTest(nom=nom):
                reponse = self.ajouter(brouillonId, **corpsImage(nom))
                self.verifierErreur(reponse, 400, "ArtefactInvalideException")
        self.assertEqual(self.fichiers(), [])
        self.assertEqual(self.lire(brouillonId)["nombreImages"], 0)

    def test_base64_invalide_sans_copie(self) -> None:
        brouillonId = self.ouvrirCreation()
        for contenu in ("pas du base64 !", "aGVsbG8", "é", "aGVsbG8=\n", "", "   "):
            with self.subTest(contenu=contenu):
                reponse = self.ajouter(
                    brouillonId, type="image", nomFichier="a.png", contenuBase64=contenu
                )
                self.verifierErreur(reponse, 400, "RequeteInvalide")
        self.assertEqual(self.fichiers(), [])

    def test_format_du_corps(self) -> None:
        brouillonId = self.ouvrirCreation()
        complet = corpsImage()
        for corps in (
            {"type": "image"},
            {"type": "image", "nomFichier": "a.png"},
            {"type": "image", "contenuBase64": complet["contenuBase64"]},
            {**complet, "nomFichier": 5},
            {**complet, "contenuBase64": 5},
            {**complet, "texte": "x"},
        ):
            with self.subTest(corps=sorted(corps)):
                self.verifierErreur(self.ajouter(brouillonId, **corps), 400, "RequeteInvalide")
        self.assertEqual(self.fichiers(), [])

    def test_exactement_5_mo_accepte(self) -> None:
        brouillonId = self.ouvrirCreation()
        reponse = self.ajouter(brouillonId, **corpsImage(octets=b"x" * TAILLE_MAXIMALE_IMAGE))
        self.assertEqual(reponse.status_code, 201, reponse.get_data(as_text=True))
        self.assertEqual(self.fichiers()[0].stat().st_size, TAILLE_MAXIMALE_IMAGE)

    def test_au_dela_de_5_mo_refuse(self) -> None:
        brouillonId = self.ouvrirCreation()
        reponse = self.ajouter(brouillonId, **corpsImage(octets=b"x" * (TAILLE_MAXIMALE_IMAGE + 1)))
        self.verifierErreur(reponse, 413, "RequeteTropVolumineuse")
        self.assertEqual(
            reponse.get_json()["erreur"]["message"], "Image trop volumineuse (5 Mo au plus)"
        )
        self.assertEqual(self.fichiers(), [])

    def test_corps_au_dela_de_8_mo_refuse(self) -> None:
        brouillonId = self.ouvrirCreation()
        reponse = self.ajouter(brouillonId, **corpsImage(octets=b"x" * (7 * 1024 * 1024)))
        self.verifierErreur(reponse, 413, "RequeteTropVolumineuse")
        self.assertEqual(self.fichiers(), [])

    def test_en_pause_aucune_copie_ne_reste(self) -> None:
        brouillonId = self.ouvrirCreation()
        self.mettreEnPause(brouillonId)
        reponse = self.ajouter(brouillonId, **corpsImage())
        self.verifierErreur(reponse, 409, "SessionIndisponibleException")
        self.assertEqual(self.fichiers(), [])
        self.assertEqual(self.lire(brouillonId)["nombreImages"], 0)

    def test_brouillon_inconnu_aucune_copie(self) -> None:
        self.verifierErreur(self.ajouter(99, **corpsImage()), 404, "RessourceIntrouvable")
        self.assertEqual(self.fichiers(), [])

    def test_nom_dangereux_reste_dans_le_dossier(self) -> None:
        brouillonId = self.ouvrirCreation()
        for nom in ("../../evasion.png", "..\\..\\evasion.png", "C:evasion.png"):
            with self.subTest(nom=nom):
                reponse = self.ajouter(brouillonId, **corpsImage(nom))
                self.assertEqual(reponse.status_code, 201, reponse.get_data(as_text=True))
        self.assertEqual(len(self.fichiers()), 3)
        self.assertEqual(sorted(p.name for p in self.dossier.iterdir()), ["images"])


class TestAnnuler(TestBrouillons):
    def test_commentaire(self) -> None:
        brouillonId = self.ouvrirCreation()
        self.commenter(brouillonId, "Premier")
        self.commenter(brouillonId, "Second")
        reponse = self.annuler(brouillonId)
        self.assertEqual(reponse.status_code, 200)
        resultat = reponse.get_json()
        self.assertEqual(set(resultat), {"libelleRetire", "brouillon"})
        self.assertIn("Second", resultat["libelleRetire"])
        self.assertEqual(len(resultat["brouillon"]["modificationsEnAttente"]), 1)
        self.assertIn("Premier", resultat["brouillon"]["modificationsEnAttente"][0])

    def test_image_supprime_sa_copie(self) -> None:
        brouillonId = self.ouvrirCreation()
        self.ajouter(brouillonId, **corpsImage("a.png"))
        premiere = self.fichiers()[0]
        self.ajouter(brouillonId, **corpsImage("b.png"))
        self.assertEqual(self.annuler(brouillonId).get_json()["brouillon"]["nombreImages"], 1)
        self.assertEqual(self.fichiers(), [premiere])

    def test_pile_alignee_entre_images_et_commentaires(self) -> None:
        """Image, commentaire, image : chaque undo retire la bonne copie, ou aucune."""
        brouillonId = self.ouvrirCreation()
        self.ajouter(brouillonId, **corpsImage("a.png"))
        self.commenter(brouillonId)
        self.ajouter(brouillonId, **corpsImage("b.png"))
        nombres = []
        for _ in range(3):
            self.assertEqual(self.annuler(brouillonId).status_code, 200)
            nombres.append(len(self.fichiers()))
        self.assertEqual(nombres, [1, 1, 0])

    def test_rien_a_annuler(self) -> None:
        brouillonId = self.ouvrirCreation()
        self.verifierErreur(self.annuler(brouillonId), 409, "SessionIndisponibleException")

    def test_refus_en_pause_garde_la_copie(self) -> None:
        brouillonId = self.ouvrirCreation()
        self.ajouter(brouillonId, **corpsImage())
        self.mettreEnPause(brouillonId)
        self.verifierErreur(self.annuler(brouillonId), 409, "SessionIndisponibleException")
        self.assertEqual(len(self.fichiers()), 1)
        self.assertEqual(self.lire(brouillonId)["nombreImages"], 1)

    def test_copie_qui_resiste_signalee_sans_echec(self) -> None:
        brouillonId = self.ouvrirCreation()
        self.ajouter(brouillonId, **corpsImage())
        console = io.StringIO()
        with (
            mock.patch.object(
                self.contexte.stockage, "supprimer", side_effect=PermissionError("tenu")
            ),
            redirect_stderr(console),
        ):
            reponse = self.annuler(brouillonId)
        self.assertEqual(reponse.status_code, 200)
        self.assertIn("Copie d'image non supprimée", console.getvalue())


class TestAbandonner(TestBrouillons):
    def test_creation(self) -> None:
        brouillonId = self.ouvrirCreation()
        version = self.contexte.version
        reponse = self.abandonner(brouillonId)
        self.assertEqual(reponse.status_code, 204)
        self.assertEqual(reponse.get_data(), b"")
        relu = self.requete("GET", self.chemin(brouillonId), JULIEN)
        self.verifierErreur(relu, 404, "RessourceIntrouvable")
        self.verifierErreur(self.requete("GET", "/ticket/11", ADMIN), 404, "RessourceIntrouvable")
        self.verifierRienEcrit(version)

    def test_edition_laisse_le_ticket_inchange(self) -> None:
        brouillonId = self.ouvrirEdition(6)
        self.commenter(brouillonId)
        version = self.contexte.version
        self.assertEqual(self.abandonner(brouillonId).status_code, 204)
        self.assertEqual(self.ticket(6).comments, [])
        self.verifierRienEcrit(version)

    def test_copies_supprimees(self) -> None:
        brouillonId = self.ouvrirCreation()
        self.ajouter(brouillonId, **corpsImage("a.png"))
        self.commenter(brouillonId)
        self.ajouter(brouillonId, **corpsImage("b.png"))
        self.assertEqual(len(self.fichiers()), 2)
        self.abandonner(brouillonId)
        self.assertEqual(self.fichiers(), [])

    def test_permis_en_pause(self) -> None:
        brouillonId = self.ouvrirCreation()
        self.ajouter(brouillonId, **corpsImage())
        self.mettreEnPause(brouillonId)
        self.assertEqual(self.abandonner(brouillonId).status_code, 204)
        self.assertEqual(self.fichiers(), [])

    def test_deux_fois_donne_404(self) -> None:
        brouillonId = self.ouvrirCreation()
        self.abandonner(brouillonId)
        self.verifierErreur(self.abandonner(brouillonId), 404, "RessourceIntrouvable")

    def test_ne_touche_pas_aux_copies_d_un_autre_brouillon(self) -> None:
        premier, second = self.ouvrirCreation(), self.ouvrirCreation()
        self.ajouter(premier, **corpsImage())
        self.ajouter(second, **corpsImage())
        self.abandonner(premier)
        self.assertEqual(len(self.fichiers()), 1)
        self.assertEqual(self.lire(second)["nombreImages"], 1)


class TestAppliquer(TestBrouillons):
    def test_creation(self) -> None:
        brouillonId = self.ouvrirCreation()
        self.ajouter(brouillonId, type="texte", texte="La carte est refusée")
        self.commenter(brouillonId, "Testé")
        version = self.contexte.version
        reponse = self.appliquer(brouillonId)
        self.assertEqual(reponse.status_code, 201, reponse.get_data(as_text=True))
        self.assertEqual(reponse.headers["Location"], "/ticket/11")
        rapport = reponse.get_json()
        self.assertEqual(rapport["libelle"], "Session de création")
        self.assertEqual(rapport["ticketId"], 11)
        self.assertEqual(rapport["nombreSucces"], 2)
        self.assertEqual(rapport["refus"], [])
        self.assertGreater(self.contexte.version, version)

        ticket = self.requete("GET", "/ticket/11", ADMIN).get_json()
        self.assertEqual(ticket["titre"], "Paiement")
        self.assertEqual(ticket["statut"], "OUVERT")
        self.assertEqual(ticket["createur"]["id"], JULIEN)
        self.assertEqual(ticket["commentaires"][0]["texte"], "Testé")
        self.assertEqual(ticket["description"][0]["contenu"], "La carte est refusée")

        relu = self.recharger().ticketParId(11)
        self.assertEqual(relu.title, "Paiement")
        self.assertEqual(len(relu.comments), 1)

    def test_edition(self) -> None:
        brouillonId = self.ouvrirEdition(6)
        self.commenter(brouillonId, "Testé")
        version = self.contexte.version
        reponse = self.appliquer(brouillonId)
        self.assertEqual(reponse.status_code, 200, reponse.get_data(as_text=True))
        self.assertNotIn("Location", reponse.headers)
        rapport = reponse.get_json()
        self.assertEqual(rapport["libelle"], "Session d'édition")
        self.assertIsNone(rapport["ticketId"])
        self.assertEqual(rapport["nombreSucces"], 1)
        self.assertGreater(self.contexte.version, version)
        self.assertEqual(self.recharger().ticketParId(6).comments[0].texte, "Testé")

    def test_brouillon_disparait(self) -> None:
        brouillonId = self.ouvrirCreation()
        self.commenter(brouillonId)
        self.appliquer(brouillonId)
        self.verifierErreur(self.appliquer(brouillonId), 404, "RessourceIntrouvable")
        self.assertEqual(self.requete("GET", "/acteur/3/brouillons", JULIEN).get_json(), [])

    def test_texte_ajoute_a_l_application(self) -> None:
        brouillonId = self.ouvrirCreation()
        rapport = self.appliquer(brouillonId, {"texte": "  La carte  "}).get_json()
        self.assertEqual(rapport["nombreSucces"], 1)
        ticket = self.requete("GET", "/ticket/11", ADMIN).get_json()
        self.assertEqual(ticket["description"][0]["contenu"], "La carte")

    def test_corps_facultatif_et_texte_vide_ignore(self) -> None:
        for corps in (None, {}, {"texte": ""}, {"texte": "   "}):
            with self.subTest(corps=corps):
                brouillonId = self.ouvrirEdition(6)
                self.commenter(brouillonId)
                reponse = self.appliquer(brouillonId, corps)
                self.assertEqual(reponse.status_code, 200, reponse.get_data(as_text=True))
                self.assertEqual(reponse.get_json()["nombreSucces"], 1)

    def test_format_du_corps(self) -> None:
        brouillonId = self.ouvrirCreation()
        for corps in ({"texte": 5}, {"texte": None}, {"autre": 1}):
            with self.subTest(corps=corps):
                self.verifierErreur(self.appliquer(brouillonId, corps), 400, "RequeteInvalide")
        reponse = self.client.post(
            self.chemin(brouillonId, "/application"),
            headers={"X-Acteur-Id": str(JULIEN)},
            data=b"{ pas du JSON",
        )
        self.verifierErreur(reponse, 400, "RequeteInvalide")
        self.assertTrue(self.lire(brouillonId)["ouverte"])

    def test_images_gardees(self) -> None:
        brouillonId = self.ouvrirCreation()
        self.ajouter(brouillonId, **corpsImage())
        self.assertEqual(self.appliquer(brouillonId).status_code, 201)
        self.assertEqual(len(self.fichiers()), 1)
        ticket = self.requete("GET", "/ticket/11", ADMIN).get_json()
        self.assertEqual(ticket["description"][0]["type"], "image")
        self.assertEqual(self.recharger().ticketParId(11).description.nombreElements, 1)

    def test_en_pause_refuse_sans_rien_ajouter(self) -> None:
        for corps in (None, {"texte": "Tapé"}):
            with self.subTest(corps=corps):
                brouillonId = self.ouvrirCreation()
                self.mettreEnPause(brouillonId)
                reponse = self.appliquer(brouillonId, corps)
                self.verifierErreur(reponse, 409, "SessionIndisponibleException")
                self.assertEqual(self.lire(brouillonId)["modificationsEnAttente"], [])
        self.assertFalse(self.sauvegarde.exists())

    def test_ticket_supprime_texte_retire_et_copies_rangees_par_l_abandon(self) -> None:
        """Le refus retire le texte, pour qu'il ne soit pas ajouté deux fois au prochain essai."""
        brouillonId = self.ouvrirEdition(6)
        self.ajouter(brouillonId, **corpsImage())
        self.assertEqual(self.requete("DELETE", "/ticket/6", JULIEN).status_code, 204)
        for _ in range(2):
            reponse = self.appliquer(brouillonId, {"texte": "Tapé"})
            self.verifierErreur(reponse, 409, "SessionIndisponibleException")
            self.assertEqual(len(self.lire(brouillonId)["modificationsEnAttente"]), 1)
        self.assertEqual(len(self.fichiers()), 1)
        self.assertEqual(self.abandonner(brouillonId).status_code, 204)
        self.assertEqual(self.fichiers(), [])

    def test_creation_vide_acceptee_par_le_modele(self) -> None:
        """Seule F5 l'empêche, en grisant le bouton : une règle qui manque au métier."""
        reponse = self.appliquer(self.ouvrirCreation())
        self.assertEqual(reponse.status_code, 201)
        self.assertEqual(reponse.get_json()["nombreSucces"], 0)
        ticket = self.requete("GET", "/ticket/11", ADMIN).get_json()
        self.assertEqual(ticket["description"], [])
        self.assertIsNotNone(self.recharger().ticketParId(11))

    def test_edition_vide_ne_sauvegarde_rien(self) -> None:
        brouillonId = self.ouvrirEdition(6)
        version = self.contexte.version
        reponse = self.appliquer(brouillonId)
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.get_json()["nombreSucces"], 0)
        self.verifierRienEcrit(version)

    def test_ticket_ferme_reste_editable(self) -> None:
        """Le modèle autorise commentaires et éléments dans tous les états."""
        self.requete("PATCH", "/ticket/6", ADMIN, {"statut": "FERME"})
        brouillonId = self.ouvrirEdition(6)
        self.commenter(brouillonId)
        self.assertEqual(self.appliquer(brouillonId).get_json()["nombreSucces"], 1)
        self.assertIs(self.ticket(6).status, Statut.FERME)


class TestParcours(TestBrouillons):
    def imageDe(self, ticketId: int) -> str:
        ticket = self.requete("GET", f"/ticket/{ticketId}", ADMIN).get_json()
        return next(e["url"] for e in ticket["description"] if e["type"] == "image")

    def test_creation_complete(self) -> None:
        """Tout le parcours du plan, jusqu'au téléchargement de l'image."""
        version = self.contexte.version

        # Ouvrir, puis ajouter texte, commentaire et image.
        reponse = self.ouvrir(type="creation", titre="Paiement refusé", priorite="HAUTE")
        self.assertEqual(reponse.status_code, 201)
        brouillonId = reponse.get_json()["id"]
        ticketId = reponse.get_json()["ticket"]["id"]
        self.assertEqual(
            self.ajouter(brouillonId, type="texte", texte="La carte est refusée").status_code, 201
        )
        self.commenter(brouillonId, "Testé sur Firefox")
        self.assertEqual(self.ajouter(brouillonId, **corpsImage("capture.png")).status_code, 201)
        copie = self.fichiers()[0]

        # Annuler le dernier ajout : une seconde image, dont la copie doit disparaître.
        self.assertEqual(self.ajouter(brouillonId, **corpsImage("en_trop.png")).status_code, 201)
        self.assertEqual(len(self.fichiers()), 2)
        annulation = self.annuler(brouillonId)
        self.assertEqual(annulation.status_code, 200)
        self.assertIn("_en_trop.png", annulation.get_json()["libelleRetire"])
        self.assertEqual(self.fichiers(), [copie])

        brouillon = self.lire(brouillonId)
        self.assertEqual(len(brouillon["modificationsEnAttente"]), 3)
        self.assertEqual(brouillon["nombreImages"], 1)

        # Mettre en pause avec le texte tapé : tout ajout est refusé, sans laisser de copie.
        reponse = self.requete(
            "PATCH",
            self.chemin(brouillonId),
            JULIEN,
            {"enPause": True, "texteBrouillon": "Depuis lundi"},
        )
        self.assertTrue(reponse.get_json()["enPause"])
        for corps in ({"type": "commentaire", "texte": "Refusé"}, corpsImage("refusee.png")):
            with self.subTest(type=corps["type"]):
                reponse = self.ajouter(brouillonId, **corps)
                self.verifierErreur(reponse, 409, "SessionIndisponibleException")
        self.verifierErreur(self.appliquer(brouillonId), 409, "SessionIndisponibleException")
        self.assertEqual(self.fichiers(), [copie])
        self.assertEqual(len(self.lire(brouillonId)["modificationsEnAttente"]), 3)

        # Rien n'a encore changé pour les autres : ni ticket, ni sauvegarde, ni version.
        lecture = self.requete("GET", f"/ticket/{ticketId}", ADMIN)
        self.verifierErreur(lecture, 404, "RessourceIntrouvable")
        self.verifierRienEcrit(version)

        # Reprendre : le texte tapé est toujours là, et le client le renvoie à l'application.
        reponse = self.requete("PATCH", self.chemin(brouillonId), JULIEN, {"enPause": False})
        brouillon = reponse.get_json()
        self.assertFalse(brouillon["enPause"])
        self.assertEqual(brouillon["texteBrouillon"], "Depuis lundi")

        # Appliquer : le rapport décrit chaque modification, et le brouillon disparaît.
        reponse = self.appliquer(brouillonId, {"texte": brouillon["texteBrouillon"]})
        self.assertEqual(reponse.status_code, 201, reponse.get_data(as_text=True))
        self.assertEqual(reponse.headers["Location"], f"/ticket/{ticketId}")
        rapport = reponse.get_json()
        self.assertEqual(rapport["ticketId"], ticketId)
        self.assertEqual(rapport["nombreSucces"], 4)
        self.assertEqual(rapport["nombreRefus"], 0)
        self.assertGreater(self.contexte.version, version)
        relu = self.requete("GET", self.chemin(brouillonId), JULIEN)
        self.verifierErreur(relu, 404, "RessourceIntrouvable")

        # Lire le ticket, dans l'ordre des ajouts.
        ticket = self.requete("GET", f"/ticket/{ticketId}", ABDOUL).get_json()
        self.assertEqual(ticket["titre"], "Paiement refusé")
        self.assertEqual(ticket["createur"]["id"], JULIEN)
        self.assertEqual([c["texte"] for c in ticket["commentaires"]], ["Testé sur Firefox"])
        self.assertEqual(
            [e["type"] for e in ticket["description"]], ["texte_saisi", "image", "texte_saisi"]
        )
        self.assertEqual(ticket["description"][0]["contenu"], "La carte est refusée")
        self.assertEqual(ticket["description"][2]["contenu"], "Depuis lundi")

        # Télécharger l'image par l'URL donnée, sans acteur.
        image = self.client.get(ticket["description"][1]["url"])
        self.assertEqual(image.status_code, 200)
        self.assertEqual(image.mimetype, "image/png")
        self.assertEqual(image.get_data(), IMAGE)
        self.assertEqual(self.fichiers(), [copie])

    def test_serveur_relance_apres_application(self) -> None:
        """Le ticket et son image survivent à un redémarrage, pas un brouillon resté ouvert."""
        applique = self.ouvrirCreation()
        self.ajouter(applique, **corpsImage())
        self.commenter(applique)
        self.assertEqual(self.appliquer(applique).status_code, 201)
        reste = self.ouvrirCreation()
        url = self.imageDe(11)

        relance = ContexteServeur(cheminSauvegarde=self.sauvegarde, dossierImages=str(self.images))
        client = creerApplication(relance).test_client()
        enTete = {"X-Acteur-Id": str(JULIEN)}
        ticket = client.get("/ticket/11", headers=enTete).get_json()
        self.assertEqual(len(ticket["commentaires"]), 1)
        self.assertEqual(client.get(url).get_data(), IMAGE)
        self.assertEqual(client.get("/acteur/3/brouillons", headers=enTete).get_json(), [])
        relu = client.get(f"/acteur/3/brouillon/{reste}", headers=enTete)
        self.verifierErreur(relu, 404, "RessourceIntrouvable")

        # Le numéro du ticket appliqué ne resservira pas, et l'image reste au bon ticket.
        nouveau = client.post(
            "/acteur/3/brouillons",
            headers=enTete,
            json={"type": "creation", "titre": "Après", "priorite": "BASSE"},
        ).get_json()
        self.assertEqual(nouveau["ticket"]["id"], 12)

    def test_edition_complete_puis_suppression(self) -> None:
        """Éditer, relire l'image, puis supprimer le ticket et sa copie."""
        brouillonId = self.ouvrirEdition(6)
        self.commenter(brouillonId, "Précision")
        self.ajouter(brouillonId, **corpsImage())
        self.assertEqual(len(self.fichiers()), 1)
        ancien = len(self.ticket(6).description.elements)

        reponse = self.appliquer(brouillonId, {"texte": "Nouveau détail"})
        self.assertEqual(reponse.status_code, 200, reponse.get_data(as_text=True))
        self.assertEqual(reponse.get_json()["nombreSucces"], 3)
        ticket = self.requete("GET", "/ticket/6", ADMIN).get_json()
        self.assertEqual(ticket["nombreCommentaires"], 1)
        self.assertEqual(len(ticket["description"]), ancien + 2)
        url = self.imageDe(6)
        self.assertEqual(self.client.get(url).get_data(), IMAGE)
        self.assertIs(self.recharger().ticketParId(6).status, Statut.OUVERT)

        self.assertEqual(self.requete("DELETE", "/ticket/6", JULIEN).status_code, 204)
        self.assertEqual(self.fichiers(), [])
        self.verifierErreur(self.client.get(url), 404, "RessourceIntrouvable")

    def test_image_en_attente_pas_encore_servie(self) -> None:
        """Elle n'est dans aucune description : ni son chemin ni son nom ne sont exposés."""
        brouillonId = self.ouvrirEdition(6)
        self.ajouter(brouillonId, **corpsImage())
        nom = self.fichiers()[0].name
        self.verifierErreur(self.client.get(f"/ticket/6/image/{nom}"), 404, "RessourceIntrouvable")
        self.assertEqual(self.appliquer(brouillonId).status_code, 200)
        self.assertEqual(self.client.get(f"/ticket/6/image/{nom}").status_code, 200)

    def test_brouillons_de_deux_users_independants(self) -> None:
        julien = self.ouvrirCreation(JULIEN)
        mike = self.ouvrirCreation(MIKE)
        self.ajouter(julien, **corpsImage())
        self.ajouter(mike, MIKE, **corpsImage())
        self.assertEqual(self.abandonner(mike, MIKE).status_code, 204)
        self.assertEqual(len(self.fichiers()), 1)
        self.assertEqual(self.appliquer(julien).status_code, 201)
        self.assertEqual(self.client.get(self.imageDe(11)).get_data(), IMAGE)


if __name__ == "__main__":
    unittest.main()
