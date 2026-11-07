"""Tests de C2 : objets de lecture et source observable, sans serveur ni Tkinter.

Les JSON viennent des exemples de openapi.yaml (repris de test_passerelle_client). La source
est branchée sur un faux serveur : on y ajoute, retire ou modifie des tickets, puis on vérifie
la notification reçue par un observateur espion.
"""
from __future__ import annotations

import copy
import os
import subprocess
import sys
import unittest
from datetime import date
from typing import Any

from ihm.passerelle.erreurs import ReponseInvalide, RessourceIntrouvable, ServeurInjoignable
from ihm.passerelle.objets_lecture import ActeurLu, BrouillonLu, RapportLu, TicketLu, TicketRefLu
from ihm.passerelle.source_tickets import SourceTickets
from modele.enums import Priorite, Statut
from modele.observateur import ObservateurTickets
from tests.test_passerelle_client import (
    EXEMPLE_ACTEUR,
    EXEMPLE_ACTEURS,
    EXEMPLE_BROUILLON,
    EXEMPLE_RAPPORT_CREATION,
    EXEMPLE_RAPPORT_LOT,
    EXEMPLE_TICKET_DETAIL,
    EXEMPLE_TICKET_RESUME,
    clientEssai,
    reponseJSON,
)

ObjetJSON = dict[str, Any]
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def avec(donnees: ObjetJSON, **changements: Any) -> ObjetJSON:
    """Copie profonde d'un exemple du contrat, avec quelques champs remplacés."""
    copie = copy.deepcopy(donnees)
    copie.update(changements)
    return copie


def sansCle(donnees: ObjetJSON, cle: str) -> ObjetJSON:
    copie = copy.deepcopy(donnees)
    del copie[cle]
    return copie


# ------------------------------------------------------------------ doublures


class FauxServeur:
    """Joue le serveur derrière la source : un compteur de version et des tickets détaillés.

    listerTickets rend les résumés (le détail sans commentaires ni description), comme l'API.
    Chaque appel est noté ; pannes[nomAppel] fait échouer cet appel.
    """

    def __init__(self) -> None:
        self.version: int = 0
        self.tickets: dict[int, ObjetJSON] = {}
        self.appels: list[str] = []
        self.pannes: dict[str, Exception] = {}

    # Changements côté serveur : chacun incrémente la version, comme le ferait l'API.

    def ajouter(self, id: int, **champs: Any) -> None:
        self.tickets[id] = avec(EXEMPLE_TICKET_DETAIL, **{"id": id, "titre": f"Ticket {id}", **champs})
        self.version += 1

    def modifier(self, id: int, **champs: Any) -> None:
        self.tickets[id].update(champs)
        self.version += 1

    def retirer(self, id: int) -> None:
        del self.tickets[id]
        self.version += 1

    # Ce que la source appelle (même noms que ClientAPI).

    def lireVersion(self) -> int:
        self._appel("version")
        return self.version

    def listerTickets(self) -> list[ObjetJSON]:
        self._appel("tickets")
        return [
            {cle: copy.deepcopy(valeur) for cle, valeur in ticket.items()
             if cle not in ("commentaires", "description")}
            for _, ticket in sorted(self.tickets.items())
        ]

    def lireTicket(self, ticketId: int) -> ObjetJSON:
        self._appel(f"ticket/{ticketId}")
        if ticketId not in self.tickets:
            raise RessourceIntrouvable(f"Le ticket {ticketId} n'existe pas", 404)
        return copy.deepcopy(self.tickets[ticketId])

    def _appel(self, nom: str) -> None:
        self.appels.append(nom)
        if nom in self.pannes:
            raise self.pannes[nom]


class Espion(ObservateurTickets):
    """Observateur qui note chaque notification reçue : (genre, ticketID)."""

    def __init__(self) -> None:
        self.evenements: list[tuple[str, int]] = []
        self.recus: list[TicketLu] = []

    def ticketAjoute(self, ticket: TicketLu) -> None:  # type: ignore[override]
        self._noter("ajout", ticket)

    def ticketRetire(self, ticket: TicketLu) -> None:  # type: ignore[override]
        self._noter("retrait", ticket)

    def ticketModifie(self, ticket: TicketLu) -> None:  # type: ignore[override]
        self._noter("modification", ticket)

    def _noter(self, genre: str, ticket: TicketLu) -> None:
        self.evenements.append((genre, ticket.ticketID))
        self.recus.append(ticket)


