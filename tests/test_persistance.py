"""Tests de M10 : persistance JSON (FabriqueEtat, Ticket.restaurer, DepotJSON, annuaire).

Lancer depuis la racine du dépôt :  python -m unittest discover -s tests -t . -v
"""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

from acteurs.admin import Admin
from acteurs.user import User
from description.fabrique_description import FabriqueDescription
from etats.fabrique_etat import FabriqueEtat
from modele.enums import Priorite, Statut
from modele.exceptions import TransitionInvalideException
from modele.observateur import ObservateurTickets
from modele.systeme_tickets import SystemeTickets
from modele.ticket import Ticket
from persistance.depot_json import DepotJSON, PersistanceException

RESSOURCES = Path(__file__).resolve().parent.parent / "ressources"


def element(type_artefact: str, chemin: Path):
    e = FabriqueDescription.creer(type_artefact, str(chemin))
    e.traiter()
    return e


def ticket(systeme: SystemeTickets, ticketID: int) -> Ticket:
    """Le dépôt garde l'ordre de création, pas l'ordre des numéros : on cherche par numéro."""
    return next(t for t in systeme.tickets if t.ticketID == ticketID)


def saisie(texte: str):
    e = FabriqueDescription.creerSaisie(texte)
    e.traiter()
    return e


class TestFabriqueEtat(unittest.TestCase):
    def test_couvre_tous_les_statuts(self) -> None:
        """Un nouveau statut sans état correspondant serait détecté ici."""
        for statut in Statut:
            with self.subTest(statut=statut.name):
                self.assertIs(FabriqueEtat.creer(statut).nom, statut)

    def test_nouvelle_instance_a_chaque_appel(self) -> None:
        self.assertIsNot(FabriqueEtat.creer(Statut.OUVERT), FabriqueEtat.creer(Statut.OUVERT))


class TestAnnuaire(unittest.TestCase):
    def setUp(self) -> None:
        self.systeme = SystemeTickets()
        self.admin = Admin(1, "Admin", "admin@uqac.ca", self.systeme)

    def test_inscription_et_recherche(self) -> None:
        self.systeme.inscrireUtilisateur(self.admin)
        self.assertEqual(self.systeme.utilisateurs, [self.admin])
        self.assertIs(self.systeme.utilisateurParId(1), self.admin)
        self.assertIsNone(self.systeme.utilisateurParId(99))

    def test_inscription_idempotente(self) -> None:
        self.systeme.inscrireUtilisateur(self.admin)
        self.systeme.inscrireUtilisateur(self.admin)
        self.assertEqual(len(self.systeme.utilisateurs), 1)

    def test_identifiant_deja_utilise(self) -> None:
        self.systeme.inscrireUtilisateur(self.admin)
        with self.assertRaises(ValueError):
            self.systeme.inscrireUtilisateur(User(1, "Autre", "autre@uqac.ca", self.systeme))


