"""Tests de S1 : démarrage du serveur (contexte, fabrique de l'application, erreurs, /version).

Lancer depuis la racine du dépôt :  python -m unittest discover -s tests -t . -v
"""
from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from flask import request

from acteurs.user import User
from api import creerApplication
from api.contexte import (
    ATTENTES_SAUVEGARDE,
    CHEMIN_DEMO,
    CHEMIN_SAUVEGARDE,
    ContexteServeur,
    contexteCourant,
)
from api.erreurs import (
    MESSAGE_ERREUR_INTERNE,
    ActeurNonIdentifie,
    RequeteInvalide,
    RessourceIntrouvable,
)
from modele.enums import Priorite, Statut
from modele.exceptions import (
    AccesRefuseException,
    ArtefactInvalideException,
    SessionIndisponibleException,
    SuppressionInterditeException,
    TransitionInvalideException,
)
from modele.systeme_tickets import SystemeTickets
from modele.ticket import Ticket
from persistance.depot_json import DepotJSON


class TestAvecDossierTemporaire(unittest.TestCase):
    """Chaque test sauvegarde dans un dossier temporaire, jamais dans donnees/sauvegarde.json."""

    def setUp(self) -> None:
        self._dossier = tempfile.TemporaryDirectory()
        self.addCleanup(self._dossier.cleanup)
        self.cheminSauvegarde = Path(self._dossier.name) / "sauvegarde.json"

    def nouveauContexte(self) -> ContexteServeur:
        return ContexteServeur(cheminSauvegarde=self.cheminSauvegarde)


class TestChargementContexte(TestAvecDossierTemporaire):
    def test_sans_sauvegarde_charge_la_demo(self) -> None:
        demo = DepotJSON(CHEMIN_DEMO).charger()
        console = io.StringIO()
        with redirect_stderr(console):
            contexte = self.nouveauContexte()
        self.assertEqual(contexte.sourceChargee, Path(CHEMIN_DEMO))
        self.assertEqual(len(contexte.systeme.utilisateurs), len(demo.utilisateurs))
        self.assertEqual(
            [t.ticketID for t in contexte.systeme.tickets], [t.ticketID for t in demo.tickets]
        )
        self.assertEqual(contexte.version, 0)
        self.assertEqual(console.getvalue(), "")

    def test_sauvegarde_valide_chargee_en_priorite(self) -> None:
        systeme = SystemeTickets()
        createur = User(7, "Seul", "seul@uqac.ca", systeme)
        systeme.inscrireUtilisateur(createur)
        createur.createTicket(Ticket(42, "Unique", Priorite.BASSE))
        DepotJSON(self.cheminSauvegarde).sauvegarder(systeme)
        contexte = self.nouveauContexte()
        self.assertEqual(contexte.sourceChargee, self.cheminSauvegarde)
        self.assertEqual([t.ticketID for t in contexte.systeme.tickets], [42])

    def test_sauvegarde_illisible_retombe_sur_la_demo(self) -> None:
        self.cheminSauvegarde.write_text("{ pas du JSON", encoding="utf-8")
        console = io.StringIO()
        with redirect_stderr(console):
            contexte = self.nouveauContexte()
        self.assertEqual(contexte.sourceChargee, Path(CHEMIN_DEMO))
        self.assertIn("illisible", console.getvalue())
        self.assertIn("démonstration", console.getvalue())


