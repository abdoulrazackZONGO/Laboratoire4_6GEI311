"""Tests de S3 : écriture des tickets (règles d'accès, PATCH, POST, DELETE).

Lancer depuis la racine du dépôt :  python -m unittest discover -s tests -t . -v
"""
from __future__ import annotations

import io
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest import mock

from api import creerApplication, representations
from api.contexte import ContexteServeur
from api.erreurs import RequeteInvalide, RessourceIntrouvable
from api.identification import Role, exigerActeurDuChemin, exigerRole, userDesigne
from modele.enums import Priorite, Statut
from modele.exceptions import AccesRefuseException
from modele.ticket import Ticket
from persistance.depot_json import DepotJSON
from sessions.rapport_execution import RapportExecution

if TYPE_CHECKING:
    from modele.systeme_tickets import SystemeTickets

RACINE = Path(__file__).resolve().parent.parent
IMAGE_SOURCE = RACINE / "ressources" / "capture_ecran.png"
ADMIN, ABDOUL, JULIEN, MIKE, HEIN = 1, 2, 3, 4, 5
# Un ticket de démonstration par statut : (ticket, assigné).
TICKET_PAR_STATUT = {
    Statut.OUVERT: (6, None),
    Statut.ASSIGNE: (2, HEIN),
    Statut.VALIDATION: (8, MIKE),
    Statut.TERMINE: (1, MIKE),
    Statut.FERME: (3, None),
}
CHAMPS_DETAIL = {
    "id", "titre", "priorite", "statut", "createur", "assigne", "dateCreation",
    "dateMiseAJour", "dejaAssigne", "transitionsPermises", "nombreCommentaires",
    "commentaires", "description",
}


class TestEcriture(unittest.TestCase):
    """Sauvegarde et images dans un dossier temporaire, requêtes par le client de test."""

    def setUp(self) -> None:
        self._dossier = tempfile.TemporaryDirectory()
        self.addCleanup(self._dossier.cleanup)
        self.dossier = Path(self._dossier.name)
        self.sauvegarde = self.dossier / "sauvegarde.json"
        self.images = self.dossier / "images"
        self.contexte = ContexteServeur(
            cheminSauvegarde=self.sauvegarde, dossierImages=self.images
        )
        self.systeme = self.contexte.systeme
        self.client = creerApplication(self.contexte).test_client()

    def ticket(self, ticketId: int) -> Ticket:
        ticket = self.systeme.ticketParId(ticketId)
        assert ticket is not None
        return ticket

    def requete(
        self, methode: str, chemin: str, acteurId: int | None, corps: dict[str, Any] | None = None
    ):
        enTetes = {} if acteurId is None else {"X-Acteur-Id": str(acteurId)}
        return self.client.open(chemin, method=methode, headers=enTetes, json=corps)

    def verifierErreur(self, reponse, code: int, typeErreur: str) -> None:
        self.assertEqual(reponse.status_code, code, reponse.get_data(as_text=True))
        self.assertEqual(reponse.get_json()["erreur"]["type"], typeErreur)

    def recharger(self) -> SystemeTickets:
        """Ce qu'un serveur relancé verrait : le système relu depuis sauvegarde.json."""
        return DepotJSON(self.sauvegarde).charger()

    def verifierRienEcrit(self, version: int) -> None:
        """Après un refus : ni sauvegarde écrite, ni version changée."""
        self.assertFalse(self.sauvegarde.exists())
        self.assertEqual(self.contexte.version, version)

    def copieImage(self, nom: str = "abc12345_capture.png") -> Path:
        """Fichier image dans le dossier de stockage temporaire."""
        self.images.mkdir(exist_ok=True)
        chemin = self.images / nom
        shutil.copy2(IMAGE_SOURCE, chemin)
        return chemin

    def ticketAvecElements(self, *elements: tuple[str, Path | str]) -> Ticket:
        """Ticket de T Julien, jamais assigné, créé par le métier avec ces éléments."""
        ticket = Ticket(self.systeme.reserverIdentifiant(), "Avec images", Priorite.BASSE)
        createur = self.systeme.utilisateurParId(JULIEN)
        session = createur.ouvrirSessionCreation(ticket)
        for typeArtefact, chemin in elements:
            session.ajouterElement(typeArtefact, str(chemin))
        rapport = session.appliquer()
        self.assertEqual(rapport.refus, [])
        return ticket