class ObservateurEnPanne(ObservateurTickets):
    def ticketAjoute(self, ticket: TicketLu) -> None:  # type: ignore[override]
        raise RuntimeError("bogue d'une fenêtre")


def sourceChargee(*ids: int) -> tuple[SourceTickets, FauxServeur, Espion]:
    """Source déjà chargée avec ces tickets, un espion abonné, appels remis à zéro."""
    serveur = FauxServeur()
    for id in ids:
        serveur.ajouter(id)
    source = SourceTickets(serveur)
    source.rafraichir()
    espion = Espion()
    source.abonner(espion)
    serveur.appels.clear()
    return source, serveur, espion


# ------------------------------------------------------------------ objets de lecture


class TestTicketLu(unittest.TestCase):
    def test_resumeAvecLesProprietesDuModele(self) -> None:
        ticket = TicketLu.depuisJSON(EXEMPLE_TICKET_RESUME)
        self.assertEqual(ticket.ticketID, 2)
        self.assertEqual(ticket.title, "Erreur d'affichage mobile")
        self.assertIs(ticket.priority, Priorite.MOYENNE)
        self.assertIs(ticket.status, Statut.ASSIGNE)
        self.assertEqual(ticket.creator.name, "Abdoul Razack")
        self.assertEqual(ticket.assignedUser.name, "Hein Tommy")
        self.assertEqual(ticket.creationDate, date(2026, 10, 20))
        self.assertEqual(ticket.updateDate, date(2026, 10, 20))
        self.assertTrue(ticket.aDejaEteAssigne)
        self.assertEqual(
            ticket.transitionsPermises,
            frozenset({Statut.OUVERT, Statut.ASSIGNE, Statut.VALIDATION, Statut.FERME}),
        )
        self.assertTrue(ticket.transitionPossible(Statut.FERME))
        self.assertFalse(ticket.transitionPossible(Statut.TERMINE))
        self.assertEqual(ticket.nombreCommentaires, 0)

    def test_resumeSansCommentairesNiDescription(self) -> None:
        ticket = TicketLu.depuisJSON(EXEMPLE_TICKET_RESUME)
        self.assertFalse(ticket.estDetaille)
        with self.assertRaises(RuntimeError):
            ticket.comments
        with self.assertRaises(RuntimeError):
            ticket.description

    def test_detailAvecCommentairesEtDescription(self) -> None:
        ticket = TicketLu.depuisJSON(EXEMPLE_TICKET_DETAIL)
        self.assertTrue(ticket.estDetaille)
        self.assertEqual(len(ticket.comments), 2)
        commentaire = ticket.comments[0]
        self.assertEqual(commentaire.texte, "Le bug se reproduit sur Chrome et Firefox.")
        self.assertEqual(commentaire.auteur.name, "Abdoul Razack")
        self.assertEqual(commentaire.date, date(2026, 10, 20))

        self.assertEqual(ticket.description.nombreElements, 2)
        texte, image = ticket.description.elements
        # Un texte saisi est un "texte" pour la vue, comme dans le modèle.
        self.assertEqual(texte.typeArtefact, "texte")
        self.assertEqual(texte.nom, "texte saisi")
        self.assertTrue(texte.contenu.startswith("Bug : impossible"))
        self.assertIsNone(texte.url)
        self.assertEqual(image.typeArtefact, "image")
        self.assertEqual(image.url, "/ticket/1/image/demo_connexion.png")
        self.assertEqual(image.resume, "[Image] demo_connexion.png (757 octets)")
        self.assertIsNone(image.contenu)

    def test_listesRenduesEnCopie(self) -> None:
        ticket = TicketLu.depuisJSON(EXEMPLE_TICKET_DETAIL)
        ticket.comments.clear()
        ticket.description.elements.clear()
        self.assertEqual(len(ticket.comments), 2)
        self.assertEqual(ticket.description.nombreElements, 2)

    def test_sansCreateurNiAssigne(self) -> None:
        ticket = TicketLu.depuisJSON(
            avec(EXEMPLE_TICKET_RESUME, createur=None, assigne=None, dejaAssigne=False)
        )
        self.assertIsNone(ticket.creator)
        self.assertIsNone(ticket.assignedUser)
        self.assertFalse(ticket.aDejaEteAssigne)

    def test_comparaisonParIdentifiant(self) -> None:
        # Deux lectures du même ticket donnent deux objets distincts mais égaux.
        avant = TicketLu.depuisJSON(EXEMPLE_TICKET_RESUME)
        apres = TicketLu.depuisJSON(avec(EXEMPLE_TICKET_RESUME, statut="FERME"))
        autre = TicketLu.depuisJSON(avec(EXEMPLE_TICKET_RESUME, id=3))
        self.assertIsNot(avant, apres)
        self.assertEqual(avant, apres)
        self.assertEqual(hash(avant), hash(apres))
        self.assertEqual(len({avant, apres}), 1)
        self.assertIn(apres, [avant])
        self.assertNotEqual(avant, autre)
        self.assertNotEqual(avant, 2)
        # Un ticket réduit (celui d'un brouillon) égale le ticket complet de même id.
        self.assertEqual(TicketRefLu(2, "Erreur d'affichage mobile", Priorite.MOYENNE), avant)

    def test_jsonHorsContrat(self) -> None:
        cas: dict[str, Any] = {
            "id manquant": sansCle(EXEMPLE_TICKET_RESUME, "id"),
            "id booléen": avec(EXEMPLE_TICKET_RESUME, id=True),
            "id texte": avec(EXEMPLE_TICKET_RESUME, id="2"),
            "priorité inconnue": avec(EXEMPLE_TICKET_RESUME, priorite="URGENTE"),
            "statut en minuscules": avec(EXEMPLE_TICKET_RESUME, statut="assigne"),
            "date illisible": avec(EXEMPLE_TICKET_RESUME, dateCreation="20/10/2026"),
            "transition inconnue": avec(EXEMPLE_TICKET_RESUME, transitionsPermises=["PERDU"]),
            "créateur réduit à un nom": avec(EXEMPLE_TICKET_RESUME, createur="Abdoul Razack"),
            "commentaires pas en liste": avec(EXEMPLE_TICKET_DETAIL, commentaires={}),
            "élément de type inconnu": avec(
                EXEMPLE_TICKET_DETAIL,
                description=[{"type": "audio", "nom": "son.mp3", "resume": "[Audio]"}],
            ),
            "liste au lieu d'un objet": [EXEMPLE_TICKET_RESUME],
            "null": None,
        }
        for nom, donnees in cas.items():
            with self.subTest(nom), self.assertRaises(ReponseInvalide):
                TicketLu.depuisJSON(donnees)


