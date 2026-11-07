"""Tests de S4 : registre des brouillons, avec de vraies sessions du modèle et sans requête HTTP.

Lancer depuis la racine du dépôt :  python -m unittest discover -s tests -t . -v
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from acteurs.user import User
from api.contexte import ContexteServeur
from api.registre_brouillons import EntreeBrouillon, RegistreBrouillons
from modele.enums import Priorite
from modele.exceptions import SessionIndisponibleException
from modele.systeme_tickets import SystemeTickets
from modele.ticket import Ticket


class TestAvecSessions(unittest.TestCase):
    def setUp(self) -> None:
        self.systeme = SystemeTickets()
        self.julien = User(3, "T Julien", "t.julien@uqac.ca", self.systeme)
        self.abdoul = User(2, "Abdoul Razack", "abdoul.razack@uqac.ca", self.systeme)
        self.registre = RegistreBrouillons()

    def ouvrirCreation(self, user: User | None = None) -> EntreeBrouillon:
        user = user if user is not None else self.julien
        ticket = Ticket(self.systeme.reserverIdentifiant(), "Nouveau", Priorite.BASSE)
        return self.registre.ouvrir(user.ouvrirSessionCreation(ticket), user, True)

    def ouvrirEdition(self, user: User | None = None) -> EntreeBrouillon:
        user = user if user is not None else self.julien
        ticket = Ticket(self.systeme.reserverIdentifiant(), "Existant", Priorite.BASSE)
        user.createTicket(ticket)
        return self.registre.ouvrir(user.ouvrirSessionEdition(ticket), user, False)


class TestEntreeBrouillon(TestAvecSessions):
    def test_etat_initial(self) -> None:
        entree = self.ouvrirCreation()
        self.assertEqual(entree.id, 1)
        self.assertIs(entree.proprietaire, self.julien)
        self.assertTrue(entree.estCreation)
        self.assertTrue(entree.session.estOuverte)
        self.assertEqual(entree.texteBrouillon, "")
        self.assertEqual(entree.copies, [])
        self.assertEqual(entree.nombreImages, 0)

    def test_creation_ou_edition(self) -> None:
        self.assertTrue(self.ouvrirCreation().estCreation)
        self.assertFalse(self.ouvrirEdition().estCreation)

    def test_est_creation_ne_bascule_pas_a_l_application(self) -> None:
        """Après appliquer(), le ticket est dans le dépôt : le test du dépôt se tromperait."""
        entree = self.ouvrirCreation()
        entree.session.appliquer()
        self.assertTrue(self.systeme.contient(entree.session.ticket))
        self.assertTrue(entree.estCreation)

    def test_texte_garde(self) -> None:
        entree = self.ouvrirCreation()
        entree.garderTexte("Le paiement échoue")
        entree.session.mettreEnPause()
        self.assertEqual(entree.texteBrouillon, "Le paiement échoue")
        entree.session.reprendre()
        self.assertEqual(entree.texteBrouillon, "Le paiement échoue")
        # Le texte gardé n'est pas une modification en attente.
        self.assertEqual(entree.session.modificationsEnAttente, [])

    def test_pile_alignee_sur_la_session(self) -> None:
        """L'undo retire de la pile la copie de l'ajout que la session vient d'annuler."""
        entree = self.ouvrirEdition()
        session = entree.session
        session.ajouterCommentaire("Premier")
        entree.empilerCopie(None)
        session.ajouterTexteSaisi("Deuxième")
        entree.empilerCopie(None)
        self.assertEqual(entree.copies, [None, None])
        self.assertEqual(len(entree.copies), len(session.modificationsEnAttente))

        libelle = session.annulerDerniere()
        self.assertIn("texte saisi", libelle)
        self.assertIsNone(entree.depilerCopie())
        self.assertEqual(len(entree.copies), len(session.modificationsEnAttente))

    def test_pile_rend_les_copies_dans_l_ordre_inverse(self) -> None:
        entree = self.ouvrirCreation()
        for copie in ("a.png", None, "b.png"):
            entree.empilerCopie(copie)
        self.assertEqual(entree.copies, ["a.png", None, "b.png"])
        self.assertEqual(entree.nombreImages, 2)
        self.assertEqual(entree.depilerCopie(), "b.png")
        self.assertEqual(entree.nombreImages, 1)
        self.assertIsNone(entree.depilerCopie())
        self.assertEqual(entree.depilerCopie(), "a.png")
        self.assertEqual(entree.copies, [])

    def test_undo_refuse_par_la_session_avant_de_toucher_la_pile(self) -> None:
        entree = self.ouvrirCreation()
        with self.assertRaises(SessionIndisponibleException):
            entree.session.annulerDerniere()
        self.assertEqual(entree.copies, [])

    def test_vider_rend_seulement_les_chemins(self) -> None:
        entree = self.ouvrirCreation()
        for copie in ("a.png", None, "b.png"):
            entree.empilerCopie(copie)
        self.assertEqual(entree.viderCopies(), ["a.png", "b.png"])
        self.assertEqual(entree.copies, [])
        self.assertEqual(entree.nombreImages, 0)
        self.assertEqual(entree.viderCopies(), [])

    def test_copies_en_lecture_seule(self) -> None:
        entree = self.ouvrirCreation()
        entree.copies.append("intrus.png")
        self.assertEqual(entree.copies, [])


