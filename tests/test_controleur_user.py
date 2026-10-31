"""Tests de ControleurUser, sans fenêtre : un faux principal remplace ControleurPrincipal."""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

from acteurs.admin import Admin
from acteurs.user import User
from ihm.controleurs.controleur_user import ControleurUser
from modele.enums import Priorite, Statut
from modele.exceptions import AccesRefuseException, SuppressionInterditeException
from modele.observateur import ObservateurTickets
from modele.systeme_tickets import SystemeTickets
from modele.ticket import Ticket

racineDepot = Path(__file__).resolve().parent.parent


class FauxPrincipal:
    """Remplace ControleurPrincipal : aucune fenêtre, les ouvertures demandées sont notées."""

    def __init__(self) -> None:
        self.systeme = SystemeTickets()
        self.creations: list[User] = []
        self.editions: list[tuple[User, Ticket]] = []

    def ouvrirCreation(self, user: User) -> None:
        self.creations.append(user)

    def ouvrirEdition(self, user: User, ticket: Ticket) -> None:
        self.editions.append((user, ticket))


class Espion(ObservateurTickets):
    """Note les retraits notifiés par le dépôt : ce que reçoivent F2, F3 et F6."""

    def __init__(self) -> None:
        self.retires: list[Ticket] = []

    def ticketRetire(self, ticket: Ticket) -> None:
        self.retires.append(ticket)