class TestActeurLu(unittest.TestCase):
    def test_acteurComplet(self) -> None:
        acteur = ActeurLu.depuisJSON(EXEMPLE_ACTEUR)
        self.assertEqual((acteur.id, acteur.name), (1, "Ambroise Fleury"))
        self.assertEqual(acteur.email, "ambroise@uqac.ca")
        self.assertEqual(acteur.role, "Admin")

    def test_referenceSansCourrielNiRole(self) -> None:
        acteur = ActeurLu.depuisJSON({"id": 2, "nom": "Abdoul Razack"})
        self.assertIsNone(acteur.email)
        self.assertIsNone(acteur.role)

    def test_comparaisonParIdentifiant(self) -> None:
        complet = ActeurLu.depuisJSON(EXEMPLE_ACTEURS[0])
        reference = ActeurLu.depuisJSON({"id": 2, "nom": "Abdoul Razack"})
        self.assertEqual(complet, reference)
        self.assertEqual(len({complet, reference}), 1)
        self.assertNotEqual(complet, ActeurLu.depuisJSON(EXEMPLE_ACTEURS[1]))
        # Un acteur et un ticket de même numéro ne sont pas égaux.
        self.assertNotEqual(complet, TicketRefLu(2, "Titre", Priorite.BASSE))

    def test_jsonHorsContrat(self) -> None:
        for donnees in ({"id": 2}, {"id": "2", "nom": "X"}, {"id": 2, "nom": "X", "role": 3}):
            with self.subTest(donnees), self.assertRaises(ReponseInvalide):
                ActeurLu.depuisJSON(donnees)