class TestReglesAcces(TestEcriture):
    def setUp(self) -> None:
        super().setUp()
        self.admin = self.systeme.utilisateurParId(ADMIN)
        self.user = self.systeme.utilisateurParId(JULIEN)

    def test_role_exige(self) -> None:
        exigerRole(self.admin, Role.Admin)
        exigerRole(self.user, Role.User)
        with self.assertRaises(AccesRefuseException):
            exigerRole(self.user, Role.Admin)
        with self.assertRaises(AccesRefuseException):
            exigerRole(self.admin, Role.User)

    def test_acteur_du_chemin(self) -> None:
        exigerActeurDuChemin(self.user, JULIEN)
        with self.assertRaises(AccesRefuseException):
            exigerActeurDuChemin(self.user, MIKE)

    def test_user_designe(self) -> None:
        self.assertIs(userDesigne(self.systeme, JULIEN), self.user)
        with self.assertRaises(RessourceIntrouvable):
            userDesigne(self.systeme, 99)
        with self.assertRaises(RequeteInvalide):
            userDesigne(self.systeme, ADMIN)


class TestRepresentationRapport(unittest.TestCase):
    def test_champs_du_contrat(self) -> None:
        rapport = RapportExecution()
        rapport.ajouterSucces("Assigner le ticket #6 à Mike Tonny")
        rapport.ajouterRefus("Assigner le ticket #3 à Mike Tonny", "Transition invalide")
        self.assertEqual(
            representations.rapport(rapport, "Lot administrateur"),
            {
                "libelle": "Lot administrateur",
                "succes": ["Assigner le ticket #6 à Mike Tonny"],
                "refus": [
                    {
                        "operation": "Assigner le ticket #3 à Mike Tonny",
                        "motif": "Transition invalide",
                    }
                ],
                "nombreSucces": 1,
                "nombreRefus": 1,
                "ticketId": None,
            },
        )
        self.assertEqual(representations.rapport(rapport, "x", 11)["ticketId"], 11)


