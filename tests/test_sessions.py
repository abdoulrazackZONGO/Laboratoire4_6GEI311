from __future__ import annotations

import unittest
from pathlib import Path
from typing import TYPE_CHECKING

from acteurs.user import User
from modele.enums import Priorite
from modele.exceptions import AccesRefuseException, SessionIndisponibleException
from modele.systeme_tickets import SystemeTickets
from modele.ticket import Ticket
from sessions.lot_admin import LotAdmin

if TYPE_CHECKING:
    from modele.enums import Statut
    from sessions.session_creation import SessionCreation
    from sessions.session_edition import SessionEdition

dossierRessources = Path(__file__).resolve().parent.parent / "ressources"


def instantane(ticket: Ticket) -> tuple[Statut, str | None, int, int]:
    """Statut, assigné, nombre de commentaires et d'éléments du ticket."""
    assigne = ticket.assignedUser.name if ticket.assignedUser is not None else None
    return (ticket.status, assigne, len(ticket.comments), ticket.description.nombreElements)


class TestAbandonSession(unittest.TestCase):
    """abandonner() renonce à toute la session d'édition avant application."""

    def setUp(self) -> None:
        systeme = SystemeTickets()
        createur = User(1, "Abdoul Razack", "abdoul.razack@uqac.ca", systeme)
        self._ticket: Ticket = Ticket(1, "Bug de connexion", Priorite.HAUTE)
        createur.createTicket(self._ticket)
        self._session: SessionEdition = createur.ouvrirSessionEdition(self._ticket)

    def testTicketInchangeApresAbandon(self) -> None:
        avant = instantane(self._ticket)
        self._session.ajouterCommentaire("Le bug se reproduit sur Chrome.")
        self._session.ajouterTexteSaisi("Étapes pour reproduire le bug.")
        self.assertTrue(self._session.estOuverte)
        self._session.abandonner()
        self.assertEqual(instantane(self._ticket), avant)
        self.assertEqual(self._session.modificationsEnAttente, [])
        self.assertFalse(self._session.estOuverte)

    def testAbandonPossibleEnPause(self) -> None:
        self._session.ajouterCommentaire("Commentaire en attente")
        self._session.mettreEnPause()
        self._session.abandonner()
        self.assertFalse(self._session.estEnPause)
        self.assertFalse(self._session.estOuverte)
        self.assertEqual(self._session.modificationsEnAttente, [])

    def testOperationsRefuseesApresAbandon(self) -> None:
        self._session.abandonner()
        for operation, action in (
            ("ajout", lambda: self._session.ajouterCommentaire("Ajout après abandon")),
            ("ajout", lambda: self._session.ajouterTexteSaisi("Texte après abandon")),
            ("annulation", self._session.annulerDerniere),
            ("mise en pause", self._session.mettreEnPause),
            ("reprise", self._session.reprendre),
            ("application", self._session.appliquer),
        ):
            with self.subTest(operation=operation):
                with self.assertRaises(SessionIndisponibleException) as contexte:
                    action()
                self.assertEqual(
                    str(contexte.exception),
                    f"Session d'édition abandonnée : {operation} impossible",
                )

    def testAbandonRefuseApresAppliquer(self) -> None:
        self._session.ajouterCommentaire("Commentaire appliqué")
        self._session.appliquer()
        self.assertFalse(self._session.estOuverte)
        with self.assertRaises(SessionIndisponibleException):
            self._session.abandonner()
        self.assertEqual(len(self._ticket.comments), 1)

    def testAbandonRefuseEnDouble(self) -> None:
        self._session.abandonner()
        with self.assertRaises(SessionIndisponibleException):
            self._session.abandonner()

    def testLotAdminSansAbandonner(self) -> None:
        self.assertFalse(hasattr(LotAdmin, "abandonner"))