class TestControleurUser(unittest.TestCase):
    """La situation de T Julien dans la maquette de F3."""

    def setUp(self) -> None:
        self._principal = FauxPrincipal()
        systeme = self._principal.systeme
        self._admin = Admin(1, "Ambroise Fleury", "ambroise.fleury@uqac.ca", systeme)
        self._abdoul = User(2, "Abdoul Razack", "abdoul.razack@uqac.ca", systeme)
        self._julien = User(3, "T Julien", "t.julien@uqac.ca", systeme)
        self._mike = User(4, "Mike Tonny", "mike.tonny@uqac.ca", systeme)

        # Créés par T Julien, dans le désordre : #9 assigné à Abdoul, #3 fermé, #6 ouvert.
        self._t9 = self._creer(self._julien, 9, "Faute dans le menu Aide")
        self._t3 = self._creer(self._julien, 3, "Export CSV")
        self._t6 = self._creer(self._julien, 6, "Bouton Annuler inactif")
        self._admin.assignTicket(self._t9, self._abdoul)
        self._admin.closeTicket(self._t3)
        # Assigné à T Julien : #10, créé par Mike.
        self._t10 = self._creer(self._mike, 10, "Notification en double")
        self._admin.assignTicket(self._t10, self._julien)

        # Une édition de #6 en pause, et un brouillon #11 (création en pause, hors du dépôt).
        self._edition6 = self._julien.ouvrirSessionEdition(self._t6)
        self._edition6.ajouterCommentaire("À vérifier sur Firefox.")
        self._edition6.mettreEnPause()
        self._t11 = Ticket(11, "Pagination de l'historique cassée", Priorite.HAUTE)
        self._brouillon = self._julien.ouvrirSessionCreation(self._t11)
        self._brouillon.ajouterTexteSaisi("La page 2 revient à la page 1.")
        self._brouillon.mettreEnPause()

        self._controleur = ControleurUser(self._principal, self._julien)

    @staticmethod
    def _creer(user: User, ticketID: int, titre: str) -> Ticket:
        ticket = Ticket(ticketID, titre, Priorite.MOYENNE)
        user.createTicket(ticket)
        return ticket

    # ------------------------------------------------------------------ onglets

    def testCreesParMoiParNumero(self) -> None:
        self.assertEqual(self._controleur.ticketsCrees(), [self._t3, self._t6, self._t9])

    def testAssignesAMoi(self) -> None:
        self.assertEqual(self._controleur.ticketsAssignes(), [self._t10])

    def testBrouillonsSeulementLesCreations(self) -> None:
        """L'édition en pause de #6 n'est pas un brouillon : son ticket est déjà dans le dépôt."""
        self.assertEqual(self._controleur.brouillons(), [self._brouillon])

    def testBrouillonApplique(self) -> None:
        self._brouillon.reprendre()
        self._brouillon.appliquer()
        self.assertEqual(self._controleur.brouillons(), [])
        self.assertIn(self._t11, self._controleur.ticketsCrees())

    def testBrouillonAbandonne(self) -> None:
        self._brouillon.abandonner()
        self.assertEqual(self._controleur.brouillons(), [])
        self.assertNotIn(self._t11, self._controleur.ticketsCrees())

    def testOngletsDUnAutreUtilisateur(self) -> None:
        autre = ControleurUser(self._principal, self._abdoul)
        self.assertEqual(autre.ticketsCrees(), [])
        self.assertEqual(autre.ticketsAssignes(), [self._t9])
        self.assertEqual(autre.brouillons(), [])

    # ------------------------------------------------------------------ colonne « Édition »

    def testEtatEdition(self) -> None:
        self.assertEqual(self._controleur.etatEdition(self._t6), "en pause")
        self.assertEqual(self._controleur.etatEdition(self._t11), "en pause")
        self.assertEqual(self._controleur.etatEdition(self._t3), "")
        self._edition6.reprendre()
        self.assertEqual(self._controleur.etatEdition(self._t6), "en cours")
        self._edition6.appliquer()
        self.assertEqual(self._controleur.etatEdition(self._t6), "")

    # ------------------------------------------------------------------ boutons

    def testPeutEditer(self) -> None:
        self.assertTrue(self._controleur.peutEditer(self._t6))
        self.assertTrue(self._controleur.peutEditer(self._t11))  # brouillon à reprendre
        self.assertFalse(self._controleur.peutEditer(self._t10))  # pas le créateur

    def testPeutSupprimer(self) -> None:
        self.assertTrue(self._controleur.peutSupprimer(self._t6))
        self.assertFalse(self._controleur.peutSupprimer(self._t9))  # déjà assigné
        self.assertFalse(self._controleur.peutSupprimer(self._t10))  # pas le créateur
        self.assertFalse(self._controleur.peutSupprimer(self._t11))  # hors du dépôt

    def testPeutSoumettre(self) -> None:
        self.assertTrue(self._controleur.peutSoumettre(self._t10))
        self.assertFalse(self._controleur.peutSoumettre(self._t9))  # assigné à Abdoul
        self.assertFalse(self._controleur.peutSoumettre(self._t6))  # personne n'est assigné
        self._controleur.soumettre(self._t10)
        self.assertFalse(self._controleur.peutSoumettre(self._t10))  # déjà en validation

    def testBoutonsCoherentsAvecLeModele(self) -> None:
        """Bouton actif : le modèle accepte ; bouton grisé : le modèle refuse (filet de sécurité)."""
        for ticket in (self._t3, self._t6, self._t9, self._t10):
            with self.subTest(ticket=ticket.ticketID):
                peut = self._controleur.peutSoumettre(ticket)
                try:
                    self._controleur.soumettre(ticket)
                    accepte = True
                except Exception:  # TransitionInvalide ou AccesRefuse
                    accepte = False
                self.assertEqual(peut, accepte)

    # ------------------------------------------------------------------ actions

    def testSupprimer(self) -> None:
        espion = Espion()
        self._principal.systeme.abonner(espion)
        self._controleur.supprimer(self._t6)
        self.assertFalse(self._principal.systeme.contient(self._t6))
        self.assertEqual(espion.retires, [self._t6])  # F2, F3 et F6 sont prévenues
        self.assertEqual(self._controleur.ticketsCrees(), [self._t3, self._t9])

    def testSupprimerRefuseSiDejaAssigne(self) -> None:
        with self.assertRaises(SuppressionInterditeException):
            self._controleur.supprimer(self._t9)

    def testSoumettre(self) -> None:
        self._controleur.soumettre(self._t10)
        self.assertEqual(self._t10.status, Statut.VALIDATION)

    def testSoumettreRefuseSiPasAssigne(self) -> None:
        with self.assertRaises(AccesRefuseException):
            self._controleur.soumettre(self._t9)

    def testNouveauTicketEtEditerDeleguentAuPrincipal(self) -> None:
        self._controleur.nouveauTicket()
        self._controleur.editer(self._t6)
        self.assertEqual(self._principal.creations, [self._julien])
        self.assertEqual(self._principal.editions, [(self._julien, self._t6)])

    # ------------------------------------------------------------------ dépendances

    def testSansTkinter(self) -> None:
        """Le contrôleur reste testable dans le CI, qui n'a pas d'écran."""
        resultat = subprocess.run(
            [sys.executable, "-c",
             "import sys, ihm.controleurs.controleur_user; "
             "print(any(m.startswith('tkinter') for m in sys.modules))"],
            cwd=racineDepot, capture_output=True, text=True, check=True,
        )
        self.assertEqual(resultat.stdout.strip(), "False")


if __name__ == "__main__":
    unittest.main()
