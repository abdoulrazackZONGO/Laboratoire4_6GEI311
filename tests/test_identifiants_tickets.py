"""Tests de l'étape 1 du lab 4 : ticketParId(), reserverIdentifiant() et unicité des identifiants.

Lancer depuis la racine du dépôt :  python -m unittest discover -s tests -t . -v
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from acteurs.user import User
from modele.enums import Priorite
from modele.observateur import ObservateurTickets
from modele.systeme_tickets import SystemeTickets
from modele.ticket import Ticket
from persistance.depot_json import DepotJSON, PersistanceException


class ObservateurAjouts(ObservateurTickets):
    """Compte les notifications d'ajout reçues."""

    def __init__(self) -> None:
        self.ajouts: int = 0

    def ticketAjoute(self, ticket: Ticket) -> None:
        self.ajouts += 1


class TestTicketParId(unittest.TestCase):
    def setUp(self) -> None:
        self.systeme = SystemeTickets()
        self.createur = User(1, "Createur", "createur@uqac.ca", self.systeme)
        self.t1 = Ticket(1, "T1", Priorite.MOYENNE)
        self.t5 = Ticket(5, "T5", Priorite.HAUTE)
        for ticket in (self.t1, self.t5):
            self.createur.createTicket(ticket)

    def test_retrouve_un_ticket_du_depot(self) -> None:
        self.assertIs(self.systeme.ticketParId(5), self.t5)
        self.assertIs(self.systeme.ticketParId(1), self.t1)

    def test_identifiant_inconnu(self) -> None:
        self.assertIsNone(self.systeme.ticketParId(2))

    def test_ticket_retire(self) -> None:
        self.createur.supprimerTicket(self.t5)
        self.assertIsNone(self.systeme.ticketParId(5))

    def test_ignore_une_creation_non_appliquee(self) -> None:
        """Le ticket d'une session de création n'entre dans le dépôt qu'à appliquer()."""
        brouillon = Ticket(self.systeme.reserverIdentifiant(), "Brouillon", Priorite.BASSE)
        session = self.createur.ouvrirSessionCreation(brouillon)
        self.assertIsNone(self.systeme.ticketParId(brouillon.ticketID))
        session.appliquer()
        self.assertIs(self.systeme.ticketParId(brouillon.ticketID), brouillon)


class TestReserverIdentifiant(unittest.TestCase):
    def setUp(self) -> None:
        self.systeme = SystemeTickets()
        self.createur = User(1, "Createur", "createur@uqac.ca", self.systeme)

    def test_depot_vide(self) -> None:
        self.assertEqual(self.systeme.reserverIdentifiant(), 1)

    def test_part_du_plus_grand_identifiant(self) -> None:
        """Avec les tickets 1 et 5, on obtient 6 : le nombre de tickets ne compte pas."""
        for identifiant in (1, 5):
            self.createur.createTicket(Ticket(identifiant, f"T{identifiant}", Priorite.BASSE))
        self.assertEqual(self.systeme.reserverIdentifiant(), 6)

    def test_reservations_successives_distinctes(self) -> None:
        premier = self.systeme.reserverIdentifiant()
        second = self.systeme.reserverIdentifiant()
        self.assertGreater(second, premier)

    def test_apres_ajout_du_ticket_reserve(self) -> None:
        identifiant = self.systeme.reserverIdentifiant()
        self.createur.createTicket(Ticket(identifiant, "Nouveau", Priorite.BASSE))
        self.assertGreater(self.systeme.reserverIdentifiant(), identifiant)

    def test_identifiant_explicite_plus_grand(self) -> None:
        """Un ticket ajouté avec son propre numéro (main.py, DepotJSON) est pris en compte."""
        self.systeme.reserverIdentifiant()
        self.createur.createTicket(Ticket(10, "T10", Priorite.BASSE))
        self.assertEqual(self.systeme.reserverIdentifiant(), 11)

    def test_identifiant_retire_non_redonne(self) -> None:
        """Sinon, un client qui compare par identifiant prendrait le nouveau ticket pour l'ancien."""
        t3 = Ticket(3, "T3", Priorite.BASSE)
        self.createur.createTicket(t3)
        self.createur.supprimerTicket(t3)
        self.assertEqual(self.systeme.reserverIdentifiant(), 4)


class TestUniciteIdentifiants(unittest.TestCase):
    def setUp(self) -> None:
        self.systeme = SystemeTickets()
        self.t3 = Ticket(3, "Bug de connexion", Priorite.HAUTE)
        self.systeme.ajouterTicket(self.t3)
        self.observateur = ObservateurAjouts()
        self.systeme.abonner(self.observateur)

    def test_autre_ticket_meme_identifiant(self) -> None:
        doublon = Ticket(3, "Doublon", Priorite.BASSE)
        with self.assertRaises(ValueError) as contexte:
            self.systeme.ajouterTicket(doublon)
        self.assertIn("3", str(contexte.exception))
        self.assertIn("Bug de connexion", str(contexte.exception))
        self.assertEqual(self.systeme.tickets, [self.t3])
        self.assertEqual(self.observateur.ajouts, 0)

    def test_meme_ticket_deux_fois(self) -> None:
        with self.assertRaises(ValueError):
            self.systeme.ajouterTicket(self.t3)
        self.assertEqual(self.systeme.tickets, [self.t3])
        self.assertEqual(self.observateur.ajouts, 0)

    def test_fichier_avec_identifiants_en_double(self) -> None:
        """DepotJSON convertit déjà ValueError en PersistanceException : fichier incohérent."""
        ticketDict = {
            "ticketID": 1, "title": "T1", "priority": "BASSE", "status": "OUVERT",
            "creationDate": "2026-10-20", "updateDate": "2026-10-20",
            "creator": 1, "assignedUser": None, "aDejaEteAssigne": False,
            "comments": [], "description": [],
        }
        donnees = {
            "version": DepotJSON.VERSION,
            "utilisateurs": [
                {"id": 1, "name": "Createur", "email": "createur@uqac.ca", "role": "User"}
            ],
            "tickets": [ticketDict, dict(ticketDict, title="T1 bis")],
        }
        with tempfile.TemporaryDirectory() as dossier:
            chemin = Path(dossier) / "doublons.json"
            chemin.write_text(json.dumps(donnees), encoding="utf-8")
            with self.assertRaises(PersistanceException):
                DepotJSON(chemin).charger()


class TestCreationsSimultanees(unittest.TestCase):
    def test_deux_creations_ouvertes_en_meme_temps(self) -> None:
        """Deux brouillons de création ouverts ensemble s'appliquent sans conflit d'identifiant."""
        systeme = SystemeTickets()
        abdoul = User(2, "Abdoul Razack", "abdoul.razack@uqac.ca", systeme)
        julien = User(3, "T Julien", "t.julien@uqac.ca", systeme)
        premier = Ticket(systeme.reserverIdentifiant(), "Premier", Priorite.HAUTE)
        second = Ticket(systeme.reserverIdentifiant(), "Second", Priorite.BASSE)
        sessionPremier = abdoul.ouvrirSessionCreation(premier)
        sessionSecond = julien.ouvrirSessionCreation(second)
        sessionSecond.appliquer()
        sessionPremier.appliquer()
        self.assertNotEqual(premier.ticketID, second.ticketID)
        self.assertEqual(
            sorted(t.ticketID for t in systeme.tickets), sorted([premier.ticketID, second.ticketID])
        )


if __name__ == "__main__":
    unittest.main()
