"""Tests de S1 : lecture et vérification du corps JSON (api/validation.py).

Lancer depuis la racine du dépôt :  python -m unittest discover -s tests -t . -v
"""
from __future__ import annotations

import unittest
from typing import Any

from flask import Flask

from api.erreurs import RequeteInvalide
from api.validation import booleen, chaineNonVide, entier, enumParNom, lireCorps, verifierChamps
from modele.enums import Priorite, Statut


class TestLireCorps(unittest.TestCase):
    def setUp(self) -> None:
        self.app = Flask(__name__)

    def lire(self, donnees: bytes) -> dict[str, Any]:
        with self.app.test_request_context(method="POST", data=donnees):
            return lireCorps()

    def verifierRefus(self, donnees: bytes, debutMessage: str) -> None:
        with self.assertRaises(RequeteInvalide) as contexte:
            self.lire(donnees)
        self.assertTrue(str(contexte.exception).startswith(debutMessage), str(contexte.exception))

    def test_objet_valide(self) -> None:
        corps = self.lire('{"titre": "Paiement refusé", "priorite": "HAUTE"}'.encode())
        self.assertEqual(corps, {"titre": "Paiement refusé", "priorite": "HAUTE"})

    def test_corps_absent(self) -> None:
        self.verifierRefus(b"", "Corps JSON absent")
        self.verifierRefus(b"   ", "Corps JSON absent")

    def test_corps_illisible(self) -> None:
        self.verifierRefus(b"{ pas du JSON", "Corps JSON illisible")
        self.verifierRefus(b"\xff\xfe\xfa", "Corps JSON illisible")

    def test_corps_qui_n_est_pas_un_objet(self) -> None:
        self.verifierRefus(b"[1, 2]", "Le corps JSON doit être un objet")
        self.verifierRefus(b'"texte"', "Le corps JSON doit être un objet")


class TestVerifierChamps(unittest.TestCase):
    def test_champs_obligatoires_et_facultatifs(self) -> None:
        verifierChamps({"statut": "ASSIGNE"}, ["statut"], ["assigneId"])
        verifierChamps({"statut": "ASSIGNE", "assigneId": 3}, ["statut"], ["assigneId"])

    def test_champ_manquant(self) -> None:
        with self.assertRaises(RequeteInvalide) as contexte:
            verifierChamps({"assigneId": 3}, ["statut"], ["assigneId"])
        self.assertEqual(str(contexte.exception), "Champ obligatoire manquant : statut")

    def test_champ_inconnu(self) -> None:
        with self.assertRaises(RequeteInvalide) as contexte:
            verifierChamps({"statut": "FERME", "statu": "FERME"}, ["statut"])
        self.assertEqual(str(contexte.exception), "Champ inconnu : statu")


class TestTypes(unittest.TestCase):
    def verifierRefus(self, fonction, corps: dict[str, Any], *arguments: Any) -> str:
        with self.assertRaises(RequeteInvalide) as contexte:
            fonction(corps, "champ", *arguments)
        return str(contexte.exception)

    def test_champ_absent(self) -> None:
        for fonction in (entier, booleen, chaineNonVide):
            with self.subTest(fonction=fonction.__name__):
                self.assertEqual(
                    self.verifierRefus(fonction, {}), "Champ obligatoire manquant : champ"
                )

    def test_entier(self) -> None:
        self.assertEqual(entier({"champ": 3}, "champ"), 3)
        for valeur in (True, "3", 3.5, None):
            with self.subTest(valeur=valeur):
                self.assertEqual(
                    self.verifierRefus(entier, {"champ": valeur}),
                    "Le champ champ doit être un entier",
                )

    def test_booleen(self) -> None:
        self.assertIs(booleen({"champ": False}, "champ"), False)
        for valeur in (1, "true", None):
            with self.subTest(valeur=valeur):
                self.assertEqual(
                    self.verifierRefus(booleen, {"champ": valeur}),
                    "Le champ champ doit être un booléen",
                )

    def test_chaine_non_vide(self) -> None:
        self.assertEqual(chaineNonVide({"champ": " Bug "}, "champ"), " Bug ")
        self.assertIn("ne doit pas être vide", self.verifierRefus(chaineNonVide, {"champ": ""}))
        self.assertIn("ne doit pas être vide", self.verifierRefus(chaineNonVide, {"champ": "  "}))
        self.assertIn("doit être une chaîne", self.verifierRefus(chaineNonVide, {"champ": 5}))

    def test_enum_par_nom(self) -> None:
        self.assertIs(enumParNom({"champ": "ASSIGNE"}, "champ", Statut), Statut.ASSIGNE)
        self.assertIs(enumParNom({"champ": "CRITIQUE"}, "champ", Priorite), Priorite.CRITIQUE)
        for valeur in ("assigne", "INCONNU", 3, None):
            with self.subTest(valeur=valeur):
                message = self.verifierRefus(enumParNom, {"champ": valeur}, Statut)
                self.assertEqual(
                    message,
                    f"Valeur invalide pour champ : {valeur!r} "
                    "(attendu : OUVERT, ASSIGNE, VALIDATION, TERMINE, FERME)",
                )


if __name__ == "__main__":
    unittest.main()