class TestRegistre(TestAvecSessions):
    def test_identifiants_croissants_tous_acteurs_confondus(self) -> None:
        identifiants = [
            self.ouvrirCreation().id,
            self.ouvrirEdition().id,
            self.ouvrirCreation(self.abdoul).id,
        ]
        self.assertEqual(identifiants, [1, 2, 3])

    def test_trouver(self) -> None:
        entree = self.ouvrirCreation()
        self.assertIs(self.registre.trouver(self.julien.id, entree.id), entree)

    def test_brouillon_inconnu(self) -> None:
        self.ouvrirCreation()
        self.assertIsNone(self.registre.trouver(self.julien.id, 99))

    def test_brouillon_d_un_autre_acteur(self) -> None:
        entree = self.ouvrirCreation()
        self.assertIsNone(self.registre.trouver(self.abdoul.id, entree.id))
        self.assertIsNotNone(self.registre.trouver(self.julien.id, entree.id))

    def test_brouillons_d_un_acteur(self) -> None:
        premier = self.ouvrirCreation()
        autre = self.ouvrirCreation(self.abdoul)
        second = self.ouvrirEdition()
        self.assertEqual(self.registre.brouillonsDe(self.julien.id), [premier, second])
        self.assertEqual(self.registre.brouillonsDe(self.abdoul.id), [autre])
        self.assertEqual(self.registre.brouillonsDe(99), [])

    def test_pause_gardee(self) -> None:
        entree = self.ouvrirEdition()
        entree.session.mettreEnPause()
        self.assertIs(self.registre.trouver(self.julien.id, entree.id), entree)
        self.assertEqual(self.registre.brouillonsDe(self.julien.id), [entree])

    def test_session_appliquee_oubliee(self) -> None:
        for entree in (self.ouvrirCreation(), self.ouvrirEdition()):
            with self.subTest(creation=entree.estCreation):
                entree.session.appliquer()
                self.assertIsNone(self.registre.trouver(self.julien.id, entree.id))
        self.assertEqual(self.registre.brouillonsDe(self.julien.id), [])

    def test_session_abandonnee_oubliee(self) -> None:
        for entree in (self.ouvrirCreation(), self.ouvrirEdition()):
            with self.subTest(creation=entree.estCreation):
                entree.session.abandonner()
                self.assertIsNone(self.registre.trouver(self.julien.id, entree.id))
        self.assertEqual(self.registre.brouillonsDe(self.julien.id), [])

    def test_session_oubliee_ne_reste_pas_en_memoire(self) -> None:
        self.ouvrirCreation().session.abandonner()
        reste = self.ouvrirCreation()
        self.assertEqual(self.registre.brouillonsDe(self.julien.id), [reste])
        self.assertEqual(list(self.registre._entrees), [reste.id])

    def test_identifiant_jamais_repris(self) -> None:
        self.ouvrirCreation().session.abandonner()
        self.assertEqual(self.ouvrirCreation().id, 2)

    def test_edition_rouvrable_apres_application(self) -> None:
        """Le modèle autorise une nouvelle session : elle reçoit un nouvel identifiant."""
        entree = self.ouvrirEdition()
        ticket = entree.session.ticket
        entree.session.appliquer()
        session = self.julien.ouvrirSessionEdition(ticket)
        nouvelle = self.registre.ouvrir(session, self.julien, False)
        self.assertEqual(nouvelle.id, entree.id + 1)

    def test_deuxieme_session_refusee_par_le_modele_sans_rien_inscrire(self) -> None:
        entree = self.ouvrirEdition()
        with self.assertRaises(SessionIndisponibleException):
            self.registre.ouvrir(
                self.julien.ouvrirSessionEdition(entree.session.ticket), self.julien, False
            )
        self.assertEqual(self.registre.brouillonsDe(self.julien.id), [entree])

    def test_ticket_retire_garde_son_brouillon_ouvert(self) -> None:
        """Application refusée, et seul l'abandon range ses copies : il doit rester trouvable."""
        entree = self.ouvrirEdition()
        self.julien.supprimerTicket(entree.session.ticket)
        self.assertIs(self.registre.trouver(self.julien.id, entree.id), entree)
        with self.assertRaises(SessionIndisponibleException):
            entree.session.appliquer()
        self.assertIs(self.registre.trouver(self.julien.id, entree.id), entree)


class TestDansLeContexte(unittest.TestCase):
    def test_un_registre_par_contexte(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            sauvegarde = Path(dossier) / "sauvegarde.json"
            premier = ContexteServeur(cheminSauvegarde=sauvegarde)
            second = ContexteServeur(cheminSauvegarde=sauvegarde)
            self.assertIsInstance(premier.brouillons, RegistreBrouillons)
            self.assertIs(premier.brouillons, premier.brouillons)
            self.assertIsNot(premier.brouillons, second.brouillons)


if __name__ == "__main__":
    unittest.main()