class TestSessionCreation(unittest.TestCase):
    """Le ticket n'entre dans le dépôt qu'à l'application de la session de création."""

    def setUp(self) -> None:
        self._systeme: SystemeTickets = SystemeTickets()
        self._createur: User = User(1, "Abdoul Razack", "abdoul.razack@uqac.ca", self._systeme)
        self._ticket: Ticket = Ticket(10, "Nouveau ticket", Priorite.MOYENNE)
        self._session: SessionCreation = self._createur.ouvrirSessionCreation(self._ticket)

    def testTicketAbsentAvantAppliquer(self) -> None:
        self._session.ajouterCommentaire("Premier commentaire")
        self._session.ajouterTexteSaisi("Description saisie du problème.")
        self.assertEqual(self._session.libelle, "Session de création")
        self.assertFalse(self._systeme.contient(self._ticket))
        self.assertIsNone(self._ticket.creator)

    def testTicketPresentApresAppliquer(self) -> None:
        self._session.ajouterCommentaire("Premier commentaire")
        self._session.ajouterTexteSaisi("Description saisie du problème.")
        self._session.ajouterElement("image", str(dossierRessources / "capture_ecran.png"))
        rapport = self._session.appliquer()
        self.assertEqual((rapport.nombreSucces, rapport.nombreRefus), (3, 0))
        self.assertTrue(self._systeme.contient(self._ticket))
        self.assertIs(self._ticket.creator, self._createur)
        self.assertEqual(len(self._ticket.comments), 1)
        self.assertEqual(self._ticket.description.nombreElements, 2)
        self.assertEqual(self._createur.mesTickets(), [self._ticket])

    def testAppliquerEnPauseRefuse(self) -> None:
        self._session.ajouterTexteSaisi("Description saisie du problème.")
        self._session.mettreEnPause()
        with self.assertRaises(SessionIndisponibleException) as contexte:
            self._session.appliquer()
        self.assertEqual(
            str(contexte.exception), "Session de création en pause : application impossible"
        )
        self.assertFalse(self._systeme.contient(self._ticket))
        self.assertIsNone(self._ticket.creator)

    def testAppliquerEnDoubleRefuse(self) -> None:
        self._session.appliquer()
        with self.assertRaises(SessionIndisponibleException):
            self._session.appliquer()
        self.assertEqual(self._systeme.tickets, [self._ticket])

    def testAbandonTicketJamaisDansLeDepot(self) -> None:
        self._session.ajouterTexteSaisi("Description saisie du problème.")
        self._session.abandonner()
        self.assertFalse(self._systeme.contient(self._ticket))
        self.assertIsNone(self._ticket.creator)
        with self.assertRaises(SessionIndisponibleException):
            self._session.appliquer()
        self.assertFalse(self._systeme.contient(self._ticket))
        self.assertIsNone(self._ticket.creator)

    def testOuvrirSessionCreationSurTicketExistantRefusee(self) -> None:
        dejaCree = Ticket(20, "Ticket déjà créé", Priorite.BASSE)
        self._createur.createTicket(dejaCree)
        creePuisSupprime = Ticket(21, "Ticket créé puis supprimé", Priorite.BASSE)
        self._createur.createTicket(creePuisSupprime)
        self._createur.supprimerTicket(creePuisSupprime)
        deposeSansCreateur = Ticket(22, "Ticket déposé sans créateur", Priorite.BASSE)
        self._systeme.ajouterTicket(deposeSansCreateur)
        for ticket in (dejaCree, creePuisSupprime, deposeSansCreateur):
            with self.subTest(ticket=ticket.title):
                with self.assertRaises(AccesRefuseException):
                    self._createur.ouvrirSessionCreation(ticket)