class TestVersionEtSauvegarde(TestAvecDossierTemporaire):
    def setUp(self) -> None:
        super().setUp()
        self.contexte = self.nouveauContexte()
        createur = self.contexte.systeme.utilisateurParId(2)
        assert createur is not None and createur.role == "User"
        self.createur: User = createur  # type: ignore[assignment]

    def test_sauvegarde_reessaie_si_le_fichier_est_tenu(self) -> None:
        """Un autre processus de Windows peut tenir le fichier un court instant."""
        with (
            mock.patch("api.contexte.time.sleep") as attente,
            mock.patch.object(
                self.contexte.depot,
                "sauvegarder",
                side_effect=[PermissionError(), PermissionError(), None],
            ) as sauvegarde,
        ):
            self.contexte.sauvegarder()
        self.assertEqual(sauvegarde.call_count, 3)
        self.assertEqual(attente.call_count, 2)

    def test_sauvegarde_abandonne_apres_le_dernier_essai(self) -> None:
        with (
            mock.patch("api.contexte.time.sleep"),
            mock.patch.object(
                self.contexte.depot, "sauvegarder", side_effect=PermissionError()
            ) as sauvegarde,
        ):
            with self.assertRaises(PermissionError):
                self.contexte.sauvegarder()
        self.assertEqual(sauvegarde.call_count, len(ATTENTES_SAUVEGARDE) + 1)

    def test_version_suit_ajout_modification_retrait(self) -> None:
        ticket = Ticket(1000, "Nouveau", Priorite.BASSE)
        versions = [self.contexte.version]
        self.createur.createTicket(ticket)
        versions.append(self.contexte.version)
        ticket.addComment("Un commentaire", self.createur)
        versions.append(self.contexte.version)
        self.createur.supprimerTicket(ticket)
        versions.append(self.contexte.version)
        self.assertEqual(versions[0], 0)
        for avant, apres in zip(versions, versions[1:]):
            self.assertGreater(apres, avant)

    def test_sauvegarder_au_chemin_choisi(self) -> None:
        reelle = Path(CHEMIN_SAUVEGARDE)
        etatAvant = reelle.stat().st_mtime_ns if reelle.exists() else None
        self.createur.createTicket(Ticket(1000, "Sauvegardé", Priorite.HAUTE))
        version = self.contexte.version
        self.contexte.sauvegarder()
        relu = DepotJSON(self.cheminSauvegarde).charger()
        self.assertIn(1000, [t.ticketID for t in relu.tickets])
        # sauvegarder() n'est pas une modification du dépôt : la version ne bouge pas.
        self.assertEqual(self.contexte.version, version)
        etatApres = reelle.stat().st_mtime_ns if reelle.exists() else None
        self.assertEqual(etatApres, etatAvant)

    def test_verrou_reentrant(self) -> None:
        """Une route qui tient le verrou peut appeler sauvegarder(), qui le reprend."""
        with self.contexte.verrou:
            self.assertTrue(self.contexte.verrou.acquire(blocking=False))
            self.contexte.verrou.release()
            self.contexte.sauvegarder()
        self.assertTrue(self.cheminSauvegarde.is_file())


class TestApplication(TestAvecDossierTemporaire):
    def setUp(self) -> None:
        super().setUp()
        self.contexte = self.nouveauContexte()
        self.app = creerApplication(self.contexte)
        self.client = self.app.test_client()

    def test_fabrique_sans_etat_global(self) -> None:
        self.assertEqual(self.app.config["MAX_CONTENT_LENGTH"], 8 * 1024 * 1024)
        autreContexte = ContexteServeur(cheminSauvegarde=Path(self._dossier.name) / "autre.json")
        autre = creerApplication(autreContexte)
        createur = autreContexte.systeme.utilisateurParId(2)
        createur.createTicket(Ticket(1000, "Seulement ici", Priorite.BASSE))  # type: ignore[union-attr]
        self.assertEqual(self.client.get("/version").get_json(), {"version": 0})
        self.assertGreater(autre.test_client().get("/version").get_json()["version"], 0)
        with self.app.app_context():
            self.assertIs(contexteCourant(), self.contexte)

    def test_version(self) -> None:
        reponse = self.client.get("/version")
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.mimetype, "application/json")
        self.assertEqual(reponse.get_json(), {"version": 0})
        createur = self.contexte.systeme.utilisateurParId(2)
        createur.createTicket(Ticket(1000, "Nouveau", Priorite.BASSE))  # type: ignore[union-attr]
        self.assertGreater(self.client.get("/version").get_json()["version"], 0)

    def test_chemin_inconnu(self) -> None:
        reponse = self.client.get("/inexistant")
        self.assertEqual(reponse.status_code, 404)
        self.assertEqual(
            reponse.get_json(),
            {"erreur": {"type": "RessourceIntrouvable", "message": "Chemin inconnu : /inexistant"}},
        )

    def test_methode_non_permise(self) -> None:
        reponse = self.client.post("/version")
        self.assertEqual(reponse.status_code, 405)
        self.assertEqual(reponse.get_json()["erreur"]["type"], "MethodeNonPermise")
        self.assertIn("GET", reponse.headers["Allow"])


