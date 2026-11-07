"""Tests de ControleurUser (F3), sans fenêtre, contre la vraie API sur les données de
démonstration. Un faux principal remplace ControleurPrincipal et note les fenêtres demandées.
"""
from __future__ import annotations

import copy
import subprocess
import sys
import unittest
from pathlib import Path

from ihm.controleurs.controleur_user import ControleurUser
from ihm.passerelle.erreurs import ErreurServeur
from ihm.passerelle.objets_lecture import ActeurLu, TicketLu, TicketRefLu
from modele.enums import Priorite, Statut
from modele.exceptions import (
    AccesRefuseException,
    SuppressionInterditeException,
    TransitionInvalideException,
)
from modele.observateur import ObservateurTickets
from tests.serveur_essai import ABDOUL, HEIN, JULIEN, MIKE, ServeurEssai
from tests.test_passerelle_client import EXEMPLE_BROUILLON

racineDepot = Path(__file__).resolve().parent.parent

# Tout refus que le serveur peut opposer à une suppression ou à une soumission.
REFUS = (
    ErreurServeur, AccesRefuseException, SuppressionInterditeException, TransitionInvalideException
)


class FauxPrincipal:
    """Remplace ControleurPrincipal : aucune fenêtre, les ouvertures demandées sont notées."""

    def __init__(self) -> None:
        self.ouvertures: list[tuple[str, int, int | None]] = []

    def ouvrirCreation(self, user: ActeurLu) -> None:
        self.ouvertures.append(("creation", user.id, None))

    def ouvrirEdition(self, user: ActeurLu, ticket: TicketRefLu) -> None:
        self.ouvertures.append(("edition", user.id, ticket.ticketID))


class Espion(ObservateurTickets):
    def __init__(self) -> None:
        self.evenements: list[tuple[str, int]] = []

    def ticketModifie(self, ticket: TicketLu) -> None:  # type: ignore[override]
        self.evenements.append(("modification", ticket.ticketID))

    def ticketRetire(self, ticket: TicketLu) -> None:  # type: ignore[override]
        self.evenements.append(("retrait", ticket.ticketID))


def brouillon(id: int, type_: str, ticketId: int, *, enPause: bool = False) -> dict:
    """Brouillon du contrat (exemple de openapi.yaml), sur le ticket voulu."""
    donnees = copy.deepcopy(EXEMPLE_BROUILLON)
    donnees.update(id=id, type=type_, enPause=enPause)
    donnees["ticket"]["id"] = ticketId
    donnees["proprietaire"] = {"id": ABDOUL, "nom": "Abdoul Razack"}
    return donnees