class TestBrouillonEtRapport(unittest.TestCase):
    def test_brouillonDeCreation(self) -> None:
        brouillon = BrouillonLu.depuisJSON(EXEMPLE_BROUILLON)
        self.assertEqual(brouillon.id, 1)
        self.assertTrue(brouillon.estCreation)
        self.assertEqual(brouillon.libelle, "Session de création")
        self.assertEqual(brouillon.ticket.ticketID, 11)
        self.assertEqual(brouillon.ticket.title, "Paiement refusé")
        self.assertIs(brouillon.ticket.priority, Priorite.MOYENNE)
        self.assertEqual(brouillon.proprietaire.name, "T Julien")
        self.assertTrue(brouillon.estOuverte)
        self.assertFalse(brouillon.estEnPause)
        self.assertEqual(brouillon.modificationsEnAttente, [])
        self.assertEqual(brouillon.nombreImages, 0)
        self.assertEqual(brouillon.texteBrouillon, "")

    def test_brouillonDEditionComparéParIdentifiant(self) -> None:
        edition = BrouillonLu.depuisJSON(
            avec(EXEMPLE_BROUILLON, type="edition", enPause=True, texteBrouillon="à finir")
        )
        self.assertFalse(edition.estCreation)
        self.assertTrue(edition.estEnPause)
        self.assertEqual(edition, BrouillonLu.depuisJSON(EXEMPLE_BROUILLON))
        self.assertNotEqual(edition, BrouillonLu.depuisJSON(avec(EXEMPLE_BROUILLON, id=2)))

    def test_brouillonHorsContrat(self) -> None:
        cas = (
            avec(EXEMPLE_BROUILLON, type="suppression"),
            avec(EXEMPLE_BROUILLON, modificationsEnAttente=[1, 2]),
            sansCle(EXEMPLE_BROUILLON, "proprietaire"),
        )
        for donnees in cas:
            with self.subTest(donnees), self.assertRaises(ReponseInvalide):
                BrouillonLu.depuisJSON(donnees)

    def test_rapportDeCreation(self) -> None:
        rapport = RapportLu.depuisJSON(EXEMPLE_RAPPORT_CREATION)
        self.assertEqual(rapport.libelle, "Session de création")
        self.assertEqual(rapport.ticketId, 11)
        self.assertEqual(rapport.nombreSucces, 1)
        self.assertEqual(rapport.refus, [])

    def test_rapportDeLot(self) -> None:
        rapport = RapportLu.depuisJSON(EXEMPLE_RAPPORT_LOT)
        self.assertIsNone(rapport.ticketId)
        self.assertEqual(rapport.nombreSucces, 2)
        self.assertEqual(rapport.nombreRefus, 1)
        # Mêmes couples (opération, motif) que sessions.RapportExecution.
        operation, motif = rapport.refus[0]
        self.assertEqual(operation, "Assigner le ticket #3 à Mike Tonny")
        self.assertTrue(motif.startswith("Transition invalide"))
        rapport.succes.clear()
        self.assertEqual(rapport.nombreSucces, 2)

    def test_rapportHorsContrat(self) -> None:
        cas = (
            avec(EXEMPLE_RAPPORT_LOT, nombreRefus=0),
            avec(EXEMPLE_RAPPORT_LOT, refus=[{"operation": "Assigner"}]),
            sansCle(EXEMPLE_RAPPORT_CREATION, "ticketId"),
        )
        for donnees in cas:
            with self.subTest(donnees), self.assertRaises(ReponseInvalide):
                RapportLu.depuisJSON(donnees)


# ------------------------------------------------------------------ source observable


