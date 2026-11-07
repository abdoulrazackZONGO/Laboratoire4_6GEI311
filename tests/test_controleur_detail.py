"""Tests de ControleurDetail (F6), sans fenêtre, contre la vraie API sur le serveur d'essai."""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

from ihm.controleurs.controleur_detail import ControleurDetail
from ihm.passerelle.erreurs import RessourceIntrouvable
from modele.enums import Statut
from tests.serveur_essai import ADMIN, JULIEN, MIKE, ServeurEssai

racineDepot = Path(__file__).resolve().parent.parent


class Observateur:
    """Note les notifications reçues de la source."""

    def __init__(self) -> None:
        self.modifies: list[int] = []
        self.retires: list[int] = []

    def ticketModifie(self, ticket) -> None:
        self.modifies.append(ticket.ticketID)

    def ticketAjoute(self, ticket) -> None:
        pass

    def ticketRetire(self, ticket) -> None:
        self.retires.append(ticket.ticketID)


class TestControleurDetail(unittest.TestCase):
    """Session Admin. Liste parcourue : les tickets 6, 7 et 10 des données de démonstration
    (6 et 7 sont OUVERT, donc supprimables par leur créateur : Julien et Mike).
    Le ticket 1 a une image et deux commentaires.
    """

    def setUp(self) -> None:
        self.serveur = ServeurEssai()
        self.addCleanup(self.serveur.fermer)
        _, self.client, self.source = self.serveur.session(ADMIN)
        self.tickets = [self.source.ticketParId(i) for i in (6, 7, 10)]
        self.observateur = Observateur()
        self.source.abonner(self.observateur)

    def controleur(self, index: int = 0) -> ControleurDetail:
        return ControleurDetail(self.client, self.source, self.tickets, index)

    def controleurTicket1(self) -> ControleurDetail:
        return ControleurDetail(self.client, self.source, [self.source.ticketParId(1)], 0)

    def supprimer(self, ticketId: int, acteurId: int) -> None:
        self.serveur.client(acteurId).supprimerTicket(ticketId)

    # ------------------------------------------------------------------ lecture

    def test_charger_lit_le_detail_du_ticket_affiche(self) -> None:
        controleur = self.controleurTicket1()
        ticket = controleur.charger()
        self.assertEqual(ticket.ticketID, 1)
        self.assertTrue(ticket.estDetaille)
        self.assertEqual(len(ticket.comments), 2)
        self.assertIs(controleur.ticket, ticket)

    def test_ticket_avant_charger_est_une_erreur_claire(self) -> None:
        with self.assertRaises(RuntimeError):
            self.controleur().ticket

    def test_index_hors_liste_refuse(self) -> None:
        with self.assertRaises(IndexError):
            self.controleur(3)

    def test_charger_ne_relit_pas_un_detail_deja_suivi(self) -> None:
        controleur = self.controleur()
        controleur.charger()
        avant = list(self.serveur.requetes)
        controleur.charger()
        self.assertEqual(self.serveur.requetes, avant)

    def test_ticket_inexistant_leve_ressource_introuvable(self) -> None:
        self.supprimer(6, JULIEN)
        with self.assertRaises(RessourceIntrouvable):
            self.controleur(0).charger()

    # ------------------------------------------------------------------ navigation

    def test_position_et_boutons(self) -> None:
        controleur = self.controleur(1)
        self.assertEqual((controleur.position, controleur.nombre), (2, 3))
        self.assertTrue(controleur.peutReculer and controleur.peutAvancer)
        controleur = self.controleur(0)
        self.assertFalse(controleur.peutReculer)
        controleur = self.controleur(2)
        self.assertFalse(controleur.peutAvancer)

    def test_aller_charge_le_voisin_et_oublie_l_ancien(self) -> None:
        controleur = self.controleur()
        controleur.charger()
        self.assertTrue(controleur.aller(1))
        self.assertEqual(controleur.ticket.ticketID, 7)
        self.assertEqual(controleur.position, 2)
        # Le ticket 6 n'est plus suivi en détail, le 7 l'est.
        self.assertFalse(self.source.ticketParId(6).estDetaille)
        self.assertTrue(self.source.ticketParId(7).estDetaille)

    def test_aller_au_bout_ne_fait_rien(self) -> None:
        controleur = self.controleur()
        controleur.charger()
        self.assertFalse(controleur.aller(-1))
        self.assertEqual(controleur.position, 1)

    def test_aller_garde_le_ticket_si_le_voisin_est_introuvable(self) -> None:
        controleur = self.controleur()
        controleur.charger()
        self.supprimer(7, MIKE)
        with self.assertRaises(RessourceIntrouvable):
            controleur.aller(1)
        self.assertEqual(controleur.ticket.ticketID, 6)
        self.assertEqual(controleur.position, 1)

    # ------------------------------------------------------------------ suivi des changements

    def test_changement_de_statut_fait_ailleurs_est_notifie_et_visible(self) -> None:
        controleur = self.controleur()
        controleur.charger()
        self.client.changerStatut(6, Statut.FERME)
        self.source.verifierVersion()
        self.assertEqual(self.observateur.modifies, [6])
        self.assertEqual(controleur.charger().status, Statut.FERME)

    def test_comparaison_par_identifiant_apres_rafraichissement(self) -> None:
        """L'objet reçu à la notification n'est plus celui chargé avant : seul l'id les relie."""
        controleur = self.controleur()
        ancien = controleur.charger()
        self.client.changerStatut(6, Statut.FERME)
        self.source.verifierVersion()
        nouveau = controleur.charger()
        self.assertIsNot(nouveau, ancien)
        self.assertTrue(controleur.estCourant(nouveau.ticketID))
        self.assertTrue(controleur.parcourt(nouveau.ticketID))

    def test_fermer_cesse_de_suivre_le_detail(self) -> None:
        controleur = self.controleur()
        controleur.charger()
        controleur.fermer()
        self.assertFalse(self.source.ticketParId(6).estDetaille)

    # ------------------------------------------------------------------ ticket retiré

    def test_retirer_le_ticket_affiche_passe_au_suivant(self) -> None:
        controleur = self.controleur()
        controleur.charger()
        self.assertTrue(controleur.retirer(6))
        self.assertEqual(controleur.nombre, 2)
        self.assertEqual(controleur.identifiantCourant, 7)
        with self.assertRaises(RuntimeError):
            controleur.ticket
        self.assertEqual(controleur.charger().ticketID, 7)

    def test_retirer_le_dernier_recule(self) -> None:
        controleur = self.controleur(2)
        controleur.charger()
        self.assertTrue(controleur.retirer(10))
        self.assertEqual(controleur.identifiantCourant, 7)

    def test_retirer_un_ticket_avant_le_courant_garde_le_courant(self) -> None:
        controleur = self.controleur(1)
        controleur.charger()
        self.assertFalse(controleur.retirer(6))
        self.assertEqual(controleur.identifiantCourant, 7)
        self.assertEqual(controleur.position, 1)
        self.assertEqual(controleur.ticket.ticketID, 7)

    def test_retirer_le_dernier_ticket_vide_la_liste(self) -> None:
        controleur = ControleurDetail(self.client, self.source, self.tickets[:1], 0)
        controleur.charger()
        controleur.retirer(6)
        self.assertTrue(controleur.estVide)
        controleur.fermer()  # sans erreur

    def test_suppression_sur_le_serveur_est_notifiee_comme_retrait(self) -> None:
        controleur = self.controleur()
        controleur.charger()
        self.supprimer(6, JULIEN)
        self.source.verifierVersion()
        self.assertEqual(self.observateur.retires, [6])

    # ------------------------------------------------------------------ images

    def test_les_images_sont_telechargees_par_l_api_puis_gardees(self) -> None:
        controleur = self.controleurTicket1()
        image = next(e for e in controleur.charger().description.elements if e.typeArtefact == "image")
        octets = controleur.octetsImage(image)
        self.assertTrue(octets.startswith(b"\x89PNG"))
        self.assertIn(("GET", image.url), self.serveur.requetes)
        avant = len(self.serveur.requetes)
        self.assertEqual(controleur.octetsImage(image), octets)
        self.assertEqual(len(self.serveur.requetes), avant)

    def test_octetsImage_refuse_un_element_sans_url(self) -> None:
        controleur = self.controleurTicket1()
        texte = controleur.charger().description.elements[0]
        with self.assertRaises(ValueError):
            controleur.octetsImage(texte)


class TestDependances(unittest.TestCase):
    def test_le_controleur_n_importe_ni_tkinter_ni_le_modele_metier(self) -> None:
        code = (
            "import sys; import ihm.controleurs.controleur_detail; "
            "interdits = [m for m in ('tkinter', 'flask', 'acteurs', 'sessions', 'persistance') "
            "if m in sys.modules]; "
            "print(','.join(interdits)); sys.exit(1 if interdits else 0)"
        )
        resultat = subprocess.run(
            [sys.executable, "-c", code], cwd=racineDepot, capture_output=True, text=True
        )
        self.assertEqual(resultat.returncode, 0, resultat.stdout + resultat.stderr)


if __name__ == "__main__":
    unittest.main()