class TestDepotJSON(unittest.TestCase):
    """Aller-retour : ce qui est rechargé est identique à ce qui a été sauvegardé."""

    def setUp(self) -> None:
        self.dossier = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dossier, ignore_errors=True)
        self.depot = DepotJSON(self.dossier / "sauvegarde.json")

        s = self.systeme = SystemeTickets()
        self.admin = Admin(1, "Ambroise Fleury", "ambroise@uqac.ca", s)
        self.abdoul = User(2, "Abdoul Razack", "abdoul@uqac.ca", s)
        self.julien = User(3, "T Julien", "julien@uqac.ca", s)
        self.mike = User(4, "Mike Tonny", "mike@uqac.ca", s)
        for u in (self.admin, self.abdoul, self.julien, self.mike):
            s.inscrireUtilisateur(u)

        # T1 : description complète, commentaires, cycle complet jusqu'à TERMINE.
        self.t1 = Ticket(1, "Problème d'accès à la page « Connexion »", Priorite.HAUTE)
        self.abdoul.createTicket(self.t1)
        self.t1.ajouterElementDescription(element("texte", RESSOURCES / "description_bug.txt"))
        self.t1.ajouterElementDescription(element("image", RESSOURCES / "capture_ecran.png"))
        self.t1.ajouterElementDescription(saisie("Le bug survient après la mise à jour."))
        self.t1.addComment("Reproduit sur Chrome", self.abdoul)
        self.t1.addComment("Assigné à Mike", self.admin)
        self.admin.assignTicket(self.t1, self.mike)
        self.mike.soumettreValidation(self.t1)
        self.admin.validerTicket(self.t1)
        # T2 : assigné. T3 : fermé. T4 : ouvert. T5 : désassigné (déjà assigné, plus d'assigné).
        self.t2 = Ticket(2, "Erreur d'affichage", Priorite.MOYENNE)
        self.t3 = Ticket(3, "Export CSV", Priorite.BASSE)
        self.t4 = Ticket(4, "Lenteur", Priorite.CRITIQUE)
        self.t5 = Ticket(5, "Police illisible", Priorite.BASSE)
        for t in (self.t2, self.t4, self.t5):
            self.abdoul.createTicket(t)
        self.julien.createTicket(self.t3)
        self.admin.assignTicket(self.t2, self.julien)
        self.admin.closeTicket(self.t3)
        self.admin.assignTicket(self.t5, self.mike)
        self.admin.desassignerTicket(self.t5)

    def recharger(self) -> SystemeTickets:
        self.depot.sauvegarder(self.systeme)
        return DepotJSON(self.depot.chemin).charger()

    def test_existe(self) -> None:
        self.assertFalse(self.depot.existe())
        self.depot.sauvegarder(self.systeme)
        self.assertTrue(self.depot.existe())

    def test_aller_retour_des_utilisateurs(self) -> None:
        charge = self.recharger()
        resume = [(u.id, u.name, u.email, u.role) for u in charge.utilisateurs]
        attendu = [(u.id, u.name, u.email, u.role) for u in self.systeme.utilisateurs]
        self.assertEqual(resume, attendu)
        self.assertIsInstance(charge.utilisateurParId(1), Admin)

    def test_aller_retour_des_tickets(self) -> None:
        charge = self.recharger()
        self.assertEqual(len(charge.tickets), 5)
        for avant, apres in zip(self.systeme.tickets, charge.tickets):
            with self.subTest(ticket=avant.ticketID):
                self.assertEqual(apres.ticketID, avant.ticketID)
                self.assertEqual(apres.title, avant.title)
                self.assertIs(apres.priority, avant.priority)
                self.assertIs(apres.status, avant.status)
                self.assertEqual(apres.creationDate, avant.creationDate)
                self.assertEqual(apres.updateDate, avant.updateDate)
                self.assertEqual(apres.creator.id, avant.creator.id)
                self.assertEqual(
                    apres.assignedUser.id if apres.assignedUser else None,
                    avant.assignedUser.id if avant.assignedUser else None,
                )
                self.assertEqual(apres.aDejaEteAssigne, avant.aDejaEteAssigne)
                self.assertEqual(
                    [(c.texte, c.auteur.id, c.date) for c in apres.comments],
                    [(c.texte, c.auteur.id, c.date) for c in avant.comments],
                )
                self.assertEqual(
                    [e.resume for e in apres.description.elements],
                    [e.resume for e in avant.description.elements],
                )

    def test_texte_saisi_et_contenus(self) -> None:
        t1 = ticket(self.recharger(), 1)
        texte, image, tape = t1.description.elements
        self.assertEqual(texte.typeArtefact, "texte")
        self.assertEqual(texte.contenu, (RESSOURCES / "description_bug.txt").read_text(encoding="utf-8"))
        self.assertEqual(image.typeArtefact, "image")
        self.assertEqual(tape.contenu, "Le bug survient après la mise à jour.")

    def test_objets_relies_apres_chargement(self) -> None:
        """Les utilisateurs rechargés sont les mêmes objets partout, reliés au nouveau dépôt."""
        charge = self.recharger()
        abdoul = charge.utilisateurParId(2)
        t1 = ticket(charge, 1)
        self.assertIs(t1.creator, abdoul)
        self.assertIs(t1.comments[0].auteur, abdoul)
        self.assertEqual([t.ticketID for t in abdoul.mesTickets()], [1, 2, 4, 5])
        self.assertEqual([t.ticketID for t in charge.ticketsAssignesA(charge.utilisateurParId(3))], [2])

    def test_machine_a_etats_apres_chargement(self) -> None:
        charge = self.recharger()
        t1, t2, t3 = (ticket(charge, i) for i in (1, 2, 3))
        julien = charge.utilisateurParId(3)
        self.assertEqual(t2.transitionsPermises, frozenset({Statut.ASSIGNE, Statut.OUVERT, Statut.VALIDATION, Statut.FERME}))
        julien.soumettreValidation(t2)
        self.assertIs(t2.status, Statut.VALIDATION)
        with self.assertRaises(TransitionInvalideException):
            charge.utilisateurParId(1).closeTicket(t3)  # FERME reste définitif
        self.assertEqual(t1.transitionsPermises, frozenset())

    def test_relais_apres_chargement(self) -> None:
        charge = self.recharger()

        class Espion(ObservateurTickets):
            def __init__(self) -> None:
                self.recus: list[int] = []

            def ticketModifie(self, ticket: Ticket) -> None:
                self.recus.append(ticket.ticketID)

        espion = Espion()
        charge.abonner(espion)
        ticket(charge, 4).addComment("après rechargement", charge.utilisateurParId(2))
        self.assertEqual(espion.recus, [4])

    def test_dates_anciennes_conservees(self) -> None:
        """Un ticket rechargé garde sa date de création, au lieu de prendre celle du jour."""
        self.depot.sauvegarder(self.systeme)
        donnees = json.loads(self.depot.chemin.read_text(encoding="utf-8"))
        donnees["tickets"][0]["creationDate"] = "2026-10-01"
        self.depot.chemin.write_text(json.dumps(donnees), encoding="utf-8")
        self.assertEqual(ticket(self.depot.charger(), 1).creationDate, date(2026, 10, 1))

    def test_fichier_lisible(self) -> None:
        self.depot.sauvegarder(self.systeme)
        texte = self.depot.chemin.read_text(encoding="utf-8")
        self.assertIn('"version": 1', texte)
        self.assertIn("Problème d'accès", texte)  # accents écrits en clair
        self.assertFalse(self.depot.chemin.with_name("sauvegarde.json.tmp").exists())

    def test_admin_sans_ticket_conserve(self) -> None:
        systeme = SystemeTickets()
        systeme.inscrireUtilisateur(Admin(9, "Seul", "seul@uqac.ca", systeme))
        self.depot.sauvegarder(systeme)
        self.assertEqual([u.name for u in self.depot.charger().utilisateurs], ["Seul"])

    def test_utilisateur_hors_annuaire_sauvegarde(self) -> None:
        """Un créateur non inscrit dans l'annuaire n'est pas perdu pour autant."""
        systeme = SystemeTickets()
        createur = User(7, "Non inscrit", "ni@uqac.ca", systeme)
        createur.createTicket(Ticket(1, "T", Priorite.BASSE))
        self.depot.sauvegarder(systeme)
        charge = self.depot.charger()
        self.assertEqual(charge.tickets[0].creator.name, "Non inscrit")

    def test_artefact_introuvable_ignore_avec_avertissement(self) -> None:
        image = self.dossier / "temporaire.png"
        shutil.copy(RESSOURCES / "capture_ecran.png", image)
        self.t4.ajouterElementDescription(element("image", image))
        self.t4.ajouterElementDescription(saisie("Texte conservé"))
        self.depot.sauvegarder(self.systeme)
        image.unlink()
        charge = self.depot.charger()
        t4 = ticket(charge, 4)
        self.assertEqual([e.typeArtefact for e in t4.description.elements], ["texte"])
        self.assertEqual(len(self.depot.avertissements), 1)
        self.assertIn("#4", self.depot.avertissements[0])

    def test_fichier_corrompu(self) -> None:
        self.depot.chemin.write_text("{ ceci n'est pas du JSON", encoding="utf-8")
        with self.assertRaises(PersistanceException):
            self.depot.charger()

    def test_version_inconnue(self) -> None:
        self.depot.chemin.write_text('{"version": 99}', encoding="utf-8")
        with self.assertRaises(PersistanceException):
            self.depot.charger()

    def test_reference_incoherente(self) -> None:
        self.depot.sauvegarder(self.systeme)
        donnees = json.loads(self.depot.chemin.read_text(encoding="utf-8"))
        donnees["tickets"][0]["creator"] = 999
        self.depot.chemin.write_text(json.dumps(donnees), encoding="utf-8")
        with self.assertRaises(PersistanceException):
            self.depot.charger()

    def test_fichier_absent(self) -> None:
        with self.assertRaises(FileNotFoundError):
            self.depot.charger()


if __name__ == "__main__":
    unittest.main()
