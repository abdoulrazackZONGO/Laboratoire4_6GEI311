"""Tests de S5 : la table des erreurs de CLAUDE.md, ligne par ligne, sur de vraies routes.

Chaque réponse est vérifiée en entier : code, Content-Type et corps exactement
{"erreur": {"type", "message"}}, avec un type prévu par le schéma Erreur de openapi.yaml.

Lancer depuis la racine du dépôt :  python -m unittest discover -s tests -t . -v
"""
from __future__ import annotations

import base64
import io
import unittest
from contextlib import redirect_stderr
from typing import Any
from unittest import mock

from tests.test_api_tickets import ABDOUL, ADMIN, JULIEN, TestEcriture

# Valeurs du champ type, d'après la description du schéma Erreur de openapi.yaml.
TYPES_DU_CONTRAT = {
    "TransitionInvalideException",
    "SessionIndisponibleException",
    "SuppressionInterditeException",
    "AccesRefuseException",
    "ArtefactInvalideException",
    "RequeteInvalide",
    "ActeurNonIdentifie",
    "RessourceIntrouvable",
    "MethodeNonPermise",
    "RequeteTropVolumineuse",
    "ErreurInterne",
}
STATUTS = "OUVERT, ASSIGNE, VALIDATION, TERMINE, FERME"