class TestChangerStatut(TestEcriture):
    def changer(self, ticketId: int, acteurId: int | None, **corps: Any):
        return self.requete("PATCH", f"/ticket/{ticketId}", acteurId, corps)

    def test_chaque_statut_contre_la_machine_a_etats(self) -> None:
        """5 états x 5 statuts demandés : 200 si l'état le permet, 409 sinon."""
        for source, (ticketId, assigneId) in TICKET_PAR_STATUT.items():
            for cible in Statut:
                if cible is Statut.VALIDATION and assigneId is None:
                    continue  # Sans assigné, c'est 403 : voir le test suivant.
                with self.subTest(source=source.name, cible=cible.name):
                    self.setUp()
                    ticket = self.ticket(ticketId)
                    self.assertIs(ticket.status, source)
                    permis = cible in ticket.transitionsPermises
                    version = self.contexte.version
                    corps = {"statut": cible.name}
                    if cible is Statut.ASSIGNE:
                        corps["assigneId"] = JULIEN
                    acteur = assigneId if cible is Statut.VALIDATION else ADMIN
                    reponse = self.requete("PATCH", f"/ticket/{ticketId}", acteur, corps)
                    if permis:
                        self.assertEqual(reponse.status_code, 200, reponse.get_data(as_text=True))
                        self.assertEqual(reponse.get_json()["statut"], cible.name)
                        self.assertIs(ticket.status, cible)
                        self.assertGreater(self.contexte.version, version)
                        self.assertIs(self.recharger().ticketParId(ticketId).status, cible)
                    else:
                        self.verifierErreur(reponse, 409, "TransitionInvalideException")
                        self.assertEqual(
                            reponse.get_json()["erreur"]["message"],
                            "Transition invalide : impossible de passer de l'état "
                            f"{source.name} au statut {cible.name}",
                        )
                        self.assertIs(ticket.status, source)
                        self.verifierRienEcrit(version)

    def test_huit_transitions_permises(self) -> None:
        """Garde-fou du test précédent : il couvre bien ces transitions, écrites à la main."""
        permises = {
            source: self.ticket(ticketId).transitionsPermises
            for source, (ticketId, _) in TICKET_PAR_STATUT.items()
        }
        self.assertEqual(
            permises,
            {
                Statut.OUVERT: {Statut.ASSIGNE, Statut.FERME},
                Statut.ASSIGNE: {Statut.ASSIGNE, Statut.OUVERT, Statut.VALIDATION, Statut.FERME},
                Statut.VALIDATION: {Statut.ASSIGNE, Statut.TERMINE},
                Statut.TERMINE: set(),
                Statut.FERME: set(),
            },
        )

    def test_validation_sans_assigne_donne_403(self) -> None:
        """soumettreValidation() vérifie l'assigné avant l'état : 403 et non 409."""
        for ticketId in (6, 3):
            with self.subTest(ticket=ticketId):
                version = self.contexte.version
                reponse = self.changer(ticketId, JULIEN, statut="VALIDATION")
                self.verifierErreur(reponse, 403, "AccesRefuseException")
                self.verifierRienEcrit(version)

    def test_assigner(self) -> None:
        reponse = self.changer(6, ADMIN, statut="ASSIGNE", assigneId=JULIEN)
        self.assertEqual(reponse.status_code, 200)
        ticket = reponse.get_json()
        self.assertEqual(set(ticket), CHAMPS_DETAIL)
        self.assertEqual(ticket["statut"], "ASSIGNE")
        self.assertEqual(ticket["assigne"], {"id": JULIEN, "nom": "T Julien"})
        self.assertTrue(ticket["dejaAssigne"])
        self.assertEqual(
            ticket["transitionsPermises"], ["OUVERT", "ASSIGNE", "VALIDATION", "FERME"]
        )

    def test_reassigner_et_rejeter_une_validation(self) -> None:
        for ticketId, ancien in ((2, HEIN), (8, MIKE)):
            with self.subTest(ticket=ticketId):
                self.assertEqual(self.ticket(ticketId).assignedUser.id, ancien)
                reponse = self.changer(ticketId, ADMIN, statut="ASSIGNE", assigneId=JULIEN)
                self.assertEqual(reponse.status_code, 200)
                self.assertEqual(reponse.get_json()["statut"], "ASSIGNE")
                self.assertEqual(reponse.get_json()["assigne"]["id"], JULIEN)

    def test_desassigner_garde_l_historique(self) -> None:
        ticket = self.changer(2, ADMIN, statut="OUVERT").get_json()
        self.assertEqual(ticket["statut"], "OUVERT")
        self.assertIsNone(ticket["assigne"])
        self.assertTrue(ticket["dejaAssigne"])

    def test_fermer_garde_l_assigne(self) -> None:
        ticket = self.changer(2, ADMIN, statut="FERME").get_json()
        self.assertEqual(ticket["statut"], "FERME")
        self.assertEqual(ticket["assigne"]["id"], HEIN)
        self.assertEqual(ticket["transitionsPermises"], [])

    def test_soumettre_puis_valider(self) -> None:
        self.assertEqual(self.changer(2, HEIN, statut="VALIDATION").status_code, 200)
        self.assertEqual(self.changer(2, ADMIN, statut="TERMINE").get_json()["statut"], "TERMINE")

    def test_user_qui_tente_une_action_d_admin(self) -> None:
        version = self.contexte.version
        for statut, ticketId, corps in (
            ("ASSIGNE", 6, {"assigneId": JULIEN}),
            ("OUVERT", 2, {}),
            ("TERMINE", 8, {}),
            ("FERME", 6, {}),
        ):
            with self.subTest(statut=statut):
                # Même l'assigné du ticket n'a pas ce droit.
                acteur = HEIN if ticketId == 2 else JULIEN
                reponse = self.changer(ticketId, acteur, statut=statut, **corps)
                self.verifierErreur(reponse, 403, "AccesRefuseException")
        self.verifierRienEcrit(version)

    def test_admin_qui_soumet_a_validation(self) -> None:
        reponse = self.changer(2, ADMIN, statut="VALIDATION")
        self.verifierErreur(reponse, 403, "AccesRefuseException")

    def test_user_qui_n_est_pas_l_assigne(self) -> None:
        reponse = self.changer(2, JULIEN, statut="VALIDATION")
        self.verifierErreur(reponse, 403, "AccesRefuseException")
        self.assertEqual(
            reponse.get_json()["erreur"]["message"], "T Julien n'est pas l'assigné du ticket 2"
        )
        self.assertIs(self.ticket(2).status, Statut.ASSIGNE)

    def test_format_du_corps(self) -> None:
        for corps in (
            {},
            {"statut": "INCONNU"},
            {"statut": "ferme"},
            {"statut": 3},
            {"statut": "FERME", "statu": "x"},
            {"statut": "ASSIGNE"},
            {"statut": "ASSIGNE", "assigneId": "3"},
            {"statut": "ASSIGNE", "assigneId": None},
            {"statut": "FERME", "assigneId": JULIEN},
            {"statut": "OUVERT", "assigneId": JULIEN},
        ):
            with self.subTest(corps=corps):
                reponse = self.requete("PATCH", "/ticket/6", ADMIN, corps)
                self.verifierErreur(reponse, 400, "RequeteInvalide")
        self.assertFalse(self.sauvegarde.exists())

    def test_corps_absent_ou_illisible(self) -> None:
        enTetes = {"X-Acteur-Id": str(ADMIN)}
        for donnees in (b"", b"{ pas du JSON", b"[1]"):
            with self.subTest(donnees=donnees):
                reponse = self.client.patch("/ticket/6", headers=enTetes, data=donnees)
                self.verifierErreur(reponse, 400, "RequeteInvalide")

    def test_ressources_introuvables(self) -> None:
        reponse = self.changer(999, ADMIN, statut="FERME")
        self.verifierErreur(reponse, 404, "RessourceIntrouvable")
        self.assertEqual(reponse.get_json()["erreur"]["message"], "Ticket introuvable : 999")
        reponse = self.changer(6, ADMIN, statut="ASSIGNE", assigneId=99)
        self.verifierErreur(reponse, 404, "RessourceIntrouvable")
        self.assertEqual(reponse.get_json()["erreur"]["message"], "Acteur introuvable : 99")
        self.assertIs(self.ticket(6).status, Statut.OUVERT)

    def test_assigne_qui_n_est_pas_un_user(self) -> None:
        reponse = self.changer(6, ADMIN, statut="ASSIGNE", assigneId=ADMIN)
        self.verifierErreur(reponse, 400, "RequeteInvalide")
        self.assertIs(self.ticket(6).status, Statut.OUVERT)

    def test_acteur_non_identifie(self) -> None:
        for acteur in (None, 99):
            with self.subTest(acteur=acteur):
                reponse = self.changer(6, acteur, statut="FERME")
                self.verifierErreur(reponse, 401, "ActeurNonIdentifie")

    def test_ordre_des_controles(self) -> None:
        """401, puis 400, puis 403 (rôle), puis 404, puis le métier."""
        corpsInvalide = {"statut": "INCONNU"}
        self.verifierErreur(
            self.requete("PATCH", "/ticket/999", None, corpsInvalide), 401, "ActeurNonIdentifie"
        )
        self.verifierErreur(
            self.requete("PATCH", "/ticket/999", JULIEN, corpsInvalide), 400, "RequeteInvalide"
        )
        self.verifierErreur(self.changer(999, JULIEN, statut="FERME"), 403, "AccesRefuseException")
        self.verifierErreur(self.changer(999, ADMIN, statut="FERME"), 404, "RessourceIntrouvable")
        self.verifierErreur(
            self.changer(1, ADMIN, statut="FERME"), 409, "TransitionInvalideException"
        )

    def test_modifications_successives_toutes_sauvegardees(self) -> None:
        self.changer(6, ADMIN, statut="ASSIGNE", assigneId=JULIEN)
        self.changer(6, JULIEN, statut="VALIDATION")
        ticket = self.recharger().ticketParId(6)
        self.assertIs(ticket.status, Statut.VALIDATION)
        self.assertEqual(ticket.assignedUser.id, JULIEN)
        self.assertTrue(ticket.aDejaEteAssigne)
        self.assertEqual(self.requete("GET", "/ticket/6", ADMIN).get_json()["statut"], "VALIDATION")


