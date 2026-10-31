"""Tests d'intégration sans fenêtre : sessions, patron Observateur et persistance JSON."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from acteurs.user import User
from modele.enums import Priorite
from modele.observateur import ObservateurTickets
from modele.systeme_tickets import SystemeTickets
from modele.ticket import Ticket
from persistance.depot_json import DepotJSON


class Espion(ObservateurTickets):
    """Observateur espion : note, dans l'ordre, chaque notification reçue."""

    def __init__(self) -> None:
        self._evenements: list[tuple[str, Ticket]] = []

    @property
    def evenements(self) -> list[tuple[str, Ticket]]:
        return list(self._evenements)

    def ticketModifie(self, ticket: Ticket) -> None:
        self._evenements.append(("ticketModifie", ticket))

    def ticketAjoute(self, ticket: Ticket) -> None:
        self._evenements.append(("ticketAjoute", ticket))

    def ticketRetire(self, ticket: Ticket) -> None:
        self._evenements.append(("ticketRetire", ticket))


class TestCreationEtObservateur(unittest.TestCase):
    """Une session de création ne notifie rien avant appliquer()."""

    def setUp(self) -> None:
        self._systeme: SystemeTickets = SystemeTickets()
        self._user: User = User(1, "Abdoul Razack", "abdoul.razack@uqac.ca", self._systeme)
        self._espion: Espion = Espion()
        self._systeme.abonner(self._espion)
        self._ticket: Ticket = Ticket(1, "Bug de connexion", Priorite.HAUTE)

    def testAucunEvenementAvantAppliquerPuisAjoutEnPremier(self) -> None:
        session = self._user.ouvrirSessionCreation(self._ticket)
        session.ajouterTexteSaisi("Le bouton « Se connecter » ne réagit pas.")
        session.ajouterCommentaire("Reproduit sur Chrome.")
        self.assertEqual(self._espion.evenements, [])
        self.assertFalse(self._systeme.contient(self._ticket))

        rapport = session.appliquer()
        self.assertEqual(rapport.nombreSucces, 2)
        self.assertEqual(
            self._espion.evenements,
            [
                ("ticketAjoute", self._ticket),
                ("ticketModifie", self._ticket),
                ("ticketModifie", self._ticket),
            ],
        )

    def testCreationAbandonneeSansEvenement(self) -> None:
        session = self._user.ouvrirSessionCreation(self._ticket)
        session.ajouterTexteSaisi("Description jamais appliquée.")
        session.abandonner()
        self.assertEqual(self._espion.evenements, [])
        self.assertFalse(self._systeme.contient(self._ticket))


class TestSessionNonSauvegardee(unittest.TestCase):
    """Les brouillons (sessions non appliquées) ne sont pas sauvegardés."""

    def setUp(self) -> None:
        self._systeme: SystemeTickets = SystemeTickets()
        self._user: User = User(1, "Abdoul Razack", "abdoul.razack@uqac.ca", self._systeme)
        self._ticket: Ticket = Ticket(1, "Bug de connexion", Priorite.HAUTE)
        self._user.createTicket(self._ticket)

    def _sauvegarderPuisCharger(self) -> SystemeTickets:
        with tempfile.TemporaryDirectory() as dossier:
            depot = DepotJSON(Path(dossier) / "sauvegarde.json")
            depot.sauvegarder(self._systeme)
            return depot.charger()

    def testSessionEditionEnPauseNonSauvegardee(self) -> None:
        session = self._user.ouvrirSessionEdition(self._ticket)
        session.ajouterCommentaire("Commentaire resté en attente")
        session.mettreEnPause()

        recharge = self._sauvegarderPuisCharger()
        ticketsRecharges = {t.ticketID: t for t in recharge.tickets}
        self.assertEqual(ticketsRecharges[1].comments, [])
        createurRecharge = recharge.utilisateurParId(1)
        self.assertIsNotNone(createurRecharge)
        self.assertEqual(createurRecharge.sessionsOuvertes, [])
        # La sauvegarde n'a pas touché à la session d'origine.
        self.assertEqual(self._user.sessionsOuvertes, [session])
        self.assertTrue(session.estEnPause)

    def testCreationNonAppliqueeAbsenteDuFichier(self) -> None:
        brouillon = Ticket(2, "Ticket en cours de création", Priorite.BASSE)
        session = self._user.ouvrirSessionCreation(brouillon)
        session.ajouterTexteSaisi("Description jamais appliquée.")

        recharge = self._sauvegarderPuisCharger()
        self.assertEqual([t.ticketID for t in recharge.tickets], [1])
