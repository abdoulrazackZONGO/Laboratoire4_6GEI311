"""Tests de ControleurAdmin (F2 et F7), sans fenêtre, contre la vraie API sur les données de
démonstration. Un faux principal remplace ControleurPrincipal et note les rapports affichés.
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

from ihm.controleurs.controleur_admin import (
    LIBELLE_LOT,
    STATUTS_DES_ACTIONS,
    ControleurAdmin,
    LotPrepare,
)
from ihm.passerelle.erreurs import RessourceIntrouvable
from ihm.passerelle.objets_lecture import ActeurLu, RapportLu, TicketLu
from modele.enums import Priorite, Statut
from modele.observateur import ObservateurTickets
from tests.serveur_essai import ABDOUL, ADMIN, HEIN, JULIEN, MIKE, ServeurEssai

racineDepot = Path(__file__).resolve().parent.parent

# Tickets de démonstration : 6 et 7 OUVERT, 2, 9 et 10 ASSIGNE, 8 VALIDATION, 1 TERMINE, 3 FERME.
TOUS_LES_TICKETS = [1, 2, 3, 6, 7, 8, 9, 10]


class FauxPrincipal:
    """Remplace ControleurPrincipal : aucune fenêtre, les rapports affichés sont notés."""

    def __init__(self) -> None:
        self.rapports: list[tuple[RapportLu, str]] = []

    def afficherRapport(self, rapport: RapportLu, libelle: str) -> None:
        self.rapports.append((rapport, libelle))


class Espion(ObservateurTickets):
    """Ce que reçoit la vue F2 : (genre, numéro) de chaque notification de la source."""

    def __init__(self) -> None:
        self.evenements: list[tuple[str, int]] = []

    def ticketModifie(self, ticket: TicketLu) -> None:  # type: ignore[override]
        self.evenements.append(("modification", ticket.ticketID))

    def ticketAjoute(self, ticket: TicketLu) -> None:  # type: ignore[override]
        self.evenements.append(("ajout", ticket.ticketID))


class TestControleurAdmin(unittest.TestCase):
    def setUp(self) -> None:
        self.serveur = ServeurEssai()
        self.addCleanup(self.serveur.fermer)
        self.principal = FauxPrincipal()
        self.admin, self.client, self.source = self.serveur.session(ADMIN)
        self.controleur = ControleurAdmin(self.principal, self.admin, self.client, self.source)  # type: ignore[arg-type]
        self.mike = self.serveur.acteur(MIKE)
        self.hein = self.serveur.acteur(HEIN)

    def tickets(self, *ids: int) -> list[TicketLu]:
        return [ticket for ticket in self.controleur.tickets() if ticket.ticketID in ids]

    @staticmethod
    def numeros(tickets: list[TicketLu]) -> list[int]:
        return [ticket.ticketID for ticket in tickets]

    # ------------------------------------------------------------------ lecture

    def testTousLesTicketsParNumero(self) -> None:
        self.assertEqual(self.numeros(self.controleur.tickets()), TOUS_LES_TICKETS)

    def testFiltreParStatut(self) -> None:
        self.assertEqual(self.numeros(self.controleur.tickets(Statut.OUVERT)), [6, 7])
        self.assertEqual(self.numeros(self.controleur.tickets(Statut.ASSIGNE)), [2, 9, 10])
        self.assertEqual(self.numeros(self.controleur.tickets(Statut.FERME)), [3])

    def testTicketCreeDansUneAutreGUIVisibleAuSondage(self) -> None:
        # Un User crée un ticket avec son propre client : F2 le voit au sondage suivant.
        self.serveur.client(ABDOUL).creerTicket("Nouveau", Priorite.BASSE, "Texte")
        self.assertNotIn(11, self.numeros(self.controleur.tickets()))
        self.assertTrue(self.source.verifierVersion())
        self.assertIn(11, self.numeros(self.controleur.tickets(Statut.OUVERT)))

    # ------------------------------------------------------------------ boutons actifs

    def testAucuneSelectionAucuneAction(self) -> None:
        self.assertEqual(
            self.controleur.actionsPossibles([]), {action: False for action in STATUTS_DES_ACTIONS}
        )

    def testDeuxTicketsOuverts(self) -> None:
        self.assertEqual(
            self.controleur.actionsPossibles(self.tickets(6, 7)),
            {"assigner": True, "desassigner": False, "valider": False, "fermer": True},
        )

    def testTicketEnValidation(self) -> None:
        # assigner couvre aussi le rejet d'une validation.
        self.assertEqual(
            self.controleur.actionsPossibles(self.tickets(8)),
            {"assigner": True, "desassigner": False, "valider": True, "fermer": False},
        )

    def testEtatsTerminauxAucuneAction(self) -> None:
        possibles = self.controleur.actionsPossibles(self.tickets(1, 3))
        self.assertFalse(any(possibles.values()))

    def testUnTicketQuiPermetSuffit(self) -> None:
        self.assertTrue(self.controleur.actionsPossibles(self.tickets(3, 6))["assigner"])

    def testCoherentAvecLeServeur(self) -> None:
        """Un bouton actif pour un ticket seul = l'opération réussit vraiment sur le serveur."""
        for ticket in self.controleur.tickets():
            for action in STATUTS_DES_ACTIONS:
                with self.subTest(ticket=ticket.ticketID, action=action):
                    attendu = self.controleur.actionsPossibles([ticket])[action]
                    serveur = ServeurEssai()
                    try:
                        assigneId = MIKE if action == "assigner" else None
                        rapport = serveur.client(ADMIN).appliquerLot(
                            action, [ticket.ticketID], assigneId
                        )
                    finally:
                        serveur.fermer()
                    self.assertEqual(rapport["nombreSucces"] == 1, attendu)

    # ------------------------------------------------------------------ aperçu du lot (F7)

    def testLotPrepareSansRienEnvoyer(self) -> None:
        avant = len(self.serveur.requetes)
        lot = self.controleur.preparerLot("assigner", self.tickets(6, 7), self.mike)
        self.assertEqual(len(self.serveur.requetes), avant)
        self.assertEqual(
            lot,
            LotPrepare(
                action="assigner", ticketIds=(6, 7), assigneId=MIKE,
                modificationsEnAttente=(
                    "Assigner le ticket #6 à Mike Tonny", "Assigner le ticket #7 à Mike Tonny",
                ),
            ),
        )
        self.assertEqual(lot.libelle, LIBELLE_LOT)

    def testLibellesIdentiquesAuRapportDuServeur(self) -> None:
        """F7 annonce exactement les opérations que F8 détaillera, succès ou refus."""
        cas = {
            "assigner": ([6, 7, 3], self.mike),
            "desassigner": ([2, 6], None),
            "valider": ([8, 7], None),
            "fermer": ([6, 1], None),
        }
        for action, (ids, user) in cas.items():
            with self.subTest(action):
                lot = self.controleur.preparerLot(action, self.tickets(*ids), user)
                rapport = RapportLu.depuisJSON(
                    self.serveur.client(ADMIN).appliquerLot(
                        action, list(lot.ticketIds), lot.assigneId
                    )
                )
                operations = rapport.succes + [operation for operation, _ in rapport.refus]
                self.assertEqual(sorted(lot.modificationsEnAttente), sorted(operations))
                self.assertEqual(rapport.libelle, lot.libelle)

    def testAssignerSansUtilisateurRefuse(self) -> None:
        with self.assertRaises(ValueError):
            self.controleur.preparerLot("assigner", self.tickets(6))

    def testActionInconnueRefusee(self) -> None:
        with self.assertRaises(ValueError):
            self.controleur.preparerLot("supprimer", self.tickets(6))

    def testLotReconstruitAChaqueChoix(self) -> None:
        pourMike = self.controleur.preparerLot("assigner", self.tickets(6), self.mike)
        pourHein = self.controleur.preparerLot("assigner", self.tickets(6), self.hein)
        self.assertEqual(pourMike.modificationsEnAttente, ("Assigner le ticket #6 à Mike Tonny",))
        self.assertEqual(pourHein.modificationsEnAttente, ("Assigner le ticket #6 à Hein Tommy",))
        self.assertEqual(pourHein.assigneId, HEIN)

    def testAssigneIgnorePourLesAutresActions(self) -> None:
        lot = self.controleur.preparerLot("fermer", self.tickets(6), self.mike)
        self.assertIsNone(lot.assigneId)

    # ------------------------------------------------------------------ application

    def testFermerAuMieuxAvecRapport(self) -> None:
        lot = self.controleur.preparerLot("fermer", self.tickets(6, 3))
        rapport = self.controleur.appliquerLot(lot)
        self.assertEqual(rapport.succes, ["Fermer le ticket #6"])
        self.assertEqual(rapport.nombreRefus, 1)
        self.assertEqual(rapport.refus[0][0], "Fermer le ticket #3")
        self.assertEqual(self.principal.rapports, [(rapport, LIBELLE_LOT)])
        # La source est relue sans attendre le sondage.
        self.assertIs(self.source.ticketParId(6).status, Statut.FERME)

    def testRejetDUneValidation(self) -> None:
        self.controleur.appliquerLot(self.controleur.preparerLot("assigner", self.tickets(8), self.hein))
        ticket = self.source.ticketParId(8)
        self.assertIs(ticket.status, Statut.ASSIGNE)
        self.assertEqual(ticket.assignedUser, self.hein)

    def testAppliquerNotifieLaListe(self) -> None:
        espion = Espion()
        self.source.abonner(espion)
        self.controleur.appliquerLot(self.controleur.preparerLot("assigner", self.tickets(6), self.mike))
        self.assertEqual(espion.evenements, [("modification", 6)])

    def testTicketSupprimeAvantApplication(self) -> None:
        """Un ticket supprimé entre F7 et « Appliquer » : le serveur refuse tout le lot (404)."""
        lot = self.controleur.preparerLot("fermer", self.tickets(7, 6))
        self.serveur.client(JULIEN).supprimerTicket(6)
        with self.assertRaises(RessourceIntrouvable):
            self.controleur.appliquerLot(lot)
        self.assertEqual(self.principal.rapports, [])
        self.source.rafraichir()
        self.assertIs(self.source.ticketParId(7).status, Statut.OUVERT)

    def testAdminComparéParIdentifiant(self) -> None:
        self.assertEqual(self.controleur.admin, ActeurLu(ADMIN, "Ambroise Fleury"))

    # ------------------------------------------------------------------ dépendances

    def testSansTkinterNiModele(self) -> None:
        """Le contrôleur reste testable dans le CI, qui n'a pas d'écran, et ne charge rien du
        serveur ni du modèle : seulement la passerelle, les énumérations et l'observateur."""
        code = (
            "import sys, ihm.controleurs.controleur_admin; "
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
