"""Tests de S2 : représentations JSON et routes de lecture, sur les données de démonstration.

Lancer depuis la racine du dépôt :  python -m unittest discover -s tests -t . -v
"""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, cast

from api import creerApplication, representations
from api.contexte import ContexteServeur
from api.erreurs import ActeurNonIdentifie
from api.identification import acteurCourant
from description.fabrique_description import FabriqueDescription
from modele.enums import Priorite
from modele.ticket import Ticket

if TYPE_CHECKING:
    from acteurs.user import User

RESSOURCES = Path(__file__).resolve().parent.parent / "ressources"

# Champs des schémas de openapi.yaml : ni plus ni moins.
CHAMPS_ACTEUR = {"id", "nom", "courriel", "role"}
CHAMPS_REFERENCE = {"id", "nom"}
CHAMPS_COMMENTAIRE = {"texte", "auteur", "date"}
CHAMPS_RESUME = {
    "id", "titre", "priorite", "statut", "createur", "assigne", "dateCreation",
    "dateMiseAJour", "dejaAssigne", "transitionsPermises", "nombreCommentaires",
}
CHAMPS_DETAIL = CHAMPS_RESUME | {"commentaires", "description"}
CHAMPS_ELEMENT = {
    "texte_saisi": {"type", "nom", "resume", "contenu"},
    "texte": {"type", "nom", "resume", "contenu"},
    "image": {"type", "nom", "resume", "url"},
    "video": {"type", "nom", "resume"},
}

# Exemple TicketDetail1 de openapi.yaml : le ticket 1 de la démonstration.
TICKET_DETAIL_1 = {
    "id": 1,
    "titre": "Bug de connexion",
    "priorite": "HAUTE",
    "statut": "TERMINE",
    "createur": {"id": 2, "nom": "Abdoul Razack"},
    "assigne": {"id": 4, "nom": "Mike Tonny"},
    "dateCreation": "2026-10-20",
    "dateMiseAJour": "2026-10-20",
    "dejaAssigne": True,
    "transitionsPermises": [],
    "nombreCommentaires": 2,
    "commentaires": [
        {
            "texte": "Le bug se reproduit sur Chrome et Firefox.",
            "auteur": {"id": 2, "nom": "Abdoul Razack"},
            "date": "2026-10-20",
        },
        {
            "texte": "Capture d'écran jointe à la description.",
            "auteur": {"id": 2, "nom": "Abdoul Razack"},
            "date": "2026-10-20",
        },
    ],
    "description": [
        {
            "type": "texte_saisi",
            "nom": "texte saisi",
            "resume": "[Texte] texte saisi (205 caractères)",
            "contenu": "Bug : impossible de se connecter à l'application.\nDepuis la dernière mise "
            "à jour, la page de connexion affiche « Identifiants invalides » même lorsque le "
            "nom d'utilisateur et le mot de passe sont corrects.",
        },
        {
            "type": "image",
            "nom": "demo_connexion.png",
            "resume": "[Image] demo_connexion.png (757 octets)",
            "url": "/ticket/1/image/demo_connexion.png",
        },
    ],
}


class TestAvecDemo(unittest.TestCase):
    """Contexte chargé sur la démonstration ; la sauvegarde va dans un dossier temporaire."""

    def setUp(self) -> None:
        self._dossier = tempfile.TemporaryDirectory()
        self.addCleanup(self._dossier.cleanup)
        self.dossier = Path(self._dossier.name)
        self.contexte = ContexteServeur(cheminSauvegarde=self.dossier / "sauvegarde.json")
        self.systeme = self.contexte.systeme

    def ticket(self, ticketId: int) -> Ticket:
        ticket = self.systeme.ticketParId(ticketId)
        assert ticket is not None
        return ticket

    def ajouterTicketQuatreTypes(self) -> Ticket:
        """Ticket avec un élément de chaque type ; la démo n'a ni fichier texte ni vidéo.

        L'image est copiée sous un nom à espace et accent, pour vérifier l'encodage de l'URL.
        """
        image = self.dossier / "capture écran.png"
        shutil.copy2(RESSOURCES / "capture_ecran.png", image)
        ticket = Ticket(self.systeme.reserverIdentifiant(), "Quatre types", Priorite.BASSE)
        createur = cast("User", self.systeme.utilisateurParId(3))
        createur.createTicket(ticket)
        for element in (
            FabriqueDescription.creerSaisie("Étapes pour reproduire."),
            FabriqueDescription.creer("texte", str(RESSOURCES / "description_bug.txt")),
            FabriqueDescription.creer("image", str(image)),
            FabriqueDescription.creer("video", str(RESSOURCES / "demo_bug.mp4")),
        ):
            element.traiter()
            ticket.ajouterElementDescription(element)
        return ticket


