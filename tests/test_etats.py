"""Tests de M2 : transitions permises et cohérence avec gererTransition().

Lancer depuis la racine du dépôt :  python -m unittest discover -s tests -v
"""
from __future__ import annotations

import unittest

from etats.etat_assigne import EtatAssigne
from etats.etat_ferme import EtatFerme
from etats.etat_ouvert import EtatOuvert
from etats.etat_termine import EtatTermine
from etats.etat_validation import EtatValidation
from modele.enums import Priorite, Statut
from modele.exceptions import TransitionInvalideException
from modele.ticket import Ticket

ETATS = (EtatOuvert, EtatAssigne, EtatValidation, EtatTermine, EtatFerme)

# Cycle de vie documenté dans le README (table des transitions).
ATTENDU = {
    Statut.OUVERT: {Statut.ASSIGNE, Statut.FERME},
    Statut.ASSIGNE: {Statut.ASSIGNE, Statut.OUVERT, Statut.VALIDATION, Statut.FERME},
    Statut.VALIDATION: {Statut.ASSIGNE, Statut.TERMINE},
    Statut.TERMINE: set(),
    Statut.FERME: set(),
}


def ticketDansEtat(classe_etat: type) -> Ticket:
    ticket = Ticket(1, "Ticket de test", Priorite.BASSE)
    ticket.setEtat(classe_etat())
    return ticket


class TestTransitionsPermises(unittest.TestCase):
    def test_table_des_transitions(self) -> None:
        """Chaque état déclare exactement les transitions du cycle de vie documenté."""
        for classe in ETATS:
            etat = classe()
            with self.subTest(etat=etat.nom.name):
                self.assertEqual(set(etat.transitionsPermises), ATTENDU[etat.nom])

    def test_etats_terminaux(self) -> None:
        """Décision du sprint : un ticket TERMINE ou FERME ne change plus d'état."""
        for classe in (EtatTermine, EtatFerme):
            with self.subTest(etat=classe.__name__):
                self.assertEqual(classe().transitionsPermises, frozenset())

    def test_coherence_avec_gerer_transition(self) -> None:
        """transitionPossible() annonce exactement ce que gererTransition() accepte."""
        for classe in ETATS:
            for statut in Statut:
                with self.subTest(etat=classe.__name__, statut=statut.name):
                    ticket = ticketDansEtat(classe)
                    annonce = ticket.transitionPossible(statut)
                    try:
                        ticket.updateStatus(statut)
                        accepte = True
                    except TransitionInvalideException:
                        accepte = False
                    self.assertEqual(annonce, accepte)
                    if accepte:
                        # La transition acceptée mène bien au statut demandé.
                        self.assertIs(ticket.status, statut)

    def test_interrogation_sans_effet(self) -> None:
        """Interroger les transitions ne modifie jamais le ticket."""
        ticket = ticketDansEtat(EtatOuvert)
        for statut in Statut:
            ticket.transitionPossible(statut)
        self.assertIs(ticket.status, Statut.OUVERT)

    def test_lecture_seule(self) -> None:
        ticket = ticketDansEtat(EtatOuvert)
        self.assertIsInstance(ticket.transitionsPermises, frozenset)
        with self.assertRaises(AttributeError):
            ticket.transitionsPermises = frozenset()  # pyright: ignore[reportAttributeAccessIssue]


if __name__ == "__main__":
    unittest.main()
