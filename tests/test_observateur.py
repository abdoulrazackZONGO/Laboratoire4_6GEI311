"""Tests de M8 : patron Observateur (sujets, relais du dépôt, notifications).

Lancer depuis la racine du dépôt :  python -m unittest discover -s tests -v
"""
from __future__ import annotations

import unittest
from pathlib import Path

from acteurs.admin import Admin
from acteurs.user import User
from commandes.commande_ajouter_element import CommandeAjouterElement
from description.fabrique_description import FabriqueDescription
from modele.enums import Priorite, Statut
from modele.exceptions import TransitionInvalideException
from modele.observateur import ObservateurTickets
from modele.systeme_tickets import SystemeTickets
from modele.ticket import Ticket

FICHIER_TEXTE = Path(__file__).resolve().parent.parent / "ressources" / "description_bug.txt"


def elementTexte():
    element = FabriqueDescription.creer("texte", str(FICHIER_TEXTE))
    element.traiter()
    return element


class Espion(ObservateurTickets):
    """Observateur de test : enregistre chaque notification reçue."""

    def __init__(self) -> None:
        self.evenements: list[tuple[str, Ticket]] = []

    def ticketModifie(self, ticket: Ticket) -> None:
        self.evenements.append(("modifie", ticket))

    def ticketAjoute(self, ticket: Ticket) -> None:
        self.evenements.append(("ajoute", ticket))

    def ticketRetire(self, ticket: Ticket) -> None:
        self.evenements.append(("retire", ticket))


class TestTicketSujet(unittest.TestCase):
    """Un ticket prévient ses abonnés à chaque modification, et seulement alors."""

    def setUp(self) -> None:
        self.systeme = SystemeTickets()
        self.admin = Admin(1, "Admin", "admin@uqac.ca", self.systeme)
        self.dev = User(2, "Dev", "dev@uqac.ca", self.systeme)
        self.ticket = Ticket(1, "T1", Priorite.HAUTE)
        self.espion = Espion()
        self.ticket.abonner(self.espion)

    def test_changement_d_etat(self) -> None:
        self.admin.closeTicket(self.ticket)
        self.assertEqual(self.espion.evenements, [("modifie", self.ticket)])

    def test_assignation(self) -> None:
        self.admin.assignTicket(self.ticket, self.dev)
        self.assertTrue(self.espion.evenements)
        self.assertTrue(all(evt == ("modifie", self.ticket) for evt in self.espion.evenements))

    def test_desassignation(self) -> None:
        self.admin.assignTicket(self.ticket, self.dev)
        self.espion.evenements.clear()
        self.admin.desassignerTicket(self.ticket)
        self.assertTrue(self.espion.evenements)

    def test_commentaire(self) -> None:
        self.ticket.addComment("Reproduit sur Chrome", self.dev)
        self.assertEqual(self.espion.evenements, [("modifie", self.ticket)])

    def test_element_de_description(self) -> None:
        self.ticket.ajouterElementDescription(elementTexte())
        self.assertEqual(self.ticket.description.nombreElements, 1)
        self.assertEqual(self.espion.evenements, [("modifie", self.ticket)])

    def test_commande_ajouter_element_notifie(self) -> None:
        """La commande passe désormais par le ticket : l'ajout est notifié."""
        CommandeAjouterElement(self.ticket, elementTexte()).executer()
        self.assertEqual(self.espion.evenements, [("modifie", self.ticket)])

    def test_transition_refusee_ne_notifie_pas(self) -> None:
        with self.assertRaises(TransitionInvalideException):
            self.admin.validerTicket(self.ticket)  # OUVERT -> TERMINE est interdit
        self.assertEqual(self.espion.evenements, [])

    def test_abonnement_idempotent(self) -> None:
        self.ticket.abonner(self.espion)
        self.assertEqual(self.ticket.nombreObservateurs, 1)
        self.ticket.addComment("x", self.dev)
        self.assertEqual(len(self.espion.evenements), 1)

    def test_desabonnement(self) -> None:
        self.ticket.desabonner(self.espion)
        self.ticket.desabonner(self.espion)  # deuxième fois : sans effet ni erreur
        self.ticket.addComment("x", self.dev)
        self.assertEqual(self.espion.evenements, [])
        self.assertEqual(self.ticket.nombreObservateurs, 0)

    def test_desabonnement_pendant_la_notification(self) -> None:
        """Un observateur qui se retire en cours de notification ne fait sauter personne."""
        sujet = self.ticket

        class Ephemere(Espion):
            def ticketModifie(self, ticket: Ticket) -> None:
                super().ticketModifie(ticket)
                sujet.desabonner(self)

        ephemere = Ephemere()
        sujet.abonner(ephemere)
        sujet.addComment("premier", self.dev)
        sujet.addComment("second", self.dev)
        self.assertEqual(len(ephemere.evenements), 1)
        self.assertEqual(len(self.espion.evenements), 2)


class TestSystemeRelais(unittest.TestCase):
    """Le dépôt annonce les ajouts et retraits, et relaie les modifications de ses tickets."""

    def setUp(self) -> None:
        self.systeme = SystemeTickets()
        self.admin = Admin(1, "Admin", "admin@uqac.ca", self.systeme)
        self.dev = User(2, "Dev", "dev@uqac.ca", self.systeme)
        self.liste = Espion()  # joue le rôle d'une fenêtre de liste
        self.systeme.abonner(self.liste)
        self.ticket = Ticket(1, "T1", Priorite.BASSE)

    def test_ajout(self) -> None:
        self.systeme.ajouterTicket(self.ticket)
        self.assertEqual(self.liste.evenements, [("ajoute", self.ticket)])

    def test_relais_des_modifications(self) -> None:
        self.systeme.ajouterTicket(self.ticket)
        self.liste.evenements.clear()
        self.ticket.addComment("relayé", self.dev)
        self.assertEqual(self.liste.evenements, [("modifie", self.ticket)])

    def test_retrait_coupe_le_relais(self) -> None:
        self.systeme.ajouterTicket(self.ticket)
        self.systeme.retirerTicket(self.ticket)
        self.assertEqual(self.liste.evenements[-1], ("retire", self.ticket))
        self.assertEqual(self.ticket.nombreObservateurs, 0)
        self.liste.evenements.clear()
        self.ticket.addComment("hors dépôt", self.dev)
        self.assertEqual(self.liste.evenements, [])

    def test_ticket_hors_depot_non_relaye(self) -> None:
        self.ticket.abonner(self.systeme)  # abonnement forcé, sans ajout au dépôt
        self.ticket.addComment("x", self.dev)
        self.assertEqual(self.liste.evenements, [])

    def test_liste_et_detail_abonnes_ensemble(self) -> None:
        """Une fenêtre de détail (abonnée au ticket) et une liste (abonnée au dépôt)."""
        detail = Espion()
        self.systeme.ajouterTicket(self.ticket)
        self.ticket.abonner(detail)
        self.liste.evenements.clear()
        self.admin.closeTicket(self.ticket)
        self.assertEqual(detail.evenements, [("modifie", self.ticket)])
        self.assertEqual(self.liste.evenements, [("modifie", self.ticket)])

    def test_creation_par_un_utilisateur(self) -> None:
        """createTicket() passe par ajouterTicket() : la liste est prévenue."""
        self.dev.createTicket(self.ticket)
        self.assertIn(("ajoute", self.ticket), self.liste.evenements)


if __name__ == "__main__":
    unittest.main()