class TestRepresentations(TestAvecDemo):
    def test_acteur(self) -> None:
        admin = self.systeme.utilisateurParId(1)
        assert admin is not None
        self.assertEqual(
            representations.acteur(admin),
            {"id": 1, "nom": "Ambroise Fleury", "courriel": "ambroise.fleury@uqac.ca",
             "role": "Admin"},
        )

    def test_reference_acteur(self) -> None:
        self.assertIsNone(representations.referenceActeur(None))
        self.assertEqual(
            representations.referenceActeur(self.systeme.utilisateurParId(3)),
            {"id": 3, "nom": "T Julien"},
        )

    def test_ticket_detail_comme_l_exemple_du_contrat(self) -> None:
        self.assertEqual(representations.ticketDetail(self.ticket(1)), TICKET_DETAIL_1)

    def test_forme_exacte_du_resume_et_du_detail(self) -> None:
        for ticket in self.systeme.tickets:
            with self.subTest(ticket=ticket.ticketID):
                resume = representations.ticketResume(ticket)
                detail = representations.ticketDetail(ticket)
                self.assertEqual(set(resume), CHAMPS_RESUME)
                self.assertEqual(set(detail), CHAMPS_DETAIL)
                for c in detail["commentaires"]:
                    self.assertEqual(set(c), CHAMPS_COMMENTAIRE)
                    self.assertEqual(set(c["auteur"]), CHAMPS_REFERENCE)
                for e in detail["description"]:
                    self.assertEqual(set(e), CHAMPS_ELEMENT[e["type"]])

    def test_ticket_sans_assigne(self) -> None:
        resume = representations.ticketResume(self.ticket(6))
        self.assertEqual(resume["statut"], "OUVERT")
        self.assertIsNone(resume["assigne"])
        self.assertFalse(resume["dejaAssigne"])

    def test_transitions_dans_l_ordre_de_l_enum(self) -> None:
        """Exemple du contrat : un ticket ASSIGNE (le ticket 2 de la démo)."""
        self.assertEqual(
            representations.ticketResume(self.ticket(2))["transitionsPermises"],
            ["OUVERT", "ASSIGNE", "VALIDATION", "FERME"],
        )
        self.assertEqual(
            representations.ticketResume(self.ticket(6))["transitionsPermises"],
            ["ASSIGNE", "FERME"],
        )

    def test_quatre_types_d_element(self) -> None:
        ticket = self.ajouterTicketQuatreTypes()
        saisi, texte, image, video = representations.ticketDetail(ticket)["description"]
        self.assertEqual(
            saisi,
            {"type": "texte_saisi", "nom": "texte saisi",
             "resume": "[Texte] texte saisi (23 caractères)", "contenu": "Étapes pour reproduire."},
        )
        self.assertEqual(texte["type"], "texte")
        self.assertEqual(texte["nom"], "description_bug.txt")
        self.assertEqual(
            texte["contenu"], (RESSOURCES / "description_bug.txt").read_text(encoding="utf-8")
        )
        self.assertEqual(image["nom"], "capture écran.png")
        self.assertEqual(
            image["url"], f"/ticket/{ticket.ticketID}/image/capture%20%C3%A9cran.png"
        )
        self.assertEqual(set(video), CHAMPS_ELEMENT["video"])
        self.assertEqual(video["nom"], "demo_bug.mp4")

    def test_aucun_chemin_disque_expose(self) -> None:
        ticket = self.ajouterTicketQuatreTypes()
        tickets = self.systeme.tickets
        texte = repr([representations.ticketDetail(t) for t in tickets])
        # Des fragments de chemin, pas des chemins entiers : repr() double les « \ » de Windows.
        for fragment in ("donnees", "ressources", self.dossier.name):
            self.assertNotIn(fragment, texte)
        self.assertIn(ticket.ticketID, [t.ticketID for t in tickets])


class TestIdentification(TestAvecDemo):
    def setUp(self) -> None:
        super().setUp()
        self.app = creerApplication(self.contexte)

    def identifier(self, enTetes: dict[str, str]):
        with self.app.test_request_context("/tickets", headers=enTetes):
            return acteurCourant()

    def verifierRefus(self, enTetes: dict[str, str], message: str) -> None:
        with self.assertRaises(ActeurNonIdentifie) as contexte:
            self.identifier(enTetes)
        self.assertEqual(str(contexte.exception), message)

    def test_acteur_connu(self) -> None:
        self.assertIs(self.identifier({"X-Acteur-Id": "3"}), self.systeme.utilisateurParId(3))

    def test_en_tete_absent(self) -> None:
        self.verifierRefus({}, "En-tête X-Acteur-Id absent")

    def test_en_tete_non_entier(self) -> None:
        self.verifierRefus({"X-Acteur-Id": "abc"}, "En-tête X-Acteur-Id non entier : 'abc'")

    def test_acteur_inconnu(self) -> None:
        self.verifierRefus({"X-Acteur-Id": "99"}, "Acteur inconnu : 99")


