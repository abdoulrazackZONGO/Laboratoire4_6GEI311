"""Tests de S5 : les chemins et méthodes de openapi.yaml sont exactement ceux de l'application.

Le YAML est lu ligne par ligne, sans dépendance : seule la section paths compte, et sa forme
est régulière (chemin indenté de 2 espaces, méthode de 4). Un fichier qui changerait de
forme ferait échouer test_lecture_du_contrat, au lieu de passer en silence.

Lancer depuis la racine du dépôt :  python -m unittest discover -s tests -t . -v
"""
from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from api import creerApplication
from api.contexte import ContexteServeur

CONTRAT = Path(__file__).resolve().parent.parent / "openapi.yaml"
METHODES_HTTP = {"get", "put", "post", "delete", "patch", "options", "head", "trace"}
# Ajoutées par Werkzeug à chaque route : elles ne sont pas des opérations du contrat.
METHODES_AUTOMATIQUES = {"HEAD", "OPTIONS"}
# Routes servies hors du contrat (la page web du bonus W1, par exemple) : chacune s'écrit ici.
ROUTES_HORS_CONTRAT: set[tuple[str, str]] = set()


def operationsDuContrat(texte: str) -> set[tuple[str, str]]:
    """(chemin, MÉTHODE) de la section paths, par exemple ("/ticket/{ticketId}", "PATCH")."""
    operations: set[tuple[str, str]] = set()
    dansPaths = False
    chemin: str | None = None
    for ligne in texte.splitlines():
        if re.match(r"^\S", ligne):
            dansPaths = ligne.rstrip() == "paths:"
            chemin = None
            continue
        if not dansPaths:
            continue
        trouve = re.match(r"^  (/\S*):\s*$", ligne)
        if trouve:
            chemin = trouve.group(1)
            continue
        trouve = re.match(r"^    ([a-z]+):", ligne)
        if trouve and chemin is not None and trouve.group(1) in METHODES_HTTP:
            operations.add((chemin, trouve.group(1).upper()))
    return operations


def operationsDeFlask() -> set[tuple[str, str]]:
    """Les mêmes couples pour l'application ; <int:ticketId> s'écrit {ticketId}."""
    with tempfile.TemporaryDirectory() as dossier:
        contexte = ContexteServeur(cheminSauvegarde=Path(dossier) / "sauvegarde.json")
        app = creerApplication(contexte)
    operations: set[tuple[str, str]] = set()
    for regle in app.url_map.iter_rules():
        chemin = re.sub(r"<(?:[^:<>]+:)?([^:<>]+)>", r"{\1}", regle.rule)
        for methode in (regle.methods or set()) - METHODES_AUTOMATIQUES:
            operations.add((chemin, methode))
    return operations


class TestContratOpenAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contrat = operationsDuContrat(CONTRAT.read_text(encoding="utf-8"))
        cls.flask = operationsDeFlask()

    def test_lecture_du_contrat(self) -> None:
        """Garde-fou de la lecture sans PyYAML : les 21 opérations du tableau de CLAUDE.md."""
        self.assertEqual(len(self.contrat), 21)
        self.assertEqual(len({chemin for chemin, _ in self.contrat}), 14)
        self.assertIn(("/ticket/{ticketId}/image/{nomImage}", "GET"), self.contrat)
        self.assertIn(
            ("/acteur/{acteurId}/brouillon/{brouillonId}/modification/derniere", "DELETE"),
            self.contrat,
        )
        # La ligne « parameters: » d'un chemin n'est pas une méthode.
        self.assertNotIn("PARAMETERS", {methode for _, methode in self.contrat})

    def test_chaque_operation_du_contrat_existe(self) -> None:
        manquantes = sorted(self.contrat - self.flask)
        self.assertEqual(manquantes, [], "opérations du contrat absentes de l'application")

    def test_aucune_route_hors_du_contrat(self) -> None:
        enTrop = sorted(self.flask - self.contrat - ROUTES_HORS_CONTRAT)
        self.assertEqual(enTrop, [], "routes de l'application absentes du contrat")

    def test_routes_hors_contrat_bien_servies(self) -> None:
        """Une route listée comme hors contrat doit exister : la liste ne garde rien d'ancien."""
        self.assertEqual(sorted(ROUTES_HORS_CONTRAT - self.flask), [])

    def test_pas_de_route_static_automatique(self) -> None:
        """Flask en ajoute une par défaut ; la page web sera servie par routes_systeme."""
        self.assertNotIn("/static/{filename}", {chemin for chemin, _ in self.flask})


class TestLectureDuYAML(unittest.TestCase):
    """La lecture sans dépendance, sur un petit contrat écrit à la main."""

    def test_forme_reguliere(self) -> None:
        texte = (
            "openapi: 3.0.3\n"
            "paths:\n"
            "  /tickets:\n"
            "    get:\n"
            "      summary: x\n"
            "    post:\n"
            "      responses:\n"
            "        '201':\n"
            "          description: get: pas une méthode\n"
            "  /ticket/{ticketId}:\n"
            "    parameters:\n"
            "      - $ref: '#/x'\n"
            "    delete:\n"
            "      summary: y\n"
            "components:\n"
            "  /pas/un/chemin:\n"
            "    get:\n"
        )
        self.assertEqual(
            operationsDuContrat(texte),
            {("/tickets", "GET"), ("/tickets", "POST"), ("/ticket/{ticketId}", "DELETE")},
        )


if __name__ == "__main__":
    unittest.main()