class TestSourceTickets(unittest.TestCase):
    def test_avantLePremierChargement(self) -> None:
        source = SourceTickets(FauxServeur())
        self.assertIsNone(source.version)
        self.assertEqual(source.tickets, [])
        self.assertIsNone(source.ticketParId(1))

    def test_premierChargement(self) -> None:
        serveur = FauxServeur()
        for id in (3, 1, 2):
            serveur.ajouter(id)
        source = SourceTickets(serveur)
        espion = Espion()
        source.abonner(espion)
        source.rafraichir()
        self.assertEqual(espion.evenements, [("ajout", 1), ("ajout", 2), ("ajout", 3)])
        self.assertEqual([t.ticketID for t in source.tickets], [1, 2, 3])
        self.assertEqual(source.version, serveur.version)
        self.assertEqual(source.ticketParId(2).title, "Ticket 2")

    def test_ticketAjouteCoteServeur(self) -> None:
        source, serveur, espion = sourceChargee(1, 2)
        serveur.ajouter(3, titre="Nouveau")
        self.assertTrue(source.verifierVersion())
        self.assertEqual(espion.evenements, [("ajout", 3)])
        self.assertEqual(espion.recus[0].title, "Nouveau")
        self.assertEqual(source.ticketParId(3).title, "Nouveau")

    def test_ticketRetireCoteServeur(self) -> None:
        source, serveur, espion = sourceChargee(1, 2)
        serveur.retirer(2)
        self.assertTrue(source.verifierVersion())
        self.assertEqual(espion.evenements, [("retrait", 2)])
        self.assertIsNone(source.ticketParId(2))
        self.assertEqual([t.ticketID for t in source.tickets], [1])

    def test_ticketModifieCoteServeur(self) -> None:
        source, serveur, espion = sourceChargee(1, 2, 3)
        serveur.modifier(2, statut="FERME", transitionsPermises=[])
        self.assertTrue(source.verifierVersion())
        self.assertEqual(espion.evenements, [("modification", 2)])
        self.assertIs(espion.recus[0].status, Statut.FERME)
        self.assertIs(source.ticketParId(2).status, Statut.FERME)

    def test_changementSansNouvelleDateDeMiseAJour(self) -> None:
        # dateMiseAJour n'a que la précision du jour : on compare la représentation entière.
        source, serveur, espion = sourceChargee(1)
        serveur.modifier(1, assigne={"id": 5, "nom": "Hein Tommy"}, nombreCommentaires=3)
        source.verifierVersion()
        self.assertEqual(espion.evenements, [("modification", 1)])

    def test_plusieursChangementsDUnCoup(self) -> None:
        source, serveur, espion = sourceChargee(1, 2, 3)
        serveur.retirer(1)
        serveur.ajouter(4)
        serveur.modifier(2, titre="Titre corrigé")
        source.verifierVersion()
        self.assertEqual(
            espion.evenements, [("retrait", 1), ("ajout", 4), ("modification", 2)]
        )

    def test_versionInchangeeUnSeulAppel(self) -> None:
        source, serveur, espion = sourceChargee(1, 2)
        self.assertFalse(source.verifierVersion())
        self.assertEqual(serveur.appels, ["version"])
        self.assertEqual(espion.evenements, [])

    def test_versionChangeeSansDifference(self) -> None:
        source, serveur, espion = sourceChargee(1, 2)
        serveur.version += 1
        self.assertTrue(source.verifierVersion())
        self.assertEqual(espion.evenements, [])
        self.assertEqual(source.version, serveur.version)
        self.assertFalse(source.verifierVersion())

    def test_rafraichirRelitMemeSansNouvelleVersion(self) -> None:
        source, serveur, _ = sourceChargee(1)
        source.rafraichir()
        self.assertEqual(serveur.appels, ["version", "tickets"])

    def test_desabonnementArreteLesNotifications(self) -> None:
        source, serveur, espion = sourceChargee(1)
        source.desabonner(espion)
        serveur.ajouter(2)
        source.verifierVersion()
        self.assertEqual(espion.evenements, [])


class TestDetailSuivi(unittest.TestCase):
    def test_lireDetail(self) -> None:
        source, serveur, espion = sourceChargee(1, 2)
        ticket = source.lireDetail(1)
        self.assertTrue(ticket.estDetaille)
        self.assertEqual(len(ticket.comments), 2)
        # La source fournit désormais l'objet le plus complet connu.
        self.assertTrue(source.ticketParId(1).estDetaille)
        self.assertTrue(source.tickets[0].estDetaille)
        self.assertFalse(source.ticketParId(2).estDetaille)
        self.assertEqual(espion.evenements, [])

    def test_changementDeDescriptionVuParLeDetailSuivi(self) -> None:
        # Le résumé ne montre pas la description : seul le détail suivi la voit changer.
        source, serveur, espion = sourceChargee(1, 2)
        source.lireDetail(1)
        for id in (1, 2):
            description = serveur.tickets[id]["description"] + [
                {"type": "video", "nom": "demo.mp4", "resume": "[Vidéo] demo.mp4"}
            ]
            serveur.modifier(id, description=description)
        source.verifierVersion()
        self.assertEqual(espion.evenements, [("modification", 1)])
        self.assertEqual(espion.recus[0].description.nombreElements, 3)
        self.assertIn("ticket/1", serveur.appels)
        self.assertNotIn("ticket/2", serveur.appels)

    def test_oublierDetail(self) -> None:
        source, serveur, _ = sourceChargee(1)
        source.lireDetail(1)
        source.oublierDetail(1)
        source.oublierDetail(1)  # sans effet la seconde fois
        serveur.version += 1
        serveur.appels.clear()
        source.verifierVersion()
        self.assertNotIn("ticket/1", serveur.appels)
        self.assertFalse(source.ticketParId(1).estDetaille)

    def test_relireUnDetailPlusRecentNotifie(self) -> None:
        source, serveur, espion = sourceChargee(1)
        source.lireDetail(1)
        serveur.modifier(1, titre="Changé entre deux lectures")
        source.lireDetail(1)
        self.assertEqual(espion.evenements, [("modification", 1)])
        source.lireDetail(1)  # rien de nouveau : pas de seconde notification
        self.assertEqual(len(espion.evenements), 1)

    def test_detailIncoherent(self) -> None:
        source, serveur, _ = sourceChargee(1, 2)
        reponses = {
            "résumé au lieu du détail": serveur.listerTickets()[0],
            "détail d'un autre ticket": avec(EXEMPLE_TICKET_DETAIL, id=2),
        }
        for nom, reponse in reponses.items():
            serveur.lireTicket = lambda ticketId, r=reponse: copy.deepcopy(r)  # type: ignore[method-assign]
            with self.subTest(nom), self.assertRaises(ReponseInvalide):
                source.lireDetail(1)

    def test_ticketSuiviSupprimeEntreDeuxLectures(self) -> None:
        source, serveur, _ = sourceChargee(1)
        source.lireDetail(1)
        serveur.version += 1
        serveur.pannes["ticket/1"] = RessourceIntrouvable("Le ticket 1 n'existe pas", 404)
        source.verifierVersion()  # ne lève pas : le prochain sondage verra le retrait
        self.assertFalse(source.ticketParId(1).estDetaille)