class TestRoutes(TestAvecDemo):
    """Requêtes par le client de test Flask, sans réseau."""

    def setUp(self) -> None:
        super().setUp()
        self.client = creerApplication(self.contexte).test_client()

    def lire(self, chemin: str, acteurId: int | str | None = None):
        enTetes = {} if acteurId is None else {"X-Acteur-Id": str(acteurId)}
        return self.client.get(chemin, headers=enTetes)

    def verifierErreur(self, reponse, code: int, typeErreur: str) -> None:
        self.assertEqual(reponse.status_code, code, reponse.get_data(as_text=True))
        self.assertEqual(reponse.get_json()["erreur"]["type"], typeErreur)


class TestRoutesActeurs(TestRoutes):
    def test_lister_les_acteurs(self) -> None:
        reponse = self.lire("/acteurs")
        self.assertEqual(reponse.status_code, 200)
        acteurs = reponse.get_json()
        self.assertEqual([a["id"] for a in acteurs], [1, 2, 3, 4, 5])
        for a in acteurs:
            self.assertEqual(set(a), CHAMPS_ACTEUR)

    def test_filtre_par_role(self) -> None:
        self.assertEqual([a["id"] for a in self.lire("/acteurs?role=User").get_json()], [2, 3, 4, 5])
        self.assertEqual([a["id"] for a in self.lire("/acteurs?role=Admin").get_json()], [1])

    def test_role_ou_parametre_invalide(self) -> None:
        for chemin in ("/acteurs?role=Chef", "/acteurs?role=user", "/acteurs?rol=User"):
            with self.subTest(chemin=chemin):
                self.verifierErreur(self.lire(chemin), 400, "RequeteInvalide")

    def test_lire_un_acteur(self) -> None:
        reponse = self.lire("/acteur/3")
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(
            reponse.get_json(),
            {"id": 3, "nom": "T Julien", "courriel": "t.julien@uqac.ca", "role": "User"},
        )

    def test_acteur_inexistant(self) -> None:
        reponse = self.lire("/acteur/99")
        self.verifierErreur(reponse, 404, "RessourceIntrouvable")
        self.assertEqual(reponse.get_json()["erreur"]["message"], "Acteur introuvable : 99")

    def test_sans_en_tete(self) -> None:
        """Ces deux chemins sont security: [] : la connexion (F1) les lit avant tout acteur."""
        self.assertEqual(self.lire("/acteurs").status_code, 200)
        self.assertEqual(self.lire("/acteur/1", acteurId=99).status_code, 200)