class TestGestionnairesErreurs(TestAvecDossierTemporaire):
    """Des routes d'essai, ajoutées à cette seule application, lèvent chaque exception."""

    EXCEPTIONS: dict[str, Exception] = {
        "transition": TransitionInvalideException(Statut.TERMINE, Statut.FERME),
        "session": SessionIndisponibleException("Session de création en pause"),
        "suppression": SuppressionInterditeException("Ticket 2 déjà assigné"),
        "acces": AccesRefuseException("T Julien n'est pas le créateur du ticket 2"),
        "artefact": ArtefactInvalideException("Format d'image non pris en charge"),
        "requete": RequeteInvalide("Champ obligatoire manquant : statut"),
        "acteur": ActeurNonIdentifie("En-tête X-Acteur-Id absent"),
        "introuvable": RessourceIntrouvable("Ticket introuvable : 99"),
        "panne": RuntimeError("détail interne à ne pas divulguer"),
    }

    def setUp(self) -> None:
        super().setUp()
        app = creerApplication(self.nouveauContexte())

        def lever(nom: str):
            raise self.EXCEPTIONS[nom]

        def lireCorpsBrut():
            return {"taille": len(request.get_data())}

        app.add_url_rule("/_essai/<nom>", view_func=lever)
        app.add_url_rule("/_essai/corps", view_func=lireCorpsBrut, methods=["POST"])
        self.client = app.test_client()

    def verifierErreur(self, nom: str, code: int, typeAttendu: str, message: str) -> None:
        reponse = self.client.get(f"/_essai/{nom}")
        self.assertEqual(reponse.status_code, code, nom)
        self.assertEqual(reponse.get_json(), {"erreur": {"type": typeAttendu, "message": message}})

    def test_exceptions_metier(self) -> None:
        for nom, code in (
            ("transition", 409), ("session", 409), ("suppression", 409),
            ("acces", 403), ("artefact", 400),
        ):
            with self.subTest(nom=nom):
                exception = self.EXCEPTIONS[nom]
                self.verifierErreur(nom, code, type(exception).__name__, str(exception))

    def test_exceptions_api(self) -> None:
        for nom, code in (("requete", 400), ("acteur", 401), ("introuvable", 404)):
            with self.subTest(nom=nom):
                exception = self.EXCEPTIONS[nom]
                self.verifierErreur(nom, code, type(exception).__name__, str(exception))

    def test_erreur_interne(self) -> None:
        console = io.StringIO()
        with redirect_stderr(console):
            self.verifierErreur("panne", 500, "ErreurInterne", MESSAGE_ERREUR_INTERNE)
        self.assertIn("RuntimeError", console.getvalue())
        self.assertIn("détail interne", console.getvalue())

    def test_requete_trop_volumineuse(self) -> None:
        self.assertEqual(self.client.post("/_essai/corps", data=b"x" * 10).status_code, 200)
        reponse = self.client.post("/_essai/corps", data=b"x" * (8 * 1024 * 1024 + 1))
        self.assertEqual(reponse.status_code, 413)
        self.assertEqual(reponse.get_json()["erreur"]["type"], "RequeteTropVolumineuse")


if __name__ == "__main__":
    unittest.main()
