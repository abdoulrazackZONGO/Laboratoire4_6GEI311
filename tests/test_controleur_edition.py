"""Tests de ControleurEdition, sans fenêtre : un faux principal remplace ControleurPrincipal."""
from __future__ import annotations

import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

from acteurs.user import User
from ihm.controleurs.controleur_edition import ControleurEdition
from modele.enums import Priorite
from modele.exceptions import SessionIndisponibleException
from modele.systeme_tickets import SystemeTickets
from modele.ticket import Ticket
from persistance.stockage_images import StockageImages
from sessions.rapport_execution import RapportExecution

racineDepot = Path(__file__).resolve().parent.parent


def ecrirePng(chemin: Path) -> Path:
    """Vrai PNG minimal : un pixel RVB."""
    def bloc(nature: bytes, donnees: bytes) -> bytes:
        crc = zlib.crc32(nature + donnees) & 0xFFFFFFFF
        return struct.pack(">I", len(donnees)) + nature + donnees + struct.pack(">I", crc)

    chemin.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + bloc(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + bloc(b"IDAT", zlib.compress(b"\x00\x25\x63\xeb"))
        + bloc(b"IEND", b"")
    )
    return chemin


class FauxPrincipal:
    """Remplace ControleurPrincipal : aucune fenêtre, les rapports affichés sont notés."""

    def __init__(self, dossierImages: Path) -> None:
        self.systeme = SystemeTickets()
        self.stockage = StockageImages(str(dossierImages))
        self.rapports: list[tuple[RapportExecution, str]] = []

    def afficherRapport(self, rapport: RapportExecution, libelle: str) -> None:
        self.rapports.append((rapport, libelle))