class TestCreerTicket(TestEcriture):
    CORPS = {"titre": "Paiement refusé", "priorite": "HAUTE", "texte": "La carte est refusée."}

    def creer(self, acteurId: int | None = JULIEN, **modifications: Any):
        return self.requete("POST", "/tickets", acteurId, {**self.CORPS, **modifications})

    def test_creation(self) -> None:
        version = self.contexte.version
        reponse = self.creer()
        self.assertEqual(reponse.status_code, 201, reponse.get_data(as_text=True))
        self.assertEqual(reponse.headers["Location"], "/ticket/11")
        resultat = reponse.get_json()
        self.assertEqual(set(resultat), {"ticket", "rapport"})
        ticket = resultat["ticket"]
        self.assertEqual(set(ticket), CHAMPS_DETAIL)
        self.assertEqual(ticket["id"], 11)
        self.assertEqual(ticket["titre"], "Paiement refusé")
        self.assertEqual(ticket["priorite"], "HAUTE")
        self.assertEqual(ticket["statut"], "OUVERT")
        self.assertEqual(ticket["createur"], {"id": JULIEN, "nom": "T Julien"})
        self.assertIsNone(ticket["assigne"])
        self.assertFalse(ticket["dejaAssigne"])
        self.assertEqual([e["type"] for e in ticket["description"]], ["texte_saisi"])
        self.assertEqual(ticket["description"][0]["contenu"], "La carte est refusée.")
        self.assertGreater(self.contexte.version, version)

    def test_rapport(self) -> None:
        rapport = self.creer().get_json()["rapport"]
        self.assertEqual(rapport["libelle"], "Session de création")
        self.assertEqual(rapport["ticketId"], 11)
        self.assertEqual(rapport["nombreSucces"], 1)
        self.assertEqual(rapport["refus"], [])
        self.assertIn("#11", rapport["succes"][0])

    def test_lecture_et_sauvegarde(self) -> None:
        self.creer()
        lu = self.requete("GET", "/ticket/11", ADMIN).get_json()
        self.assertEqual(lu["titre"], "Paiement refusé")
        ticket = self.recharger().ticketParId(11)
        self.assertEqual(ticket.title, "Paiement refusé")
        self.assertEqual(ticket.creator.id, JULIEN)
        self.assertEqual(ticket.description.nombreElements, 1)

    def test_espaces_de_bord_retires_comme_dans_la_gui(self) -> None:
        ticket = self.creer(titre="  Bug  ", texte="\n Texte \n").get_json()["ticket"]
        self.assertEqual(ticket["titre"], "Bug")
        self.assertEqual(ticket["description"][0]["contenu"], "Texte")

    def test_identifiants_distincts(self) -> None:
        identifiants = [self.creer().get_json()["ticket"]["id"] for _ in range(3)]
        self.assertEqual(identifiants, [11, 12, 13])

    def test_titre_non_encodable_ne_bloque_pas_le_serveur(self) -> None:
        """Ce ticket en mémoire ferait échouer toutes les sauvegardes et lectures suivantes."""
        version = self.contexte.version
        reponse = self.client.post(
            "/tickets",
            headers={"X-Acteur-Id": str(JULIEN)},
            data=rb'{"titre": "\ud800", "priorite": "BASSE", "texte": "x"}',
        )
        self.verifierErreur(reponse, 400, "RequeteInvalide")
        self.assertIsNone(self.systeme.ticketParId(11))
        self.verifierRienEcrit(version)
        self.assertEqual(self.requete("GET", "/tickets", ADMIN).status_code, 200)
        reponse = self.requete("PATCH", "/ticket/7", ADMIN, {"statut": "FERME"})
        self.assertEqual(reponse.status_code, 200)

    def test_nom_de_champ_non_encodable(self) -> None:
        """Le message d'erreur citerait ce nom : la réponse elle-même ne pourrait pas partir."""
        reponse = self.client.patch(
            "/ticket/6",
            headers={"X-Acteur-Id": str(ADMIN)},
            data=rb'{"statut": "FERME", "\ud800": 1}',
        )
        self.verifierErreur(reponse, 400, "RequeteInvalide")
        self.assertIn("caractère Unicode invalide", reponse.get_json()["erreur"]["message"])

    def test_emoji_dans_le_titre_sauvegarde(self) -> None:
        reponse = self.client.post(
            "/tickets",
            headers={"X-Acteur-Id": str(JULIEN)},
            json={"titre": "Bug 😀", "priorite": "BASSE", "texte": "x"},
        )
        self.assertEqual(reponse.status_code, 201, reponse.get_data(as_text=True))
        self.assertEqual(reponse.get_json()["ticket"]["titre"], "Bug 😀")
        self.assertEqual(self.recharger().ticketParId(11).title, "Bug 😀")

    def test_admin_refuse(self) -> None:
        version = self.contexte.version
        self.verifierErreur(self.creer(ADMIN), 403, "AccesRefuseException")
        self.verifierRienEcrit(version)

    def test_format_du_corps(self) -> None:
        for corps in (
            {},
            {"titre": "x", "priorite": "HAUTE"},
            {"titre": "x", "texte": "y"},
            {"priorite": "HAUTE", "texte": "y"},
            {**self.CORPS, "statut": "OUVERT"},
            {**self.CORPS, "titre": "   "},
            {**self.CORPS, "titre": 5},
            {**self.CORPS, "texte": ""},
            {**self.CORPS, "priorite": "haute"},
            {**self.CORPS, "priorite": "URGENTE"},
        ):
            with self.subTest(corps=corps):
                version = self.contexte.version
                reponse = self.requete("POST", "/tickets", JULIEN, corps)
                self.verifierErreur(reponse, 400, "RequeteInvalide")
                self.verifierRienEcrit(version)
        # Aucun identifiant n'a été consommé par ces refus.
        self.assertEqual(self.creer().get_json()["ticket"]["id"], 11)

    def test_acteur_non_identifie(self) -> None:
        for acteur in (None, 99):
            with self.subTest(acteur=acteur):
                self.verifierErreur(self.creer(acteur), 401, "ActeurNonIdentifie")

    def test_ordre_des_controles(self) -> None:
        """401, puis 403 (rôle), puis 400."""
        self.verifierErreur(self.requete("POST", "/tickets", None, {}), 401, "ActeurNonIdentifie")
        self.verifierErreur(
            self.requete("POST", "/tickets", ADMIN, {}), 403, "AccesRefuseException"
        )
        self.verifierErreur(self.requete("POST", "/tickets", JULIEN, {}), 400, "RequeteInvalide")


