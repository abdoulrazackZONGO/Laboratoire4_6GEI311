"""Tests de S5 : outils/essai_api.py contre un vrai serveur, lancé dans ce processus.

Le script sert juste avant la démo : ce test vérifie qu'il reste d'accord avec le serveur.

Lancer depuis la racine du dépôt :  python -m unittest discover -s tests -t . -v
"""
from __future__ import annotations

import io
import logging
import socket
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from werkzeug.serving import make_server

from api import creerApplication
from api.contexte import ContexteServeur
from outils import essai_api
from persistance.depot_json import DepotJSON


class TestEssaiAPI(unittest.TestCase):
    def setUp(self) -> None:
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.sauvegarde = Path(dossier.name) / "sauvegarde.json"
        self.contexte = ContexteServeur(
            cheminSauvegarde=self.sauvegarde, dossierImages=str(Path(dossier.name) / "images")
        )
        journal = logging.getLogger("werkzeug")
        self.addCleanup(journal.setLevel, journal.level)
        journal.setLevel(logging.ERROR)
        serveur = make_server("127.0.0.1", 0, creerApplication(self.contexte), threaded=True)
        fil = threading.Thread(target=serveur.serve_forever, daemon=True)
        fil.start()
        self.addCleanup(fil.join, 5)
        self.addCleanup(serveur.server_close)
        self.addCleanup(serveur.shutdown)
        self.url = f"http://127.0.0.1:{serveur.server_port}"

    def executer(self) -> tuple[int, list[str]]:
        sortie = io.StringIO()
        code = essai_api.executer(self.url, sortie)
        return code, sortie.getvalue().splitlines()

    def test_tout_conforme(self) -> None:
        statutsDemo = {t.ticketID: t.status for t in self.contexte.systeme.tickets}
        code, lignes = self.executer()
        self.assertEqual(code, 0, "\n".join(lignes))
        requetes = [ligne for ligne in lignes if ligne.startswith("[")]
        self.assertEqual(len(requetes), 9)
        self.assertTrue(all(ligne.startswith("[OK]") for ligne in requetes), requetes)
        self.assertIn("Toutes les réponses sont celles attendues.", lignes)

        # Les étapes demandées : lecture, création, assignation, transition refusée, lot.
        texte = "\n".join(lignes)
        self.assertIn("[OK] 201 (attendu 201)  POST   /tickets  ticket #11 créé", texte)
        self.assertIn("assigné à", texte)
        refus = "[OK] 409 (attendu 409)  PATCH  /ticket/11  TransitionInvalideException"
        self.assertIn(refus, texte)
        self.assertIn("lot : 1 succès, 0 refus", texte)

        # Les tickets de démonstration n'ont pas bougé ; le ticket de l'essai est sauvegardé.
        for ticketId, statut in statutsDemo.items():
            self.assertIs(self.contexte.systeme.ticketParId(ticketId).status, statut)
        relu = DepotJSON(self.sauvegarde).charger().ticketParId(11)
        self.assertEqual(relu.title, "Essai avant la démo")
        self.assertTrue(relu.aDejaEteAssigne)

    def test_deux_essais_de_suite(self) -> None:
        """Avant la démo, on peut le relancer : il crée simplement un ticket de plus."""
        self.assertEqual(self.executer()[0], 0)
        code, lignes = self.executer()
        self.assertEqual(code, 0, "\n".join(lignes))
        self.assertIn("ticket #12 créé", "\n".join(lignes))

    def test_ecart_au_contrat_signale(self) -> None:
        """Si le serveur acceptait la transition interdite, l'essai le dirait et rendrait 1."""
        with mock.patch("acteurs.admin.Admin.validerTicket"):
            code, lignes = self.executer()
        self.assertEqual(code, 1)
        self.assertIn("[KO] 200 (attendu 409)  PATCH  /ticket/11", "\n".join(lignes))
        self.assertIn("1 réponse(s) inattendue(s) : à corriger avant la démo.", lignes)

    def test_serveur_injoignable(self) -> None:
        with socket.socket() as prise:
            prise.bind(("127.0.0.1", 0))
            port = prise.getsockname()[1]
        sortie = io.StringIO()
        code = essai_api.executer(f"http://127.0.0.1:{port}", sortie)
        self.assertEqual(code, 2)
        self.assertIn("Serveur injoignable", sortie.getvalue())
        self.assertIn("python serveur.py", sortie.getvalue())

    def test_ligne_de_commande(self) -> None:
        sortie = io.StringIO()
        with redirect_stdout(sortie):
            code = essai_api.main(["--url", self.url])
        self.assertEqual(code, 0, sortie.getvalue())
        self.assertIn("Toutes les réponses sont celles attendues.", sortie.getvalue())


if __name__ == "__main__":
    unittest.main()
