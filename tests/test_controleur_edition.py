"""Tests de ControleurEdition (F5), sans fenêtre, contre la vraie API : le brouillon vit sur le
serveur d'essai, qui garde ses copies d'images dans un dossier temporaire.
"""
from __future__ import annotations

import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

from ihm.controleurs.controleur_edition import ControleurEdition
from ihm.passerelle.objets_lecture import BrouillonLu, RapportLu, TicketLu
from modele.enums import Priorite
from modele.exceptions import SessionIndisponibleException
from tests.serveur_essai import JULIEN, ServeurEssai

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
    """Remplace ControleurPrincipal : aucune fenêtre ; rapports et signaux notés."""

    def __init__(self) -> None:
        self.rapports: list[tuple[RapportLu, str]] = []
        self.signaux = 0

    def afficherRapport(self, rapport: RapportLu, libelle: str) -> None:
        self.rapports.append((rapport, libelle))

    def signalerBrouillons(self) -> None:
        self.signaux += 1


class TestControleurEdition(unittest.TestCase):
    """Brouillon de création de T Julien ; deux images PNG prêtes à envoyer."""

    def setUp(self) -> None:
        self.serveur = ServeurEssai()
        self.addCleanup(self.serveur.fermer)
        temporaire = tempfile.TemporaryDirectory()
        self.addCleanup(temporaire.cleanup)
        self.dossier = Path(temporaire.name)
        self.principal = FauxPrincipal()
        _, self.client, self.source = self.serveur.session(JULIEN)
        self.controleur = self.ouvrir(
            self.client.ouvrirBrouillonCreation("Pagination de l'historique cassée", Priorite.HAUTE)
        )
        self.capture = str(ecrirePng(self.dossier / "capture_historique.png"))
        self.console = str(ecrirePng(self.dossier / "console_erreur.png"))

    def ouvrir(self, donnees: dict) -> ControleurEdition:
        return ControleurEdition(
            self.principal, self.client, BrouillonLu.depuisJSON(donnees), self.source  # type: ignore[arg-type]
        )

    def copies(self) -> list[Path]:
        """Copies présentes dans le dossier d'images du serveur."""
        dossier = self.serveur.dossierImages
        return sorted(dossier.iterdir()) if dossier.exists() else []

    def surLeServeur(self) -> BrouillonLu:
        return BrouillonLu.depuisJSON(self.client.lireBrouillon(self.controleur.brouillonId))

    def ticket(self, ticketId: int) -> TicketLu:
        return TicketLu.depuisJSON(self.client.lireTicket(ticketId))

    # ------------------------------------------------------------------ images et undo

    def testDeuxImagesEnUneSelection(self) -> None:
        refus = self.controleur.ajouterImages([self.capture, self.console])
        self.assertEqual(refus, [])
        self.assertEqual(len(self.copies()), 2)
        self.assertEqual(len(self.controleur.modificationsEnAttente), 2)
        self.assertEqual(self.controleur.nombreImages, 2)
        self.assertEqual(self.surLeServeur().nombreImages, 2)

    def testImageRefuseeLesAutresAjoutees(self) -> None:
        jpg = self.dossier / "photo.jpg"
        jpg.write_bytes(b"\xff\xd8\xff")
        absente = str(self.dossier / "absente.png")
        refus = self.controleur.ajouterImages([self.capture, str(jpg), absente, self.console])
        self.assertEqual(len(refus), 2)
        self.assertTrue(refus[0].startswith("photo.jpg : "))
        self.assertTrue(refus[1].startswith("absente.png : "))
        self.assertEqual(len(self.copies()), 2)
        self.assertEqual(len(self.controleur.modificationsEnAttente), 2)

    def testUndoImageSupprimeSaCopie(self) -> None:
        self.controleur.ajouterImages([self.capture])
        self.assertEqual(len(self.copies()), 1)
        libelle = self.controleur.annulerDerniere()
        self.assertIn("[Image]", libelle)
        self.assertEqual(self.copies(), [])
        self.assertEqual(self.controleur.nombreImages, 0)

    def testUndoCommentaireSansToucherAuxFichiers(self) -> None:
        self.controleur.ajouterImages([self.capture])
        self.controleur.commenter("Se produit seulement après la page 3.")
        copiesAvant = self.copies()
        libelle = self.controleur.annulerDerniere()
        self.assertIn("commentaire", libelle)
        self.assertEqual(self.copies(), copiesAvant)
        self.assertEqual(len(self.controleur.modificationsEnAttente), 1)
        self.assertEqual(self.controleur.nombreImages, 1)

    # ------------------------------------------------------------------ abandon et pause

    def testAbandonSupprimeToutesLesCopies(self) -> None:
        self.controleur.ajouterImages([self.capture, self.console])
        self.controleur.commenter("Commentaire")
        self.controleur.abandonner()
        self.assertEqual(self.copies(), [])
        self.assertFalse(self.controleur.estOuverte)
        self.assertEqual(self.controleur.modificationsEnAttente, [])
        self.assertEqual(self.client.listerBrouillons(), [])
        self.source.rafraichir()
        self.assertIsNone(self.source.ticketParId(self.controleur.ticket.ticketID))
        self.assertEqual(self.principal.signaux, 1)

    def testPauseGardeLeTexteSurLeServeur(self) -> None:
        texte = "Le bouton « Page suivante » ne réagit plus."
        self.controleur.mettreEnPause(texte)
        self.assertTrue(self.controleur.estEnPause)
        self.assertEqual(self.controleur.texteBrouillon, texte)
        serveur = self.surLeServeur()
        self.assertTrue(serveur.estEnPause)
        self.assertEqual(serveur.texteBrouillon, texte)
        # Le texte n'est pas une modification en attente : il n'entre qu'à l'application.
        self.assertEqual(serveur.modificationsEnAttente, [])
        # Rien ne s'ajoute pendant la pause.
        with self.assertRaises(SessionIndisponibleException):
            self.controleur.commenter("Pendant la pause")
        # Reprise (faite par ControleurPrincipal.ouvrirEdition), puis application du texte gardé.
        self.controleur.actualiser(BrouillonLu.depuisJSON(
            self.client.modifierBrouillon(self.controleur.brouillonId, enPause=False)
        ))
        rapport = self.controleur.appliquer(self.controleur.texteBrouillon)
        elements = self.ticket(rapport.ticketId).description.elements
        self.assertEqual([(e.typeArtefact, e.contenu) for e in elements], [("texte", texte)])

    # ------------------------------------------------------------------ application

    def testAppliquerEnCreation(self) -> None:
        numero = self.controleur.ticket.ticketID
        self.controleur.ajouterImages([self.capture])
        self.controleur.commenter("Commentaire")
        rapport = self.controleur.appliquer("Texte de la description")
        self.assertEqual(rapport.ticketId, numero)
        self.assertEqual((rapport.nombreSucces, rapport.nombreRefus), (3, 0))
        self.assertEqual(self.principal.rapports, [(rapport, "Session de création")])
        # La source est relue : le ticket créé est déjà dans la liste, avec son créateur.
        ticket = self.source.ticketParId(numero)
        self.assertIsNotNone(ticket)
        self.assertEqual(ticket.creator.id, JULIEN)
        self.assertFalse(self.controleur.estOuverte)
        self.assertEqual((self.controleur.nombreImages, self.controleur.texteBrouillon), (0, ""))
        # L'image appliquée reste : sa copie est maintenant référencée par le ticket.
        self.assertEqual(len(self.copies()), 1)
        self.assertEqual(self.client.listerBrouillons(), [])

    def testAppliquerSansTexteNAjouteRien(self) -> None:
        self.controleur.ajouterImages([self.capture])
        rapport = self.controleur.appliquer("   \n")
        self.assertEqual(self.ticket(rapport.ticketId).description.nombreElements, 1)

    def testAppliquerRefuseRetireLeTexte(self) -> None:
        # #6 : ticket de Julien, jamais assigné, donc supprimable pendant son édition.
        controleur = self.ouvrir(self.client.ouvrirBrouillonEdition(6))
        controleur.commenter("Commentaire")
        self.client.supprimerTicket(6)
        with self.assertRaises(SessionIndisponibleException):
            controleur.appliquer("Texte")
        # Le texte n'est pas resté dans la pile : un nouvel essai ne le doublera pas.
        serveur = BrouillonLu.depuisJSON(self.client.lireBrouillon(controleur.brouillonId))
        self.assertEqual(len(serveur.modificationsEnAttente), 1)
        self.assertTrue(controleur.estOuverte)
        self.assertEqual(self.principal.rapports, [])

    def testEstCreation(self) -> None:
        self.assertTrue(self.controleur.estCreation)
        edition = self.ouvrir(self.client.ouvrirBrouillonEdition(6))
        self.assertFalse(edition.estCreation)
        # Il ne bascule pas quand le ticket entre dans le dépôt.
        self.controleur.appliquer("Texte")
        self.assertTrue(self.controleur.estCreation)

    def testChaqueChangementDEtatEstSignale(self) -> None:
        """F3 relit ses brouillons : pause, abandon et application la préviennent."""
        self.controleur.commenter("Un ajout ne change pas la liste des brouillons")
        self.assertEqual(self.principal.signaux, 0)
        self.controleur.mettreEnPause("")
        self.assertEqual(self.principal.signaux, 1)
        edition = self.ouvrir(self.client.ouvrirBrouillonEdition(6))
        edition.appliquer("Texte ajouté")
        self.assertEqual(self.principal.signaux, 2)

    # ------------------------------------------------------------------ dépendances

    def testSansTkinterNiModele(self) -> None:
        """Le contrôleur reste testable dans le CI, qui n'a pas d'écran, et ne charge du
        modèle que les exceptions et les énumérations."""
        code = (
            "import sys, ihm.controleurs.controleur_edition; "
            "interdits = ('tkinter', 'flask', 'api', 'acteurs', 'sessions', 'commandes', "
            "'etats', 'description', 'persistance', 'modele.ticket', 'modele.systeme_tickets'); "
            "print(sorted(m for m in sys.modules if m.split('.')[0] in interdits "
            "or m in interdits))"
        )
        resultat = subprocess.run(
            [sys.executable, "-c", code],
            cwd=racineDepot, capture_output=True, text=True, check=True,
        )
        self.assertEqual(resultat.stdout.strip(), "[]")


if __name__ == "__main__":
    unittest.main()
