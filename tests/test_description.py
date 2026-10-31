from __future__ import annotations

import unittest
from pathlib import Path
from typing import TYPE_CHECKING

from acteurs.user import User
from description.fabrique_description import FabriqueDescription
from modele.enums import Priorite
from modele.exceptions import ArtefactInvalideException
from modele.systeme_tickets import SystemeTickets
from modele.ticket import Ticket

if TYPE_CHECKING:
    from sessions.session_edition import SessionEdition

dossierRessources = Path(__file__).resolve().parent.parent / "ressources"


class TestDescription(unittest.TestCase):
    """Propriétés typeArtefact et contenu des éléments de description."""

    def testTypeArtefactDesTroisTypes(self) -> None:
        for typeArtefact, fichier in (
            ("texte", "description_bug.txt"),
            ("image", "capture_ecran.png"),
            ("video", "demo_bug.mp4"),
        ):
            with self.subTest(typeArtefact=typeArtefact):
                element = FabriqueDescription.creer(typeArtefact, str(dossierRessources / fichier))
                element.traiter()
                self.assertEqual(element.typeArtefact, typeArtefact)

    def testContenuDuTexte(self) -> None:
        chemin = dossierRessources / "description_bug.txt"
        element = FabriqueDescription.creer("texte", str(chemin))
        element.traiter()
        self.assertEqual(element.contenu, chemin.read_text(encoding="utf-8"))

    def testTexteSaisi(self) -> None:
        texte = "Le bouton « Se connecter » ne réagit pas."
        element = FabriqueDescription.creerSaisie(texte)
        element.traiter()
        self.assertEqual(element.resume, f"[Texte] texte saisi ({len(texte)} caractères)")
        self.assertEqual(element.chemin, "")
        self.assertEqual(element.contenu, texte)
        self.assertEqual(element.typeArtefact, "texte")

    def testTexteSaisiBlancRefuse(self) -> None:
        for texte in ("", "   ", " \n\t "):
            with self.subTest(texte=texte):
                element = FabriqueDescription.creerSaisie(texte)
                with self.assertRaises(ArtefactInvalideException) as contexte:
                    element.traiter()
                self.assertEqual(str(contexte.exception), "Texte saisi vide")


class TestTexteSaisiEnSession(unittest.TestCase):
    """ajouterTexteSaisi() dans une session d'édition."""

    def setUp(self) -> None:
        systeme = SystemeTickets()
        createur = User(1, "Abdoul Razack", "abdoul.razack@uqac.ca", systeme)
        self._ticket: Ticket = Ticket(1, "Bug de connexion", Priorite.HAUTE)
        createur.createTicket(self._ticket)
        self._session: SessionEdition = createur.ouvrirSessionEdition(self._ticket)

    def testAjouterTexteSaisiPuisAppliquer(self) -> None:
        texte = "Étapes : saisir des identifiants valides, cliquer sur « Se connecter »."
        self._session.ajouterTexteSaisi(texte)
        self.assertEqual(self._ticket.description.nombreElements, 0)
        rapport = self._session.appliquer()
        self.assertEqual(rapport.nombreSucces, 1)
        elements = self._ticket.description.elements
        self.assertEqual(len(elements), 1)
        self.assertEqual(elements[0].contenu, texte)

    def testTexteVideRefuseSansModifierLaPile(self) -> None:
        self._session.ajouterCommentaire("Commentaire déjà en attente")
        avant = self._session.modificationsEnAttente
        with self.assertRaises(ArtefactInvalideException):
            self._session.ajouterTexteSaisi("   ")
        self.assertEqual(self._session.modificationsEnAttente, avant)
