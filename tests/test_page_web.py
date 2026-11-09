"""Tests de W1 : service de la page web, et page qui n'utilise que l'API du contrat.

La page elle-même s'essaie dans un navigateur ; ces tests vérifient ce qui se lit sans lui :
les trois fichiers servis, rien d'autre du disque, et les chemins appelés par app.js.

Lancer depuis la racine du dépôt :  python -m unittest discover -s tests -t . -v
"""
from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from api import creerApplication
from api.contexte import ContexteServeur
from tests.test_contrat_openapi import CONTRAT, operationsDuContrat

RACINE = Path(__file__).resolve().parent.parent
WEB = RACINE / "web"


class TestServicePage(unittest.TestCase):
    def setUp(self) -> None:
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        contexte = ContexteServeur(cheminSauvegarde=Path(dossier.name) / "sauvegarde.json")
        self.client = creerApplication(contexte).test_client()

    def test_trois_fichiers_avec_leur_type(self) -> None:
        """Sans en-tête X-Acteur-Id : le navigateur charge la page avant tout choix d'acteur."""
        for chemin, fichier, typeAttendu in (
            ("/", "index.html", "text/html; charset=utf-8"),
            ("/app.js", "app.js", "text/javascript; charset=utf-8"),
            ("/style.css", "style.css", "text/css; charset=utf-8"),
        ):
            with self.subTest(chemin=chemin):
                reponse = self.client.get(chemin)
                self.assertEqual(reponse.status_code, 200)
                self.assertEqual(reponse.headers["Content-Type"], typeAttendu)
                self.assertEqual(reponse.headers["X-Content-Type-Options"], "nosniff")
                self.assertEqual(reponse.headers["Cache-Control"], "no-cache")
                self.assertEqual(reponse.get_data(), (WEB / fichier).read_bytes())

    def test_la_page_charge_ses_deux_fichiers(self) -> None:
        page = self.client.get("/").get_data(as_text=True)
        self.assertIn('<script src="/app.js" defer></script>', page)
        self.assertIn('<link rel="stylesheet" href="/style.css">', page)

    def test_aucun_autre_fichier_servi(self) -> None:
        for chemin in (
            "/index.html",
            "/web/app.js",
            "/web/index.html",
            "/app.js/../serveur.py",
            "/..%2Fserveur.py",
            "/serveur.py",
            "/openapi.yaml",
            "/donnees/demo.json",
            "/static/app.js",
        ):
            with self.subTest(chemin=chemin):
                reponse = self.client.get(chemin)
                self.assertEqual(reponse.status_code, 404, reponse.get_data(as_text=True)[:200])
                self.assertEqual(reponse.mimetype, "application/json")

    def test_seul_get_est_permis(self) -> None:
        for chemin in ("/", "/app.js", "/style.css"):
            with self.subTest(chemin=chemin):
                reponse = self.client.post(chemin)
                self.assertEqual(reponse.status_code, 405)
                self.assertEqual(reponse.get_json()["erreur"]["type"], "MethodeNonPermise")


class TestScriptDeLaPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = (WEB / "app.js").read_text(encoding="utf-8")
        cls.contrat = operationsDuContrat(CONTRAT.read_text(encoding="utf-8"))

    def appels(self) -> list[tuple[str, str]]:
        """(MÉTHODE, chemin) de chaque api(...) ; ${...} devient un paramètre, ?... est retiré."""
        appels = []
        for methode, _, chemin in re.findall(r'api\(\s*"([A-Z]+)",\s*([`"])(.+?)\2', self.script):
            chemin = re.sub(r"\$\{[^}]*\}", "{x}", chemin).split("?")[0]
            appels.append((methode, chemin))
        return appels

    def test_chaque_appel_est_une_operation_du_contrat(self) -> None:
        motifs = {
            (methode, re.compile("^" + re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(chemin)) + "$"))
            for chemin, methode in self.contrat
        }
        appels = self.appels()
        self.assertGreaterEqual(len(appels), 7)
        for methode, chemin in appels:
            with self.subTest(appel=f"{methode} {chemin}"):
                self.assertTrue(
                    any(m == methode and motif.match(chemin) for m, motif in motifs),
                    f"{methode} {chemin} n'est pas dans openapi.yaml",
                )

    def test_operations_demandees_presentes(self) -> None:
        appels = set(self.appels())
        for attendu in (
            ("GET", "/acteurs"),
            ("GET", "/tickets"),
            ("GET", "/ticket/{x}"),
            ("POST", "/tickets"),
            ("PATCH", "/ticket/{x}"),
            ("DELETE", "/ticket/{x}"),
            ("GET", "/version"),
        ):
            with self.subTest(attendu=attendu):
                self.assertIn(attendu, appels)

    def test_parametres_de_liste_du_contrat(self) -> None:
        """La vue User filtre par createur et assigne, l'Admin et les filtres par statut."""
        parametres = set(re.findall(r"requete\(\{\s*(?:\.\.\.vue,\s*)?(\w+):", self.script))
        parametres |= set(re.findall(r'parametre: "(\w+)"', self.script))
        self.assertEqual(parametres, {"createur", "assigne", "statut"})
        contrat = CONTRAT.read_text(encoding="utf-8")
        for nom in parametres:
            with self.subTest(parametre=nom):
                self.assertRegex(contrat, rf"name: {nom}\b")

    def test_deux_vues(self) -> None:
        """Comme F2 et F3 : onglets du User, actions de l'Admin, actions du User."""
        for attendu in (
            '"Créés par moi"',
            '"Assignés à moi"',
            "function actionsAdmin(",
            "function actionsUser(",
            '"Soumettre à validation"',
            '"Tous les tickets"',
            '"Mes tickets"',
        ):
            with self.subTest(attendu=attendu):
                self.assertIn(attendu, self.script)

    def test_donnees_jamais_inserees_comme_html(self) -> None:
        """Un titre de ticket ne doit pas pouvoir injecter de script dans la page."""
        for interdit in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
            with self.subTest(interdit=interdit):
                self.assertNotIn(interdit, self.script)

    def test_en_tete_acteur_envoye(self) -> None:
        self.assertIn('entetes["X-Acteur-Id"]', self.script)


if __name__ == "__main__":
    unittest.main()