class TestSupprimerTicket(TestEcriture):
    def supprimer(self, ticketId: int, acteurId: int | None = JULIEN):
        return self.requete("DELETE", f"/ticket/{ticketId}", acteurId)

    def test_suppression(self) -> None:
        version = self.contexte.version
        reponse = self.supprimer(6)
        self.assertEqual(reponse.status_code, 204)
        self.assertEqual(reponse.get_data(), b"")
        self.assertGreater(self.contexte.version, version)
        self.verifierErreur(self.requete("GET", "/ticket/6", ADMIN), 404, "RessourceIntrouvable")
        self.assertIsNone(self.recharger().ticketParId(6))

    def test_identifiant_jamais_repris(self) -> None:
        corps = {"titre": "T", "priorite": "BASSE", "texte": "x"}
        premier = self.requete("POST", "/tickets", JULIEN, corps).get_json()["ticket"]["id"]
        self.assertEqual(self.supprimer(premier).status_code, 204)
        second = self.requete("POST", "/tickets", JULIEN, corps).get_json()["ticket"]["id"]
        self.assertEqual(second, premier + 1)

    def test_ticket_deja_assigne(self) -> None:
        """Le ticket 2 est assigné ; le 6, une fois désassigné, garde son historique."""
        version = self.contexte.version
        self.verifierErreur(self.supprimer(2, ABDOUL), 409, "SuppressionInterditeException")
        self.verifierRienEcrit(version)
        self.requete("PATCH", "/ticket/6", ADMIN, {"statut": "ASSIGNE", "assigneId": MIKE})
        self.requete("PATCH", "/ticket/6", ADMIN, {"statut": "OUVERT"})
        self.verifierErreur(self.supprimer(6), 409, "SuppressionInterditeException")
        self.assertIsNotNone(self.systeme.ticketParId(6))

    def test_pas_le_createur(self) -> None:
        version = self.contexte.version
        self.verifierErreur(self.supprimer(6, ABDOUL), 403, "AccesRefuseException")
        self.assertIsNotNone(self.systeme.ticketParId(6))
        self.verifierRienEcrit(version)

    def test_admin_refuse(self) -> None:
        self.verifierErreur(self.supprimer(6, ADMIN), 403, "AccesRefuseException")
        self.assertIsNotNone(self.systeme.ticketParId(6))

    def test_acteur_ou_ticket_inconnu(self) -> None:
        self.verifierErreur(self.supprimer(6, None), 401, "ActeurNonIdentifie")
        self.verifierErreur(self.supprimer(6, 99), 401, "ActeurNonIdentifie")
        self.verifierErreur(self.supprimer(999), 404, "RessourceIntrouvable")

    def test_ordre_des_controles(self) -> None:
        """401, puis 403 (rôle), puis 404, puis le métier."""
        self.verifierErreur(self.supprimer(999, None), 401, "ActeurNonIdentifie")
        self.verifierErreur(self.supprimer(999, ADMIN), 403, "AccesRefuseException")
        self.verifierErreur(self.supprimer(999, JULIEN), 404, "RessourceIntrouvable")
        self.verifierErreur(self.supprimer(2, JULIEN), 403, "AccesRefuseException")

    # ------------------------------------------------------------------ images

    def test_copies_supprimees(self) -> None:
        premiere, seconde = self.copieImage("a_1.png"), self.copieImage("b_2.png")
        temoin = self.copieImage("c_temoin.png")
        ticket = self.ticketAvecElements(("image", premiere), ("image", seconde))
        self.assertEqual(self.supprimer(ticket.ticketID).status_code, 204)
        self.assertFalse(premiere.exists())
        self.assertFalse(seconde.exists())
        self.assertTrue(temoin.exists())

    def test_meme_image_deux_fois_dans_le_ticket(self) -> None:
        image = self.copieImage()
        ticket = self.ticketAvecElements(("image", image), ("image", image))
        self.assertEqual(self.supprimer(ticket.ticketID).status_code, 204)
        self.assertFalse(image.exists())

    def test_refus_ne_touche_pas_aux_images(self) -> None:
        image = self.copieImage()
        ticket = self.ticketAvecElements(("image", image))
        self.verifierErreur(self.supprimer(ticket.ticketID, ABDOUL), 403, "AccesRefuseException")
        self.assertTrue(image.exists())

    def test_image_de_demonstration_gardee(self) -> None:
        image = self.copieImage("demo_connexion.png")
        ticket = self.ticketAvecElements(("image", image))
        self.assertEqual(self.supprimer(ticket.ticketID).status_code, 204)
        self.assertTrue(image.exists())

    def test_copie_dont_le_nom_contient_demo_supprimee(self) -> None:
        """Une copie envoyée s'appelle <aléa>_demo_x.png : elle n'est pas versionnée."""
        image = self.copieImage("abc12345_demo_x.png")
        ticket = self.ticketAvecElements(("image", image))
        self.assertEqual(self.supprimer(ticket.ticketID).status_code, 204)
        self.assertFalse(image.exists())

    def test_vraies_images_de_demonstration_intactes(self) -> None:
        """Même citée par un ticket supprimable, une image du dépôt Git reste en place."""
        image = RACINE / "donnees" / "images" / "demo_connexion.png"
        ticket = self.ticketAvecElements(("image", image))
        self.assertEqual(self.supprimer(ticket.ticketID).status_code, 204)
        self.assertTrue(image.exists())

    def test_image_citee_par_un_autre_ticket_gardee(self) -> None:
        image = self.copieImage()
        premier = self.ticketAvecElements(("image", image))
        second = self.ticketAvecElements(("image", image))
        self.assertEqual(self.supprimer(premier.ticketID).status_code, 204)
        self.assertTrue(image.exists())
        # Le second ticket la lit encore, et il reste rechargeable depuis la sauvegarde.
        relu = self.recharger().ticketParId(second.ticketID)
        self.assertEqual(relu.description.nombreElements, 1)
        self.assertEqual(self.supprimer(second.ticketID).status_code, 204)
        self.assertFalse(image.exists())

    def test_seules_les_images_sont_supprimees(self) -> None:
        """Texte et vidéo ne sont jamais copiés : leur fichier appartient à l'utilisateur."""
        self.images.mkdir(exist_ok=True)
        texte = self.images / "notes.txt"
        texte.write_text("Notes", encoding="utf-8")
        ticket = self.ticketAvecElements(("texte", texte))
        self.assertEqual(self.supprimer(ticket.ticketID).status_code, 204)
        self.assertTrue(texte.exists())

    def test_fichier_qui_resiste(self) -> None:
        """Le ticket est déjà supprimé : 204, et le problème est signalé dans la console."""
        ticket = self.ticketAvecElements(("image", self.copieImage()))
        console = io.StringIO()
        with (
            mock.patch.object(
                self.contexte.stockage, "supprimer", side_effect=PermissionError("tenu")
            ),
            redirect_stderr(console),
        ):
            reponse = self.supprimer(ticket.ticketID)
        self.assertEqual(reponse.status_code, 204)
        self.assertIn(f"Image du ticket {ticket.ticketID} non supprimée", console.getvalue())

    def test_sauvegarde_qui_echoue_garde_l_image(self) -> None:
        """Le fichier JSON cite encore le ticket : son image doit rester."""
        image = self.copieImage()
        ticket = self.ticketAvecElements(("image", image))
        with (
            mock.patch.object(self.contexte, "sauvegarder", side_effect=OSError("disque plein")),
            redirect_stderr(io.StringIO()),
        ):
            reponse = self.supprimer(ticket.ticketID)
        self.verifierErreur(reponse, 500, "ErreurInterne")
        self.assertTrue(image.exists())


