"""Tests de ControleurAdmin, sans fenêtre : un faux principal remplace ControleurPrincipal."""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

from acteurs.admin import Admin
from acteurs.user import User
from ihm.controleurs.controleur_admin import STATUTS_DES_ACTIONS, ControleurAdmin
from modele.enums import Priorite, Statut
from modele.observateur import ObservateurTickets
from modele.systeme_tickets import SystemeTickets
from modele.ticket import Ticket
from sessions.rapport_execution import RapportExecution

racineDepot = Path(__file__).resolve().parent.parent


class FauxPrincipal:
    """Remplace ControleurPrincipal : aucune fenêtre, les rapports affichés sont notés."""

    def __init__(self) -> None:
        self.systeme = SystemeTickets()
        self.rapports: list[tuple[RapportExecution, str]] = []

    def afficherRapport(self, rapport: RapportExecution, libelle: str) -> None:
        self.rapports.append((rapport, libelle))


class Compteur(ObservateurTickets):
    """Compte les modifications notifiées par le dépôt : ce que reçoit la vue F2."""

    def __init__(self) -> None:
        self.modifications = 0

    def ticketModifie(self, ticket: Ticket) -> None:
        self.modifications += 1


class TestControleurAdmin(unittest.TestCase):
    """Un ticket dans chaque statut, comme dans la maquette de F2."""

    def setUp(self) -> None:
        self._principal = FauxPrincipal()
        systeme = self._principal.systeme
        self._admin = Admin(1, "Ambroise Fleury", "ambroise.fleury@uqac.ca", systeme)
        self._abdoul = User(2, "Abdoul Razack", "abdoul.razack@uqac.ca", systeme)
        self._julien = User(3, "T Julien", "t.julien@uqac.ca", systeme)
        self._mike = User(4, "Mike Tonny", "mike.tonny@uqac.ca", systeme)

        # Créés dans le désordre : la liste doit être triée par numéro.
        self._t7 = self._creer(self._mike, 7, "Lenteur de la recherche")
        self._t1 = self._creer(self._abdoul, 1, "Bug de connexion")
        self._t2 = self._creer(self._abdoul, 2, "Erreur d'affichage mobile")
        self._t3 = self._creer(self._julien, 3, "Export CSV")
        self._t6 = self._creer(self._julien, 6, "Bouton Annuler inactif")
        self._t8 = self._creer(self._julien, 8, "Erreur 500 au paiement")

        self._admin.assignTicket(self._t1, self._mike)
        self._mike.soumettreValidation(self._t1)
        self._admin.validerTicket(self._t1)  # TERMINE
        self._admin.assignTicket(self._t2, self._mike)  # ASSIGNE
        self._admin.closeTicket(self._t3)  # FERME
        self._admin.assignTicket(self._t8, self._mike)
        self._mike.soumettreValidation(self._t8)  # VALIDATION ; #6 et #7 restent OUVERT

        self._controleur = ControleurAdmin(self._principal, self._admin)

    @staticmethod
    def _creer(user: User, ticketID: int, titre: str) -> Ticket:
        ticket = Ticket(ticketID, titre, Priorite.MOYENNE)
        user.createTicket(ticket)
        return ticket

    # ------------------------------------------------------------------ tickets()

    def testTousLesTicketsParNumero(self) -> None:
        numeros = [ticket.ticketID for ticket in self._controleur.tickets()]
        self.assertEqual(numeros, [1, 2, 3, 6, 7, 8])

    def testFiltreParStatut(self) -> None:
        self.assertEqual(self._controleur.tickets(Statut.OUVERT), [self._t6, self._t7])
        self.assertEqual(self._controleur.tickets(Statut.VALIDATION), [self._t8])

    def testNouveauTicketVisibleSansRienRecharger(self) -> None:
        t9 = self._creer(self._julien, 9, "Faute dans le menu Aide")
        self.assertIn(t9, self._controleur.tickets(Statut.OUVERT))

    # ------------------------------------------------------------------ actionsPossibles()

    def testAucuneSelectionAucuneAction(self) -> None:
        self.assertEqual(
            self._controleur.actionsPossibles([]),
            {"assigner": False, "desassigner": False, "valider": False, "fermer": False},
        )

    def testDeuxTicketsOuverts(self) -> None:
        """Repère 6 de la maquette : ASSIGNE et FERME permis, OUVERT et TERMINE non."""
        self.assertEqual(
            self._controleur.actionsPossibles([self._t6, self._t7]),
            {"assigner": True, "desassigner": False, "valider": False, "fermer": True},
        )

    def testTicketEnValidation(self) -> None:
        # « Assigner » couvre le rejet d'une validation.
        self.assertEqual(
            self._controleur.actionsPossibles([self._t8]),
            {"assigner": True, "desassigner": False, "valider": True, "fermer": False},
        )

    def testEtatsTerminauxAucuneAction(self) -> None:
        self.assertFalse(any(self._controleur.actionsPossibles([self._t1, self._t3]).values()))

    def testUnTicketQuiPermetSuffit(self) -> None:
        possibles = self._controleur.actionsPossibles([self._t3, self._t2, self._t8])
        self.assertTrue(all(possibles.values()))

    def testCoherentAvecLesEtats(self) -> None:
        """Chaque bouton suit exactement transitionPossible() de l'état du ticket."""
        for ticket in (self._t1, self._t2, self._t3, self._t6, self._t8):
            possibles = self._controleur.actionsPossibles([ticket])
            for action, statut in STATUTS_DES_ACTIONS.items():
                with self.subTest(ticket=ticket.status.name, action=action):
                    self.assertEqual(possibles[action], ticket.transitionPossible(statut))

    # ------------------------------------------------------------------ preparerLot()

    def testLotPrepareSansRienModifier(self) -> None:
        lot = self._controleur.preparerLot("assigner", [self._t6, self._t7], self._julien)
        self.assertEqual(
            lot.modificationsEnAttente,
            ["Assigner le ticket #6 à T Julien", "Assigner le ticket #7 à T Julien"],
        )
        self.assertEqual(self._t6.status, Statut.OUVERT)
        self.assertIsNone(self._t6.assignedUser)
        self.assertEqual(self._principal.rapports, [])

    def testLibellesDesQuatreActions(self) -> None:
        attendus = {
            "desassigner": "Désassigner le ticket #2",
            "valider": "Valider le ticket #2",
            "fermer": "Fermer le ticket #2",
        }
        for action, libelle in attendus.items():
            with self.subTest(action=action):
                lot = self._controleur.preparerLot(action, [self._t2])
                self.assertEqual(lot.modificationsEnAttente, [libelle])

    def testAssignerSansUtilisateurRefuse(self) -> None:
        with self.assertRaises(ValueError):
            self._controleur.preparerLot("assigner", [self._t6])

    def testActionInconnueRefusee(self) -> None:
        with self.assertRaises(ValueError):
            self._controleur.preparerLot("supprimer", [self._t6])

    def testLotReconstruitAChaqueChoix(self) -> None:
        """Changer d'assigné dans F7 donne un nouveau lot ; l'ancien, jamais appliqué, ne fait rien."""
        self._controleur.preparerLot("assigner", [self._t6], self._julien)
        lot = self._controleur.preparerLot("assigner", [self._t6], self._mike)
        self._controleur.appliquerLot(lot)
        self.assertIs(self._t6.assignedUser, self._mike)
        self.assertEqual(self._principal.rapports[0][0].nombreSucces, 1)

    # ------------------------------------------------------------------ appliquerLot()

    def testFermerAuMieuxAvecRapport(self) -> None:
        """Exemple de la maquette F8 : #2 et #7 fermés, #8 refusé avec son motif."""
        lot = self._controleur.preparerLot("fermer", [self._t2, self._t7, self._t8])
        self._controleur.appliquerLot(lot)

        self.assertEqual(len(self._principal.rapports), 1)
        rapport, libelle = self._principal.rapports[0]
        self.assertEqual(libelle, "Lot administrateur")
        self.assertEqual(rapport.succes, ["Fermer le ticket #2", "Fermer le ticket #7"])
        self.assertEqual(len(rapport.refus), 1)
        self.assertEqual(rapport.refus[0][0], "Fermer le ticket #8")
        self.assertIn("VALIDATION", rapport.refus[0][1])
        self.assertEqual(
            [self._t2.status, self._t7.status, self._t8.status],
            [Statut.FERME, Statut.FERME, Statut.VALIDATION],
        )

    def testRejetDUneValidation(self) -> None:
        lot = self._controleur.preparerLot("assigner", [self._t8], self._abdoul)
        self._controleur.appliquerLot(lot)
        self.assertEqual(self._t8.status, Statut.ASSIGNE)
        self.assertIs(self._t8.assignedUser, self._abdoul)

    def testAppliquerNotifieLaListe(self) -> None:
        """La liste F2, abonnée au dépôt, est prévenue sans rafraîchissement manuel."""
        compteur = Compteur()
        self._principal.systeme.abonner(compteur)
        self._controleur.appliquerLot(self._controleur.preparerLot("valider", [self._t8]))
        self.assertGreater(compteur.modifications, 0)

    def testTicketRetireAvantApplication(self) -> None:
        lot = self._controleur.preparerLot("fermer", [self._t6, self._t7])
        self._julien.supprimerTicket(self._t6)
        self._controleur.appliquerLot(lot)
        rapport = self._principal.rapports[0][0]
        self.assertEqual(rapport.refus, [("Fermer le ticket #6", "ticket retiré du dépôt")])
        self.assertEqual(rapport.succes, ["Fermer le ticket #7"])

    # ------------------------------------------------------------------ dépendances

    def testSansTkinter(self) -> None:
        """Le contrôleur reste testable dans le CI, qui n'a pas d'écran."""
        resultat = subprocess.run(
            [sys.executable, "-c",
             "import sys, ihm.controleurs.controleur_admin; "
             "print(any(m.startswith('tkinter') for m in sys.modules))"],
            cwd=racineDepot, capture_output=True, text=True, check=True,
        )
        self.assertEqual(resultat.stdout.strip(), "False")


if __name__ == "__main__":
    unittest.main()