class TestRoutesTickets(TestRoutes):
    CHEMINS_TICKET = ("/ticket/{}", "/ticket/{}/commentaires", "/ticket/{}/description")

    def identifiants(self, chemin: str) -> list[int]:
        reponse = self.lire(chemin, acteurId=1)
        self.assertEqual(reponse.status_code, 200, reponse.get_data(as_text=True))
        return [t["id"] for t in reponse.get_json()]

    def test_tous_les_tickets(self) -> None:
        reponse = self.lire("/tickets", acteurId=2)
        self.assertEqual(reponse.status_code, 200)
        tickets = reponse.get_json()
        self.assertEqual([t["id"] for t in tickets], [1, 2, 3, 6, 7, 8, 9, 10])
        for t in tickets:
            self.assertEqual(set(t), CHAMPS_RESUME)

    def test_liste_triee_par_identifiant(self) -> None:
        """Le dépôt garde l'ordre d'ajout ; la réponse, elle, est triée."""
        createur = cast("User", self.systeme.utilisateurParId(3))
        createur.createTicket(Ticket(5, "Ajouté en dernier", Priorite.BASSE))
        self.assertEqual(self.identifiants("/tickets"), [1, 2, 3, 5, 6, 7, 8, 9, 10])

    def test_filtres(self) -> None:
        for chaine, attendus in (
            ("statut=ASSIGNE", [2, 9, 10]),
            ("createur=2", [1, 2]),
            ("assigne=4", [1, 8]),
            ("statut=ASSIGNE&createur=2", [2]),
            ("statut=OUVERT&createur=3&assigne=2", []),
            ("createur=3&assigne=2", [9]),
            ("statut=TERMINE", [1]),
        ):
            with self.subTest(filtre=chaine):
                self.assertEqual(self.identifiants(f"/tickets?{chaine}"), attendus)

    def test_exemple_du_contrat(self) -> None:
        """Exemple de GET /tickets dans openapi.yaml (filtre statut=ASSIGNE&createur=2)."""
        (ticket,) = self.lire("/tickets?statut=ASSIGNE&createur=2", acteurId=2).get_json()
        self.assertEqual(ticket, {
            "id": 2, "titre": "Erreur d'affichage mobile", "priorite": "MOYENNE",
            "statut": "ASSIGNE", "createur": {"id": 2, "nom": "Abdoul Razack"},
            "assigne": {"id": 5, "nom": "Hein Tommy"}, "dateCreation": "2026-10-20",
            "dateMiseAJour": "2026-10-20", "dejaAssigne": True,
            "transitionsPermises": ["OUVERT", "ASSIGNE", "VALIDATION", "FERME"],
            "nombreCommentaires": 0,
        })

    def test_acteur_inconnu_dans_un_filtre(self) -> None:
        """Point fixé par le contrat : liste vide, pas une erreur. Un Admin n'a rien créé."""
        for chaine in ("createur=99", "assigne=99", "createur=1", "assigne=1"):
            with self.subTest(filtre=chaine):
                self.assertEqual(self.identifiants(f"/tickets?{chaine}"), [])

    def test_filtre_invalide(self) -> None:
        for chaine in ("statut=assigne", "statut=INCONNU", "createur=abc", "assigne=2.5",
                       "statu=FERME"):
            with self.subTest(filtre=chaine):
                self.verifierErreur(self.lire(f"/tickets?{chaine}", acteurId=1), 400,
                                    "RequeteInvalide")

    def test_lire_un_ticket(self) -> None:
        reponse = self.lire("/ticket/1", acteurId=4)
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.get_json(), TICKET_DETAIL_1)

    def test_commentaires(self) -> None:
        reponse = self.lire("/ticket/1/commentaires", acteurId=1)
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.get_json(), TICKET_DETAIL_1["commentaires"])
        self.assertEqual(self.lire("/ticket/2/commentaires", acteurId=1).get_json(), [])

    def test_description(self) -> None:
        reponse = self.lire("/ticket/1/description", acteurId=1)
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.get_json(), TICKET_DETAIL_1["description"])

    def test_description_quatre_types(self) -> None:
        ticket = self.ajouterTicketQuatreTypes()
        elements = self.lire(f"/ticket/{ticket.ticketID}/description", acteurId=3).get_json()
        self.assertEqual([e["type"] for e in elements], ["texte_saisi", "texte", "image", "video"])
        for e in elements:
            self.assertEqual(set(e), CHAMPS_ELEMENT[e["type"]])

    def test_ticket_inexistant(self) -> None:
        for modele in self.CHEMINS_TICKET:
            with self.subTest(chemin=modele):
                reponse = self.lire(modele.format(99), acteurId=1)
                self.verifierErreur(reponse, 404, "RessourceIntrouvable")
                self.assertEqual(reponse.get_json()["erreur"]["message"], "Ticket introuvable : 99")

    def test_identifiant_de_ticket_non_entier(self) -> None:
        """<int:ticketId> ne reconnaît pas le chemin : 404, comme un chemin inconnu."""
        self.verifierErreur(self.lire("/ticket/abc", acteurId=1), 404, "RessourceIntrouvable")

    def test_acteur_absent_ou_inconnu(self) -> None:
        chemins = ["/tickets", "/tickets?statut=ASSIGNE"] + [
            modele.format(1) for modele in self.CHEMINS_TICKET
        ]
        for chemin in chemins:
            for acteurId in (None, "abc", 99):
                with self.subTest(chemin=chemin, acteur=acteurId):
                    self.verifierErreur(self.lire(chemin, acteurId), 401, "ActeurNonIdentifie")

    def test_identification_avant_validation(self) -> None:
        """Étape 1 avant l'étape 2 : sans acteur, un filtre invalide donne 401, pas 400."""
        self.verifierErreur(self.lire("/tickets?statut=INCONNU"), 401, "ActeurNonIdentifie")

    def test_lecture_sans_effet(self) -> None:
        """Lire ne modifie rien : ni la version, ni la sauvegarde."""
        for chemin in ["/tickets"] + [modele.format(1) for modele in self.CHEMINS_TICKET]:
            self.lire(chemin, acteurId=1)
        self.assertEqual(self.client.get("/version").get_json(), {"version": 0})
        self.assertFalse((self.dossier / "sauvegarde.json").exists())

    def test_ecriture_non_permise(self) -> None:
        """Méthodes que le contrat n'aura jamais sur ces chemins : 405.

        PUT, parce que PATCH ne change que le statut ; POST sur les commentaires, parce
        qu'ils s'ajoutent par un brouillon. Ce test reste donc valable après S3 et S4.
        """
        enTetes = {"X-Acteur-Id": "1"}
        self.verifierErreur(self.client.put("/ticket/1", headers=enTetes), 405,
                            "MethodeNonPermise")
        self.verifierErreur(self.client.post("/ticket/1/commentaires", headers=enTetes), 405,
                            "MethodeNonPermise")


if __name__ == "__main__":
    unittest.main()
