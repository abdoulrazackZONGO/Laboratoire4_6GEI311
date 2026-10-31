"""Tests des données de démonstration donnees/demo.json, sans fenêtre."""
from __future__ import annotations

import os
import unittest
from pathlib import Path
from typing import TYPE_CHECKING

from modele.enums import Statut
from persistance.depot_json import DepotJSON

if TYPE_CHECKING:
    from description.element_description import ElementDescription

racineDepot = Path(__file__).resolve().parent.parent


class TestDonneesDemo(unittest.TestCase):
    """demo.json se charge comme au démarrage de l'application, depuis la racine du dépôt."""

    @classmethod
    def setUpClass(cls) -> None:
        # Les chemins des images sont relatifs à la racine, comme dans l'application.
        cls._dossierInitial = os.getcwd()
        os.chdir(racineDepot)
        try:
            cls._depot = DepotJSON("donnees/demo.json")
            cls._systeme = cls._depot.charger()
        except BaseException:
            # tearDownClass n'est pas appelé si setUpClass échoue.
            os.chdir(cls._dossierInitial)
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        os.chdir(cls._dossierInitial)

    def elements(self, typeArtefact: str) -> list[ElementDescription]:
        return [
            element
            for ticket in self._systeme.tickets
            for element in ticket.description.elements
            if element.typeArtefact == typeArtefact
        ]

    def testAucunAvertissement(self) -> None:
        self.assertEqual(self._depot.avertissements, [])

    def testHuitTickets(self) -> None:
        self.assertEqual(len(self._systeme.tickets), 8)

    def testCinqStatutsPresents(self) -> None:
        self.assertEqual({ticket.status for ticket in self._systeme.tickets}, set(Statut))

    def testPlusGrandIdentifiant(self) -> None:
        self.assertEqual(max(ticket.ticketID for ticket in self._systeme.tickets), 10)

    def testAucuneVideo(self) -> None:
        self.assertEqual(self.elements("video"), [])

    def testChaqueImageExiste(self) -> None:
        images = self.elements("image")
        self.assertTrue(images)
        for image in images:
            with self.subTest(chemin=image.chemin):
                self.assertTrue(Path(image.chemin).is_file())