class TestTableDesErreurs(TestEcriture):
    def verifier(
        self,
        reponse,
        code: int,
        typeErreur: str,
        message: str | None = None,
        debut: str | None = None,
    ) -> dict[str, Any]:
        """Le format complet d'une erreur ; le message exact, ou seulement son début."""
        self.assertEqual(reponse.status_code, code, reponse.get_data(as_text=True)[:300])
        self.assertEqual(reponse.mimetype, "application/json")
        corps = reponse.get_json()
        self.assertEqual(set(corps), {"erreur"})
        self.assertEqual(set(corps["erreur"]), {"type", "message"})
        self.assertIn(typeErreur, TYPES_DU_CONTRAT)
        self.assertEqual(corps["erreur"]["type"], typeErreur)
        self.assertIsInstance(corps["erreur"]["message"], str)
        if message is not None:
            self.assertEqual(corps["erreur"]["message"], message)
        if debut is not None:
            self.assertTrue(corps["erreur"]["message"].startswith(debut), corps)
        return corps["erreur"]

    def changerStatut(self, donnees: bytes | dict[str, Any], acteurId: int | None = ADMIN):
        """PATCH /ticket/6 : un corps JSON (dict) ou des octets bruts."""
        enTetes = {} if acteurId is None else {"X-Acteur-Id": str(acteurId)}
        if isinstance(donnees, bytes):
            return self.client.patch("/ticket/6", headers=enTetes, data=donnees)
        return self.client.patch("/ticket/6", headers=enTetes, json=donnees)

    # ------------------------------------------------------------------ 400

    def test_json_illisible(self) -> None:
        reponse = self.changerStatut(b"{ pas du JSON")
        self.verifier(reponse, 400, "RequeteInvalide", debut="Corps JSON illisible : ")

    def test_corps_qui_n_est_pas_un_objet(self) -> None:
        for donnees in (b"[1, 2]", b'"FERME"', b"42"):
            with self.subTest(donnees=donnees):
                reponse = self.changerStatut(donnees)
                self.verifier(reponse, 400, "RequeteInvalide", "Le corps JSON doit être un objet")

    def test_champ_manquant(self) -> None:
        """L'exemple de la réponse RequeteInvalide de openapi.yaml."""
        reponse = self.changerStatut({})
        self.verifier(reponse, 400, "RequeteInvalide", "Champ obligatoire manquant : statut")

    def test_champ_inconnu(self) -> None:
        reponse = self.changerStatut({"statut": "FERME", "statu": "FERME"})
        self.verifier(reponse, 400, "RequeteInvalide", "Champ inconnu : statu")

    def test_enum_invalide(self) -> None:
        reponse = self.changerStatut({"statut": "INCONNU"})
        message = f"Valeur invalide pour statut : 'INCONNU' (attendu : {STATUTS})"
        self.verifier(reponse, 400, "RequeteInvalide", message)

    def test_parametre_de_requete_invalide(self) -> None:
        reponse = self.requete("GET", "/tickets?statut=ferme", ADMIN)
        message = f"Valeur invalide pour statut : 'ferme' (attendu : {STATUTS})"
        self.verifier(reponse, 400, "RequeteInvalide", message)
        reponse = self.requete("GET", "/tickets?statu=FERME", ADMIN)
        self.verifier(reponse, 400, "RequeteInvalide", "Paramètre inconnu : statu")

    def test_artefact_refuse_par_le_modele(self) -> None:
        brouillon = self.requete(
            "POST", "/acteur/3/brouillons", JULIEN, {"type": "edition", "ticketId": 6}
        ).get_json()
        reponse = self.requete(
            "POST",
            f"/acteur/3/brouillon/{brouillon['id']}/modifications",
            JULIEN,
            {"type": "texte", "texte": "   "},
        )
        self.verifier(reponse, 400, "ArtefactInvalideException", "Texte saisi vide")

    # ------------------------------------------------------------------ 401

    def test_en_tete_absent(self) -> None:
        """L'exemple de la réponse NonIdentifie de openapi.yaml."""
        reponse = self.changerStatut({"statut": "FERME"}, acteurId=None)
        self.verifier(reponse, 401, "ActeurNonIdentifie", "En-tête X-Acteur-Id absent")

    def test_en_tete_non_entier(self) -> None:
        reponse = self.client.get("/tickets", headers={"X-Acteur-Id": "abc"})
        self.verifier(reponse, 401, "ActeurNonIdentifie", "En-tête X-Acteur-Id non entier : 'abc'")

    def test_acteur_inconnu(self) -> None:
        reponse = self.requete("GET", "/tickets", 99)
        self.verifier(reponse, 401, "ActeurNonIdentifie", "Acteur inconnu : 99")

    # ------------------------------------------------------------------ 403

    def test_mauvais_role(self) -> None:
        reponse = self.changerStatut({"statut": "FERME"}, acteurId=JULIEN)
        message = "T Julien n'a pas le rôle Admin : action refusée"
        self.verifier(reponse, 403, "AccesRefuseException", message)

    def test_acteur_du_chemin_different_de_l_en_tete(self) -> None:
        reponse = self.requete("GET", f"/acteur/{ADMIN}/brouillons", JULIEN)
        message = f"T Julien ne peut pas agir au nom de l'acteur {ADMIN}"
        self.verifier(reponse, 403, "AccesRefuseException", message)

    def test_acces_refuse_par_le_modele(self) -> None:
        """L'exemple de la réponse AccesRefuse de openapi.yaml."""
        reponse = self.requete("DELETE", "/ticket/2", JULIEN)
        message = "T Julien n'est pas le créateur du ticket 2"
        self.verifier(reponse, 403, "AccesRefuseException", message)

    # ------------------------------------------------------------------ 404 et 405

    def test_ressource_inexistante(self) -> None:
        """L'exemple de la réponse Introuvable de openapi.yaml."""
        reponse = self.requete("GET", "/ticket/99", ADMIN)
        self.verifier(reponse, 404, "RessourceIntrouvable", "Ticket introuvable : 99")

    def test_chemin_inconnu(self) -> None:
        reponse = self.requete("GET", "/inconnu", ADMIN)
        self.verifier(reponse, 404, "RessourceIntrouvable", "Chemin inconnu : /inconnu")

    def test_methode_non_permise(self) -> None:
        """Un lot n'est pas conservé : pas de GET sur ce chemin, et Allow le dit."""
        reponse = self.requete("GET", f"/acteur/{ADMIN}/lots", ADMIN)
        message = f"Méthode GET non permise sur /acteur/{ADMIN}/lots"
        self.verifier(reponse, 405, "MethodeNonPermise", message)
        permises = {m.strip() for m in reponse.headers["Allow"].split(",")}
        self.assertIn("POST", permises)
        self.assertNotIn("GET", permises)

    # ------------------------------------------------------------------ 409

    def test_transition_invalide(self) -> None:
        """L'exemple de la réponse Conflit de openapi.yaml : le ticket 1 est TERMINE."""
        reponse = self.requete("PATCH", "/ticket/1", ADMIN, {"statut": "FERME"})
        message = "Transition invalide : impossible de passer de l'état TERMINE au statut FERME"
        self.verifier(reponse, 409, "TransitionInvalideException", message)

    def test_session_indisponible(self) -> None:
        corps = {"type": "edition", "ticketId": 6}
        premier = self.requete("POST", "/acteur/3/brouillons", JULIEN, corps)
        self.assertEqual(premier.status_code, 201)
        reponse = self.requete("POST", "/acteur/3/brouillons", JULIEN, corps)
        message = "Une session est déjà ouverte sur le ticket 6 : session d'édition refusée"
        self.verifier(reponse, 409, "SessionIndisponibleException", message)

    def test_suppression_interdite(self) -> None:
        reponse = self.requete("DELETE", "/ticket/2", ABDOUL)
        message = "Le ticket 2 a déjà été assigné : suppression interdite"
        self.verifier(reponse, 409, "SuppressionInterditeException", message)

    # ------------------------------------------------------------------ 413

    def test_requete_trop_volumineuse(self) -> None:
        """L'exemple de la réponse TropVolumineux de openapi.yaml : au-delà de 8 Mo."""
        corps = {"titre": "x", "priorite": "BASSE", "texte": "x" * (9 * 1024 * 1024)}
        reponse = self.requete("POST", "/tickets", JULIEN, corps)
        message = "Requête trop volumineuse (8 Mo au plus)"
        self.verifier(reponse, 413, "RequeteTropVolumineuse", message)

    def test_image_trop_volumineuse(self) -> None:
        brouillon = self.requete(
            "POST", "/acteur/3/brouillons", JULIEN, {"type": "edition", "ticketId": 6}
        ).get_json()
        contenu = base64.b64encode(b"x" * (5 * 1024 * 1024 + 1)).decode("ascii")
        reponse = self.requete(
            "POST",
            f"/acteur/3/brouillon/{brouillon['id']}/modifications",
            JULIEN,
            {"type": "image", "nomFichier": "grosse.png", "contenuBase64": contenu},
        )
        message = "Image trop volumineuse (5 Mo au plus)"
        self.verifier(reponse, 413, "RequeteTropVolumineuse", message)

    # ------------------------------------------------------------------ 500

    def test_exception_imprevue(self) -> None:
        """Message générique dans la réponse, trace complète dans la console du serveur."""
        console = io.StringIO()
        panne = RuntimeError("détail interne à ne pas divulguer")
        with (
            mock.patch.object(self.systeme, "ticketParId", side_effect=panne),
            redirect_stderr(console),
        ):
            reponse = self.requete("GET", "/ticket/1", ADMIN)
        self.verifier(reponse, 500, "ErreurInterne", "Erreur interne du serveur")
        texte = reponse.get_data(as_text=True)
        for indice in ("Traceback", "RuntimeError", "détail interne", "ticketParId", ".py"):
            with self.subTest(indice=indice):
                self.assertNotIn(indice, texte)
        self.assertIn("Traceback", console.getvalue())
        self.assertIn("RuntimeError: détail interne à ne pas divulguer", console.getvalue())

    def test_exception_imprevue_pendant_une_ecriture(self) -> None:
        """Même format, et la route n'a rien sauvegardé."""
        version = self.contexte.version
        with (
            mock.patch.object(self.systeme, "ticketParId", side_effect=KeyError("x")),
            redirect_stderr(io.StringIO()),
        ):
            reponse = self.requete("PATCH", "/ticket/6", ADMIN, {"statut": "FERME"})
        self.verifier(reponse, 500, "ErreurInterne", "Erreur interne du serveur")
        self.verifierRienEcrit(version)


if __name__ == "__main__":
    unittest.main()