class TestControleurUser(unittest.TestCase):
    """Données de démonstration : Abdoul a créé 1 et 2 (déjà assignés) et s'est vu assigner 9."""

    def setUp(self) -> None:
        self.serveur = ServeurEssai()
        self.addCleanup(self.serveur.fermer)
        self.principal = FauxPrincipal()
        self.controleur = self.controleurDe(ABDOUL)

    def controleurDe(self, acteurId: int) -> ControleurUser:
        user, client, source = self.serveur.session(acteurId)
        controleur = ControleurUser(self.principal, user, client, source)  # type: ignore[arg-type]
        controleur.chargerBrouillons()
        return controleur

    def ticket(self, ticketId: int, controleur: ControleurUser | None = None) -> TicketLu:
        """Le ticket tel que F3 le lit, dans l'un de ses onglets ou dans la source."""
        controleur = controleur or self.controleur
        ticket = controleur.source.ticketParId(ticketId)
        assert ticket is not None
        return ticket

    def creerTicket(self, acteurId: int = ABDOUL) -> int:
        """Un ticket neuf, jamais assigné : le seul cas où la suppression est permise."""
        resultat = self.serveur.client(acteurId).creerTicket("À supprimer", Priorite.BASSE, "Texte")
        self.controleur.source.rafraichir()
        return resultat["ticket"]["id"]

    @staticmethod
    def numeros(tickets: list[TicketLu]) -> list[int]:
        return [ticket.ticketID for ticket in tickets]

    # ------------------------------------------------------------------ onglets

    def testCreesParMoi(self) -> None:
        self.assertEqual(self.numeros(self.controleur.ticketsCrees()), [1, 2])
        self.assertIn(("GET", f"/tickets?createur={ABDOUL}"), self.serveur.requetes)

    def testAssignesAMoi(self) -> None:
        self.assertEqual(self.numeros(self.controleur.ticketsAssignes()), [9])
        # M1 : un ticket TERMINE garde son assigné, il reste dans l'onglet.
        mike = self.controleurDe(MIKE)
        self.assertEqual(self.numeros(mike.ticketsAssignes()), [1, 8])

    def testOngletsDUnAutreUtilisateur(self) -> None:
        julien = self.controleurDe(JULIEN)
        self.assertEqual(self.numeros(julien.ticketsCrees()), [3, 6, 9])
        self.assertEqual(self.numeros(julien.ticketsAssignes()), [10])

    def testSansBrouillon(self) -> None:
        # Les données de démonstration n'ont aucun brouillon.
        self.assertEqual(self.controleur.brouillons(), [])
        self.assertEqual(self.controleur.etatEdition(self.ticket(1)), "")

    def testBrouillonsOuvertsSurLeServeur(self) -> None:
        """Une création en cours et une édition en pause, ouvertes par l'API (S4)."""
        client = self.serveur.client(ABDOUL)
        creation = client.ouvrirBrouillonCreation("Paiement refusé", Priorite.MOYENNE)
        edition = client.ouvrirBrouillonEdition(1)
        client.modifierBrouillon(edition["id"], enPause=True)
        self.controleur.chargerBrouillons()
        brouillons = self.controleur.brouillons()
        self.assertEqual([b.id for b in brouillons], [creation["id"]])
        self.assertEqual(brouillons[0].ticket.title, "Paiement refusé")
        self.assertEqual(self.controleur.etatEdition(brouillons[0].ticket), "en cours")
        self.assertEqual(self.controleur.etatEdition(self.ticket(1)), "en pause")
        self.assertEqual(self.controleur.etatEdition(self.ticket(2)), "")
        self.assertTrue(self.controleur.peutEditer(brouillons[0].ticket))
        # Le ticket d'une création n'est pas encore dans le dépôt : ni suppression ni soumission.
        self.assertFalse(self.controleur.peutSupprimer(brouillons[0].ticket))
        self.assertFalse(self.controleur.peutSoumettre(brouillons[0].ticket))
        # Les brouillons d'Abdoul ne sont pas ceux de Julien.
        julien = self.controleurDe(JULIEN)
        self.assertEqual(julien.brouillons(), [])

    def testBrouillonsDuServeur(self) -> None:
        reponses = [
            brouillon(1, "creation", 11),
            brouillon(2, "edition", 2, enPause=True),
            brouillon(3, "creation", 12, enPause=True),
        ]
        self.controleur._client.listerBrouillons = lambda: reponses  # type: ignore[method-assign]
        self.controleur.chargerBrouillons()
        # L'onglet ne montre que les créations ; l'édition de 2 se voit dans la colonne « Édition ».
        self.assertEqual([b.ticket.ticketID for b in self.controleur.brouillons()], [11, 12])
        self.assertEqual(self.controleur.etatEdition(self.ticket(2)), "en pause")
        self.assertEqual(self.controleur.etatEdition(self.ticket(1)), "")
        creation = self.controleur.brouillons()[0]
        self.assertEqual(self.controleur.etatEdition(creation.ticket), "en cours")
        self.assertTrue(self.controleur.peutEditer(creation.ticket))

    def testPanneDesBrouillonsSignalee(self) -> None:
        """Une erreur du serveur n'est pas cachée : F3 l'affichera."""
        def panne() -> list:
            raise ErreurServeur("Erreur interne", 500)

        self.controleur._client.listerBrouillons = panne  # type: ignore[method-assign]
        with self.assertRaises(ErreurServeur):
            self.controleur.chargerBrouillons()

    # ------------------------------------------------------------------ boutons actifs

    def testPeutEditer(self) -> None:
        self.assertTrue(self.controleur.peutEditer(self.ticket(1)))
        # Assigné mais pas créateur : il ne peut pas éditer.
        self.assertFalse(self.controleur.peutEditer(self.ticket(9)))

    def testComparaisonParIdentifiantPasParIdentite(self) -> None:
        """Les objets de deux lectures différentes ne sont jamais les mêmes : `is` échouerait."""
        lu = self.controleur.ticketsCrees()[0]
        self.assertIsNot(lu.creator, self.controleur.user)
        self.assertTrue(self.controleur.peutEditer(lu))

    def testPeutSupprimer(self) -> None:
        nouveau = self.creerTicket()
        self.assertTrue(self.controleur.peutSupprimer(self.ticket(nouveau)))
        # Déjà assigné une fois : la suppression est refusée.
        self.assertFalse(self.controleur.peutSupprimer(self.ticket(1)))
        # Pas le créateur.
        self.assertFalse(self.controleur.peutSupprimer(self.ticket(6)))
        # Le ticket d'un brouillon n'est pas dans le dépôt.
        self.assertFalse(
            self.controleur.peutSupprimer(TicketRefLu(nouveau, "À supprimer", Priorite.BASSE))
        )

    def testPeutSoumettre(self) -> None:
        self.assertTrue(self.controleur.peutSoumettre(self.ticket(9)))
        # Assigné à Hein, pas à Abdoul.
        self.assertFalse(self.controleur.peutSoumettre(self.ticket(2)))
        # Déjà en validation : la transition n'est plus permise.
        mike = self.controleurDe(MIKE)
        self.assertFalse(mike.peutSoumettre(self.ticket(8, mike)))

    def testBoutonsCoherentsAvecLeServeur(self) -> None:
        """Bouton actif = le serveur accepte vraiment ; bouton grisé = le serveur refuse."""
        for acteurId in (ABDOUL, JULIEN, MIKE, HEIN):
            controleur = self.controleurDe(acteurId)
            for ticket in controleur.ticketsCrees() + controleur.ticketsAssignes():
                for nom, regle, action in (
                    ("supprimer", controleur.peutSupprimer,
                     lambda client, t: client.supprimerTicket(t.ticketID)),
                    ("soumettre", controleur.peutSoumettre,
                     lambda client, t: client.changerStatut(t.ticketID, Statut.VALIDATION)),
                ):
                    with self.subTest(acteur=acteurId, ticket=ticket.ticketID, action=nom):
                        serveur = ServeurEssai()
                        try:
                            action(serveur.client(acteurId), ticket)
                            accepte = True
                        except REFUS:
                            accepte = False
                        finally:
                            serveur.fermer()
                        self.assertEqual(regle(ticket), accepte)

    # ------------------------------------------------------------------ actions

    def testSupprimer(self) -> None:
        nouveau = self.creerTicket()
        espion = Espion()
        self.controleur.source.abonner(espion)
        self.controleur.supprimer(self.ticket(nouveau))
        self.assertEqual(espion.evenements, [("retrait", nouveau)])
        self.assertEqual(self.numeros(self.controleur.ticketsCrees()), [1, 2])

    def testSupprimerRefuseSiDejaAssigne(self) -> None:
        with self.assertRaises(SuppressionInterditeException):
            self.controleur.supprimer(self.ticket(1))

    def testSoumettre(self) -> None:
        espion = Espion()
        self.controleur.source.abonner(espion)
        self.controleur.soumettre(self.ticket(9))
        self.assertIs(self.ticket(9).status, Statut.VALIDATION)
        self.assertEqual(espion.evenements, [("modification", 9)])

    def testSoumettreRefuseSiPasAssigne(self) -> None:
        with self.assertRaises(AccesRefuseException):
            self.controleur.soumettre(self.ticket(2))

    def testNouveauTicketEtEditerDeleguentAuPrincipal(self) -> None:
        self.controleur.nouveauTicket()
        self.controleur.editer(self.ticket(1))
        self.assertEqual(
            self.principal.ouvertures, [("creation", ABDOUL, None), ("edition", ABDOUL, 1)]
        )

    # ------------------------------------------------------------------ dépendances

    def testSansTkinterNiModele(self) -> None:
        code = (
            "import sys, ihm.controleurs.controleur_user; "
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