class TestEchecs(unittest.TestCase):
    def test_serveurInjoignableLaisseLaCopieIntacte(self) -> None:
        source, serveur, espion = sourceChargee(1, 2)
        version = source.version
        serveur.ajouter(3)
        serveur.pannes["tickets"] = ServeurInjoignable("http://127.0.0.1:5000", "connexion refusée")
        with self.assertRaises(ServeurInjoignable):
            source.verifierVersion()
        self.assertEqual(source.version, version)
        self.assertEqual([t.ticketID for t in source.tickets], [1, 2])
        self.assertEqual(espion.evenements, [])
        # Le serveur revient : le sondage suivant rattrape le changement.
        del serveur.pannes["tickets"]
        self.assertTrue(source.verifierVersion())
        self.assertEqual(espion.evenements, [("ajout", 3)])

    def test_reponseHorsContratLaisseLaCopieIntacte(self) -> None:
        source, serveur, espion = sourceChargee(1)
        serveur.ajouter(2, priorite="URGENTE")
        with self.assertRaises(ReponseInvalide):
            source.verifierVersion()
        serveur.listerTickets = lambda: {"tickets": []}  # type: ignore[method-assign,assignment]
        with self.assertRaises(ReponseInvalide):
            source.rafraichir()
        self.assertEqual([t.ticketID for t in source.tickets], [1])
        self.assertEqual(espion.evenements, [])

    def test_observateurEnPanneNeLaissePasLaCopieAMoitie(self) -> None:
        source, serveur, _ = sourceChargee(1)
        source.abonner(ObservateurEnPanne())
        serveur.ajouter(2)
        with self.assertRaises(RuntimeError):
            source.verifierVersion()
        self.assertIsNotNone(source.ticketParId(2))
        self.assertEqual(source.version, serveur.version)


class TestIntegrationPasserelle(unittest.TestCase):
    def test_sourceBrancheeSurClientAPI(self) -> None:
        client, transport = clientEssai(
            reponseJSON({"version": 7}),
            reponseJSON([EXEMPLE_TICKET_RESUME]),
            reponseJSON({"version": 7}),
            reponseJSON(avec(EXEMPLE_TICKET_DETAIL, id=2)),
        )
        source = SourceTickets(client)
        source.rafraichir()
        self.assertEqual(source.version, 7)
        self.assertEqual(source.tickets[0].title, "Erreur d'affichage mobile")
        self.assertFalse(source.verifierVersion())
        self.assertTrue(source.lireDetail(2).estDetaille)
        chemins = [requete.url.removeprefix("http://serveur.test") for requete in transport.requetes]
        self.assertEqual(chemins, ["/version", "/tickets", "/version", "/ticket/2"])

    def test_passerelleSansTkinter(self) -> None:
        # Critère de fin de C2 : la passerelle se charge sans Tkinter.
        code = (
            "import sys, ihm.passerelle.client_api, ihm.passerelle.objets_lecture, "
            "ihm.passerelle.source_tickets; print('tkinter' in sys.modules)"
        )
        resultat = subprocess.run(
            [sys.executable, "-c", code], cwd=RACINE, capture_output=True, text=True, check=True
        )
        self.assertEqual(resultat.stdout.strip(), "False")


if __name__ == "__main__":
    unittest.main()
