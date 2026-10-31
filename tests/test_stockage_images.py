"""Tests de StockageImages, dans un dossier temporaire."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from acteurs.user import User
from modele.enums import Priorite
from modele.exceptions import ArtefactInvalideException
from modele.systeme_tickets import SystemeTickets
from modele.ticket import Ticket
from persistance.stockage_images import StockageImages

imageOrigine = Path(__file__).resolve().parent.parent / "ressources" / "capture_ecran.png"


class TestStockageImages(unittest.TestCase):
    """Copie des images dans donnees/images, relatif au dossier de travail."""

    def setUp(self) -> None:
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        # Le stockage par défaut est relatif : on travaille depuis le dossier temporaire.
        # Nettoyages en ordre inverse : on revient au dossier initial avant d'effacer le temporaire.
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(temporaire.name)
        self._dossierTravail: Path = Path(temporaire.name)
        self._stockage: StockageImages = StockageImages()

    def testCopieReussie(self) -> None:
        chemin = self._stockage.copier(str(imageOrigine))
        self.assertRegex(chemin, r"^donnees/images/[0-9a-f]{8}_capture_ecran\.png$")
        self.assertEqual(Path(chemin).read_bytes(), imageOrigine.read_bytes())
        self.assertTrue(imageOrigine.is_file())

    def testCopieUtilisableParLaSession(self) -> None:
        chemin = self._stockage.copier(str(imageOrigine))
        systeme = SystemeTickets()
        createur = User(1, "Abdoul Razack", "abdoul.razack@uqac.ca", systeme)
        ticket = Ticket(1, "Bug de connexion", Priorite.HAUTE)
        createur.createTicket(ticket)
        session = createur.ouvrirSessionEdition(ticket)
        session.ajouterElement("image", chemin)
        session.appliquer()
        self.assertEqual(ticket.description.elements[0].chemin, chemin)

    def testNomUniquePourDeuxCopies(self) -> None:
        premiere = self._stockage.copier(str(imageOrigine))
        seconde = self._stockage.copier(str(imageOrigine))
        self.assertNotEqual(premiere, seconde)
        self.assertTrue(Path(premiere).is_file())
        self.assertTrue(Path(seconde).is_file())

    def testExtensionSansTenirCompteDeLaCasse(self) -> None:
        gif = self._dossierTravail / "animation.GIF"
        gif.write_bytes(b"GIF89a")
        chemin = self._stockage.copier(str(gif))
        self.assertTrue(chemin.endswith("_animation.GIF"))

    def testRefusJpg(self) -> None:
        jpg = self._dossierTravail / "photo.jpg"
        jpg.write_bytes(b"\xff\xd8\xff")
        with self.assertRaises(ArtefactInvalideException):
            self._stockage.copier(str(jpg))
        self.assertFalse(Path("donnees/images").exists())

    def testRefusFichierAbsent(self) -> None:
        with self.assertRaises(ArtefactInvalideException):
            self._stockage.copier("absent.png")

    def testSupprimerEffaceUneCopie(self) -> None:
        chemin = self._stockage.copier(str(imageOrigine))
        self._stockage.supprimer(chemin)
        self.assertFalse(Path(chemin).exists())

    def testSupprimerSansEffetHorsDuDossier(self) -> None:
        self._stockage.copier(str(imageOrigine))
        original = self._dossierTravail / "original.png"
        original.write_bytes(imageOrigine.read_bytes())
        for chemin in (str(original), "donnees/images/../../original.png"):
            with self.subTest(chemin=chemin):
                self._stockage.supprimer(chemin)
                self.assertTrue(original.is_file())

    def testSupprimerFichierAbsentSansEffet(self) -> None:
        self._stockage.supprimer("donnees/images/inexistant.png")
