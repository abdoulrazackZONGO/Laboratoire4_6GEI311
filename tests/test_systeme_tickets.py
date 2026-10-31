"""Tests de M1 : SystemeTickets.ticketsAssignesA().

Lancer depuis la racine du dépôt :  python -m unittest discover -s tests -v
"""
from __future__ import annotations

import unittest

from acteurs.admin import Admin
from acteurs.user import User
from modele.enums import Priorite, Statut
from modele.systeme_tickets import SystemeTickets
from modele.ticket import Ticket


class TestTicketsAssignesA(unittest.TestCase):
    def setUp(self) -> None:
        self.systeme = SystemeTickets()
        self.admin = Admin(1, "Admin", "admin@uqac.ca", self.systeme)
        self.createur = User(2, "Createur", "createur@uqac.ca", self.systeme)
        self.dev = User(3, "Dev", "dev@uqac.ca", self.systeme)
        self.autre = User(4, "Autre", "autre@uqac.ca", self.systeme)
        self.t1 = Ticket(1, "T1", Priorite.MOYENNE)
        self.t2 = Ticket(2, "T2", Priorite.MOYENNE)
        self.t3 = Ticket(3, "T3", Priorite.MOYENNE)
        # Ajout direct au dépôt : le test ne dépend pas du mode de création (sessions).
        for ticket in (self.t1, self.t2, self.t3):
            ticket.definirCreateur(self.createur)
            self.systeme.ajouterTicket(ticket)

    def test_aucun_ticket_assigne(self) -> None:
        self.assertEqual(self.systeme.ticketsAssignesA(self.dev), [])

    def test_seulement_les_tickets_assignes(self) -> None:
        self.admin.assignTicket(self.t1, self.dev)
        self.admin.assignTicket(self.t2, self.autre)
        self.admin.assignTicket(self.t3, self.dev)
        self.assertEqual(self.systeme.ticketsAssignesA(self.dev), [self.t1, self.t3])
        self.assertEqual(self.systeme.ticketsAssignesA(self.autre), [self.t2])

    def test_distinct_des_tickets_crees(self) -> None:
        """Le créateur voit ses tickets via ticketsDe(), pas via ticketsAssignesA()."""
        self.admin.assignTicket(self.t1, self.dev)
        self.assertEqual(self.systeme.ticketsDe(self.createur), [self.t1, self.t2, self.t3])
        self.assertEqual(self.systeme.ticketsAssignesA(self.createur), [])

    def test_desassignation(self) -> None:
        self.admin.assignTicket(self.t1, self.dev)
        self.admin.desassignerTicket(self.t1)
        self.assertEqual(self.systeme.ticketsAssignesA(self.dev), [])

    def test_reassignation(self) -> None:
        self.admin.assignTicket(self.t1, self.dev)
        self.admin.assignTicket(self.t1, self.autre)
        self.assertEqual(self.systeme.ticketsAssignesA(self.dev), [])
        self.assertEqual(self.systeme.ticketsAssignesA(self.autre), [self.t1])

    def test_conserve_apres_validation(self) -> None:
        """Choix documenté : l'assigné reste visible sur un ticket TERMINE (traçabilité)."""
        self.admin.assignTicket(self.t1, self.dev)
        self.t1.updateStatus(Statut.VALIDATION)
        self.admin.validerTicket(self.t1)
        self.assertIs(self.t1.status, Statut.TERMINE)
        self.assertEqual(self.systeme.ticketsAssignesA(self.dev), [self.t1])

    def test_retourne_une_copie(self) -> None:
        self.admin.assignTicket(self.t1, self.dev)
        self.systeme.ticketsAssignesA(self.dev).clear()
        self.assertEqual(self.systeme.ticketsAssignesA(self.dev), [self.t1])


if __name__ == "__main__":
    unittest.main()