class TestControleurEdition(unittest.TestCase):
    """Session de création de T Julien ; les images sont copiées dans un dossier temporaire."""

    def setUp(self) -> None:
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        self._dossier = Path(temporaire.name)
        self._dossierImages = self._dossier / "images"
        self._principal = FauxPrincipal(self._dossierImages)
        self._julien = User(3, "T Julien", "t.julien@uqac.ca", self._principal.systeme)
        self._ticket = Ticket(11, "Pagination de l'historique cassée", Priorite.HAUTE)
        self._session = self._julien.ouvrirSessionCreation(self._ticket)
        self._controleur = ControleurEdition(self._principal, self._session)
        self._capture = str(ecrirePng(self._dossier / "capture_historique.png"))
        self._console = str(ecrirePng(self._dossier / "console_erreur.png"))

    def copies(self) -> list[Path]:
        """Copies présentes dans le dossier de stockage."""
        if not self._dossierImages.exists():
            return []
        return sorted(self._dossierImages.iterdir())

    def testDeuxImagesEnUneSelection(self) -> None:
        refus = self._controleur.ajouterImages([self._capture, self._console])
        self.assertEqual(refus, [])
        self.assertEqual(len(self.copies()), 2)
        self.assertEqual(len(self._session.modificationsEnAttente), 2)
        self.assertEqual(self._controleur.nombreImages, 2)

    def testImageRefuseeSansCopieLesAutresAjoutees(self) -> None:
        jpg = self._dossier / "photo.jpg"
        jpg.write_bytes(b"\xff\xd8\xff")
        absente = str(self._dossier / "absente.png")
        refus = self._controleur.ajouterImages([self._capture, str(jpg), absente, self._console])
        self.assertEqual(len(refus), 2)
        self.assertIn("photo.jpg", refus[0])
        self.assertIn("absente.png", refus[1])
        self.assertEqual(len(self.copies()), 2)
        self.assertEqual(len(self._session.modificationsEnAttente), 2)

    def testUndoImageSupprimeSaCopie(self) -> None:
        self._controleur.ajouterImages([self._capture])
        self.assertEqual(len(self.copies()), 1)
        libelle = self._controleur.annulerDerniere()
        self.assertIn("[Image]", libelle)
        self.assertEqual(self.copies(), [])
        self.assertEqual(self._controleur.nombreImages, 0)

    def testUndoCommentaireSansToucherAuxFichiers(self) -> None:
        self._controleur.ajouterImages([self._capture])
        self._controleur.commenter("Se produit seulement après la page 3.")
        copiesAvant = self.copies()
        libelle = self._controleur.annulerDerniere()
        self.assertIn("commentaire", libelle)
        self.assertEqual(self.copies(), copiesAvant)
        self.assertEqual(len(self._session.modificationsEnAttente), 1)
        self.assertEqual(self._controleur.nombreImages, 1)

    def testAbandonSupprimeToutesLesCopies(self) -> None:
        self._controleur.ajouterImages([self._capture, self._console])
        self._controleur.commenter("Commentaire")
        self._controleur.abandonner()
        self.assertEqual(self.copies(), [])
        self.assertFalse(self._session.estOuverte)
        self.assertFalse(self._principal.systeme.contient(self._ticket))

    def testPauseGardeLeTexteHorsDeLaSession(self) -> None:
        texte = "Le bouton « Page suivante » ne réagit plus."
        self._controleur.mettreEnPause(texte)
        self.assertEqual(self._controleur.texteBrouillon, texte)
        self.assertTrue(self._session.estEnPause)
        self.assertEqual(self._session.modificationsEnAttente, [])
        # La reprise est faite par ControleurPrincipal.ouvrirEdition().
        self._session.reprendre()
        self._controleur.appliquer(self._controleur.texteBrouillon)
        elements = self._ticket.description.elements
        self.assertEqual([element.typeArtefact for element in elements], ["texte"])
        self.assertEqual(elements[0].contenu, texte)

    def testAppliquerEnCreation(self) -> None:
        self._controleur.ajouterImages([self._capture])
        self._controleur.commenter("Commentaire")
        self._controleur.mettreEnPause("Texte de la description")
        self._session.reprendre()
        self._controleur.appliquer("Texte de la description")
        self.assertTrue(self._principal.systeme.contient(self._ticket))
        self.assertIs(self._ticket.creator, self._julien)
        self.assertEqual(len(self._principal.rapports), 1)
        rapport, libelle = self._principal.rapports[0]
        self.assertEqual(libelle, "Session de création")
        self.assertEqual((rapport.nombreSucces, rapport.nombreRefus), (3, 0))
        self.assertEqual(self._controleur.nombreImages, 0)
        self.assertEqual(self._controleur.texteBrouillon, "")
        # L'image appliquée reste : sa copie est maintenant référencée par le ticket.
        self.assertEqual(len(self.copies()), 1)

    def testAppliquerSansTexteNAjouteRien(self) -> None:
        self._controleur.ajouterImages([self._capture])
        self._controleur.appliquer("   \n")
        self.assertEqual(self._ticket.description.nombreElements, 1)

    def testAppliquerRefuseRetireLeTexte(self) -> None:
        abdoul = User(2, "Abdoul Razack", "abdoul.razack@uqac.ca", self._principal.systeme)
        ticket = Ticket(6, "Bouton Annuler inactif", Priorite.MOYENNE)
        abdoul.createTicket(ticket)
        session = abdoul.ouvrirSessionEdition(ticket)
        controleur = ControleurEdition(self._principal, session)
        controleur.commenter("Commentaire")
        abdoul.supprimerTicket(ticket)
        with self.assertRaises(SessionIndisponibleException):
            controleur.appliquer("Texte")
        # Le texte n'est pas resté dans la pile : un nouvel essai ne le doublera pas.
        self.assertEqual(len(session.modificationsEnAttente), 1)
        self.assertEqual(self._principal.rapports, [])

    def testEstCreation(self) -> None:
        self.assertTrue(self._controleur.estCreation)
        abdoul = User(2, "Abdoul Razack", "abdoul.razack@uqac.ca", self._principal.systeme)
        ticket = Ticket(6, "Bouton Annuler inactif", Priorite.MOYENNE)
        abdoul.createTicket(ticket)
        edition = ControleurEdition(self._principal, abdoul.ouvrirSessionEdition(ticket))
        self.assertFalse(edition.estCreation)
        # Calculé une seule fois : il ne bascule pas quand le ticket entre dans le dépôt.
        self._controleur.appliquer("Texte")
        self.assertTrue(self._controleur.estCreation)

    def testSansTkinter(self) -> None:
        """Le contrôleur reste testable dans le CI, qui n'a pas d'écran."""
        resultat = subprocess.run(
            [sys.executable, "-c",
             "import sys, ihm.controleurs.controleur_edition; "
             "print(any(m.startswith('tkinter') for m in sys.modules))"],
            cwd=racineDepot, capture_output=True, text=True, check=True,
        )
        self.assertEqual(resultat.stdout.strip(), "False")
