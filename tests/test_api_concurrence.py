"""Tests de S5 : requêtes simultanées sur un vrai serveur, lancé dans ce processus.

Le serveur Flask sert chaque requête dans son propre fil (threaded=True, comme serveur.py).
Créer en même temps doit donner des identifiants tous différents et une sauvegarde lisible.

Lancer depuis la racine du dépôt :  python -m unittest discover -s tests -t . -v
"""
from __future__ import annotations

import json
import logging
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from unittest import mock

from werkzeug.serving import make_server

from api import creerApplication
from api.contexte import ContexteServeur
from persistance.depot_json import DepotJSON

JULIEN, MIKE = 3, 4
FILS_TICKETS = 8
TICKETS_PAR_FIL = 3
FILS_BROUILLONS = 4
DELAI = 20.0
# Aucun proxy : comme ClientAPI, pour qu'un proxy système n'intercepte pas 127.0.0.1.
_OUVREUR = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class TestCreationsSimultanees(unittest.TestCase):
    def setUp(self) -> None:
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.sauvegarde = Path(dossier.name) / "sauvegarde.json"
        self.contexte = ContexteServeur(
            cheminSauvegarde=self.sauvegarde, dossierImages=str(Path(dossier.name) / "images")
        )
        # Une ligne de journal par requête : inutile ici, et elle noierait le résultat.
        journal = logging.getLogger("werkzeug")
        self.addCleanup(journal.setLevel, journal.level)
        journal.setLevel(logging.ERROR)

        self.serveur = make_server(
            "127.0.0.1", 0, creerApplication(self.contexte), threaded=True
        )
        fil = threading.Thread(target=self.serveur.serve_forever, daemon=True)
        fil.start()
        self.addCleanup(fil.join, 5)
        self.addCleanup(self.serveur.server_close)
        self.addCleanup(self.serveur.shutdown)
        self.url = f"http://127.0.0.1:{self.serveur.server_port}"

    def envoyer(self, methode: str, chemin: str, acteurId: int, corps: Any = None):
        """(code, corps JSON) ; une réponse d'erreur est rendue, pas levée."""
        donnees = None if corps is None else json.dumps(corps).encode("utf-8")
        requete = urllib.request.Request(
            self.url + chemin,
            data=donnees,
            method=methode,
            headers={"X-Acteur-Id": str(acteurId), "Content-Type": "application/json"},
        )
        try:
            with _OUVREUR.open(requete, timeout=DELAI) as reponse:
                return reponse.status, json.loads(reponse.read() or b"null")
        except urllib.error.HTTPError as erreur:
            with erreur:
                return erreur.code, json.loads(erreur.read() or b"null")

    def surveillerSimultanes(self, objet: object, nom: str) -> dict[str, int]:
        """Remplace objet.nom par une version lente qui compte ses appels simultanés.

        L'attente élargit la fenêtre où deux fils se croiseraient : sans le verrou du
        contexte, le maximum dépasse 1. Le CPython seul ne le montrerait presque jamais.
        """
        original = getattr(objet, nom)
        compte = {"actifs": 0, "maximum": 0}
        verrou = threading.Lock()

        def lent(*arguments: Any, **options: Any) -> Any:
            with verrou:
                compte["actifs"] += 1
                compte["maximum"] = max(compte["maximum"], compte["actifs"])
            try:
                time.sleep(0.002)
                return original(*arguments, **options)
            finally:
                with verrou:
                    compte["actifs"] -= 1

        remplacement = mock.patch.object(objet, nom, side_effect=lent)
        remplacement.start()
        self.addCleanup(remplacement.stop)
        return compte

    def lancer(self, taches: list) -> list[str]:
        """Démarre toutes les tâches au même instant ; rend les erreurs levées dans les fils."""
        depart = threading.Barrier(len(taches))
        erreurs: list[str] = []

        def executer(tache) -> None:
            try:
                depart.wait(DELAI)
                tache()
            except Exception as erreur:  # noqa: BLE001 - rapportée par le test
                erreurs.append(repr(erreur))

        fils = [threading.Thread(target=executer, args=(tache,)) for tache in taches]
        for fil in fils:
            fil.start()
        for fil in fils:
            fil.join(DELAI * 3)
        self.assertFalse(any(fil.is_alive() for fil in fils), "un fil ne s'est pas terminé")
        return erreurs

    def test_post_tickets_et_brouillons_en_meme_temps(self) -> None:
        """POST /tickets et les brouillons de création réservent tous des identifiants."""
        resultats: list[tuple[str, int, Any]] = []
        verrou = threading.Lock()

        def noter(origine: str, code: int, corps: Any) -> None:
            with verrou:
                resultats.append((origine, code, corps))

        def creerTickets(numero: int) -> None:
            for rang in range(TICKETS_PAR_FIL):
                corps = {"titre": f"Fil {numero}, ticket {rang}", "priorite": "BASSE", "texte": "x"}
                noter("tickets", *self.envoyer("POST", "/tickets", JULIEN, corps))

        def creerParBrouillon(numero: int) -> None:
            corps = {"type": "creation", "titre": f"Brouillon {numero}", "priorite": "HAUTE"}
            code, brouillon = self.envoyer("POST", f"/acteur/{MIKE}/brouillons", MIKE, corps)
            self.assertEqual(code, 201, brouillon)
            chemin = f"/acteur/{MIKE}/brouillon/{brouillon['id']}/application"
            noter("brouillon", *self.envoyer("POST", chemin, MIKE, {"texte": f"Texte {numero}"}))

        reservations = self.surveillerSimultanes(self.contexte.systeme, "reserverIdentifiant")
        sauvegardes = self.surveillerSimultanes(self.contexte.depot, "sauvegarder")
        taches = [lambda n=n: creerTickets(n) for n in range(FILS_TICKETS)]
        taches += [lambda n=n: creerParBrouillon(n) for n in range(FILS_BROUILLONS)]
        self.assertEqual(self.lancer(taches), [])

        # Le verrou du contexte : jamais deux réservations ni deux écritures du fichier à la fois.
        self.assertEqual(reservations["maximum"], 1)
        self.assertEqual(sauvegardes["maximum"], 1)

        attendus = FILS_TICKETS * TICKETS_PAR_FIL + FILS_BROUILLONS
        self.assertEqual(len(resultats), attendus)
        for origine, code, corps in resultats:
            self.assertEqual(code, 201, (origine, corps))
        identifiants = [
            corps["ticket"]["id"] if origine == "tickets" else corps["ticketId"]
            for origine, _, corps in resultats
        ]
        self.assertEqual(len(set(identifiants)), attendus, sorted(identifiants))

        # Relue par DepotJSON, la sauvegarde contient chaque ticket créé, une seule fois.
        relus = [ticket.ticketID for ticket in DepotJSON(self.sauvegarde).charger().tickets]
        self.assertEqual(len(relus), len(set(relus)))
        self.assertTrue(set(identifiants) <= set(relus))
        self.assertEqual(len(relus), len(self.contexte.systeme.tickets))

    def test_ecritures_et_lectures_melangees(self) -> None:
        """Lectures pendant les écritures : jamais d'erreur, et une version qui ne recule pas."""

        def lire() -> None:
            versions: list[int] = []
            for _ in range(10):
                code, liste = self.envoyer("GET", "/tickets", JULIEN)
                self.assertEqual(code, 200)
                self.assertIsInstance(liste, list)
                code, version = self.envoyer("GET", "/version", JULIEN)
                versions.append(version["version"])
            # Vues par un même client, l'une après l'autre.
            self.assertEqual(versions, sorted(versions))

        def ecrire(numero: int) -> None:
            for rang in range(5):
                corps = {"titre": f"{numero}-{rang}", "priorite": "BASSE", "texte": "x"}
                code, _ = self.envoyer("POST", "/tickets", JULIEN, corps)
                self.assertEqual(code, 201)

        taches = [lire for _ in range(4)] + [lambda n=n: ecrire(n) for n in range(4)]
        self.assertEqual(self.lancer(taches), [])
        self.assertEqual(len(self.contexte.systeme.tickets), 8 + 4 * 5)
        self.assertGreater(self.contexte.version, 0)
        self.assertEqual(len(DepotJSON(self.sauvegarde).charger().tickets), 8 + 4 * 5)


if __name__ == "__main__":
    unittest.main()