class TestUneSessionParTicket(unittest.TestCase):
    """Un utilisateur n'a qu'une session ouverte à la fois sur un même ticket."""

    def setUp(self) -> None:
        self._systeme: SystemeTickets = SystemeTickets()
        self._createur: User = User(1, "Abdoul Razack", "abdoul.razack@uqac.ca", self._systeme)
        self._ticket: Ticket = Ticket(1, "Bug de connexion", Priorite.HAUTE)
        self._createur.createTicket(self._ticket)

    def testSecondeSessionRefusee(self) -> None:
        premiere = self._createur.ouvrirSessionEdition(self._ticket)
        with self.assertRaises(SessionIndisponibleException):
            self._createur.ouvrirSessionEdition(self._ticket)
        self.assertIs(self._createur.sessionEnCours(self._ticket), premiere)

    def testSecondeCreationRefusee(self) -> None:
        nouveau = Ticket(2, "Nouveau ticket", Priorite.BASSE)
        premiere = self._createur.ouvrirSessionCreation(nouveau)
        with self.assertRaises(SessionIndisponibleException):
            self._createur.ouvrirSessionCreation(nouveau)
        self.assertIs(self._createur.sessionEnCours(nouveau), premiere)

    def testNouvelleSessionApresAbandon(self) -> None:
        premiere = self._createur.ouvrirSessionEdition(self._ticket)
        premiere.abandonner()
        self.assertIsNone(self._createur.sessionEnCours(self._ticket))
        seconde = self._createur.ouvrirSessionEdition(self._ticket)
        self.assertIsNot(seconde, premiere)
        self.assertIs(self._createur.sessionEnCours(self._ticket), seconde)

    def testNouvelleSessionApresAppliquer(self) -> None:
        premiere = self._createur.ouvrirSessionEdition(self._ticket)
        premiere.ajouterCommentaire("Commentaire appliqué")
        premiere.appliquer()
        self.assertIsNone(self._createur.sessionEnCours(self._ticket))
        seconde = self._createur.ouvrirSessionEdition(self._ticket)
        self.assertIs(self._createur.sessionEnCours(self._ticket), seconde)

    def testSessionEnPauseRetournee(self) -> None:
        session = self._createur.ouvrirSessionEdition(self._ticket)
        session.mettreEnPause()
        self.assertIs(self._createur.sessionEnCours(self._ticket), session)
        with self.assertRaises(SessionIndisponibleException):
            self._createur.ouvrirSessionEdition(self._ticket)

    def testSessionEnCoursSansSession(self) -> None:
        self.assertIsNone(self._createur.sessionEnCours(self._ticket))

    def testCreateurVerifieAvantSessionOuverte(self) -> None:
        self._createur.ouvrirSessionEdition(self._ticket)
        autre = User(2, "T Julien", "t.julien@uqac.ca", self._systeme)
        with self.assertRaises(AccesRefuseException):
            autre.ouvrirSessionEdition(self._ticket)

    def testSessionsOuvertesCompteCreationsEtEditions(self) -> None:
        self.assertEqual(self._createur.sessionsOuvertes, [])
        edition = self._createur.ouvrirSessionEdition(self._ticket)
        creation = self._createur.ouvrirSessionCreation(Ticket(2, "Nouveau ticket", Priorite.BASSE))
        self.assertEqual(self._createur.sessionsOuvertes, [edition, creation])
        creation.abandonner()
        self.assertEqual(self._createur.sessionsOuvertes, [edition])
        edition.appliquer()
        self.assertEqual(self._createur.sessionsOuvertes, [])


class TestTicketDeLaSession(unittest.TestCase):
    """session.ticket est le ticket passé à l'ouverture de la session."""

    def setUp(self) -> None:
        self._systeme: SystemeTickets = SystemeTickets()
        self._createur: User = User(1, "Abdoul Razack", "abdoul.razack@uqac.ca", self._systeme)

    def testTicketDeLaSessionEdition(self) -> None:
        ticket = Ticket(1, "Bug de connexion", Priorite.HAUTE)
        self._createur.createTicket(ticket)
        session = self._createur.ouvrirSessionEdition(ticket)
        self.assertIs(session.ticket, ticket)

    def testTicketDeLaSessionCreation(self) -> None:
        existant = Ticket(1, "Bug de connexion", Priorite.HAUTE)
        self._createur.createTicket(existant)
        self._createur.ouvrirSessionEdition(existant)
        nouveau = Ticket(2, "Nouveau ticket", Priorite.BASSE)
        creation = self._createur.ouvrirSessionCreation(nouveau)
        self.assertIs(creation.ticket, nouveau)
        # Usage visé par l'interface : les brouillons de création sont les sessions
        # ouvertes dont le ticket n'est pas encore dans le dépôt.
        brouillons = [
            s for s in self._createur.sessionsOuvertes if not self._systeme.contient(s.ticket)
        ]
        self.assertEqual(brouillons, [creation])

    def testTicketEnLectureSeule(self) -> None:
        ticket = Ticket(1, "Bug de connexion", Priorite.HAUTE)
        self._createur.createTicket(ticket)
        session = self._createur.ouvrirSessionEdition(ticket)
        with self.assertRaises(AttributeError):
            session.ticket = Ticket(2, "Autre ticket", Priorite.BASSE)
        self.assertIs(session.ticket, ticket)