class TestLireImage(TestEcriture):
    def lire(self, chemin: str):
        """Sans en-tête X-Acteur-Id : une balise <img> n'en envoie pas."""
        return self.client.get(chemin)

    def urlImage(self, ticketId: int) -> str:
        """L'URL que donne la description, seule chose qu'un client connaît."""
        ticket = self.requete("GET", f"/ticket/{ticketId}", ADMIN).get_json()
        return next(e["url"] for e in ticket["description"] if e["type"] == "image")

    def verifierIntrouvable(self, chemin: str) -> None:
        self.verifierErreur(self.lire(chemin), 404, "RessourceIntrouvable")

    def test_image_de_demonstration(self) -> None:
        reponse = self.lire(self.urlImage(1))
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.mimetype, "image/png")
        self.assertEqual(reponse.headers["X-Content-Type-Options"], "nosniff")
        attendu = (RACINE / "donnees" / "images" / "demo_connexion.png").read_bytes()
        self.assertEqual(reponse.get_data(), attendu)

    def test_sans_acteur_mais_avec_un_en_tete_aussi(self) -> None:
        url = self.urlImage(1)
        self.assertEqual(self.lire(url).status_code, 200)
        self.assertEqual(self.requete("GET", url, ABDOUL).status_code, 200)

    def test_type_mime_selon_l_extension(self) -> None:
        for nom, attendu in (
            ("abc_a.png", "image/png"),
            ("abc_b.PNG", "image/png"),
            ("abc_c.gif", "image/gif"),
            ("abc_d.GIF", "image/gif"),
        ):
            with self.subTest(nom=nom):
                ticket = self.ticketAvecElements(("image", self.copieImage(nom)))
                reponse = self.lire(f"/ticket/{ticket.ticketID}/image/{nom}")
                self.assertEqual(reponse.status_code, 200)
                self.assertEqual(reponse.mimetype, attendu)

    def test_nom_a_echapper_dans_l_url(self) -> None:
        """L'URL de la description reste valable avec accents, espaces, # et %."""
        for nom in ("abc_capture écran.png", "abc_n°1 #2 100%.png"):
            with self.subTest(nom=nom):
                image = self.copieImage(nom)
                ticket = self.ticketAvecElements(("image", image))
                reponse = self.lire(self.urlImage(ticket.ticketID))
                self.assertEqual(reponse.status_code, 200)
                self.assertEqual(reponse.get_data(), image.read_bytes())

    def test_nom_inconnu(self) -> None:
        self.verifierIntrouvable("/ticket/1/image/inconnu.png")
        self.verifierIntrouvable("/ticket/1/image/demo_connexion.PNG")
        self.verifierIntrouvable("/ticket/1/image/%ED%A0%80.png")
        reponse = self.lire("/ticket/1/image/inconnu.png")
        self.assertEqual(reponse.get_json()["erreur"]["message"], "Image introuvable : inconnu.png")

    def test_image_d_un_autre_ticket(self) -> None:
        self.assertEqual(self.lire("/ticket/1/image/demo_connexion.png").status_code, 200)
        self.verifierIntrouvable("/ticket/2/image/demo_connexion.png")

    def test_ticket_inconnu(self) -> None:
        self.verifierIntrouvable("/ticket/999/image/demo_connexion.png")

    def test_aucun_fichier_hors_de_la_description(self) -> None:
        """Ni remontée de dossier, ni autre fichier du serveur, écrits de toutes les façons."""
        for nom in (
            "../sauvegarde.json",
            "../../donnees/demo.json",
            "..%2F..%2Fdonnees%2Fdemo.json",
            "%2E%2E%2F%2E%2E%2Fserveur.py",
            "..\\..\\serveur.py",
            "..%5C..%5Cserveur.py",
            "demo.json",
            "serveur.py",
            "%2Fetc%2Fpasswd",
            "C:%5CWindows%5Cwin.ini",
        ):
            with self.subTest(nom=nom):
                reponse = self.lire(f"/ticket/1/image/{nom}")
                self.assertEqual(reponse.status_code, 404, reponse.get_data(as_text=True)[:200])
                self.assertEqual(reponse.mimetype, "application/json")

    def test_seules_les_images_sont_servies(self) -> None:
        """Un texte de la description a un chemin, mais pas d'URL : il n'est pas servi ici."""
        self.images.mkdir(exist_ok=True)
        texte = self.images / "notes.txt"
        texte.write_text("Notes", encoding="utf-8")
        video = RACINE / "ressources" / "demo_bug.mp4"
        ticket = self.ticketAvecElements(("texte", texte), ("video", video))
        self.verifierIntrouvable(f"/ticket/{ticket.ticketID}/image/notes.txt")
        self.verifierIntrouvable(f"/ticket/{ticket.ticketID}/image/demo_bug.mp4")

    def test_ticket_supprime(self) -> None:
        image = self.copieImage()
        ticket = self.ticketAvecElements(("image", image))
        chemin = f"/ticket/{ticket.ticketID}/image/{image.name}"
        self.assertEqual(self.lire(chemin).status_code, 200)
        suppression = self.requete("DELETE", f"/ticket/{ticket.ticketID}", JULIEN)
        self.assertEqual(suppression.status_code, 204)
        self.verifierIntrouvable(chemin)

    def test_fichier_disparu_du_disque(self) -> None:
        image = self.copieImage()
        ticket = self.ticketAvecElements(("image", image))
        image.unlink()
        self.verifierIntrouvable(f"/ticket/{ticket.ticketID}/image/{image.name}")

    def test_fichier_supprimable_apres_lecture(self) -> None:
        """La réponse ne garde pas le fichier ouvert : Windows refuserait sa suppression."""
        image = self.copieImage()
        ticket = self.ticketAvecElements(("image", image))
        reponse = self.lire(f"/ticket/{ticket.ticketID}/image/{image.name}")
        self.assertEqual(reponse.status_code, 200)
        image.unlink()
        self.assertEqual(reponse.get_data(), IMAGE_SOURCE.read_bytes())

    def test_lecture_sans_effet(self) -> None:
        version = self.contexte.version
        self.lire(self.urlImage(1))
        self.verifierRienEcrit(version)

    def test_methode_absente(self) -> None:
        reponse = self.requete("POST", "/ticket/1/image/demo_connexion.png", ADMIN)
        self.verifierErreur(reponse, 405, "MethodeNonPermise")


if __name__ == "__main__":
    unittest.main()
