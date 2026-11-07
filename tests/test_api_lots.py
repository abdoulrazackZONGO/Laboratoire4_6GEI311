"""Tests de S3 : lots de l'Admin (POST /acteur/{acteurId}/lots).

Lancer depuis la racine du dépôt :  python -m unittest discover -s tests -t . -v
"""
from __future__ import annotations

import unittest
from typing import Any

from modele.enums import Statut
from tests.test_api_tickets import ADMIN, HEIN, JULIEN, MIKE, TestEcriture

# Exemple RapportLot de openapi.yaml : le lot [6, 7, 3] assigné à Mike Tonny.
RAPPORT_LOT = {
    "libelle": "Lot administrateur",
    "succes": ["Assigner le ticket #6 à Mike Tonny", "Assigner le ticket #7 à Mike Tonny"],
    "refus": [
        {
            "operation": "Assigner le ticket #3 à Mike Tonny",
            "motif": "Transition invalide : impossible de passer de l'état FERME au statut ASSIGNE",
        }
    ],
    "nombreSucces": 2,
    "nombreRefus": 1,
    "ticketId": None,
}


class TestLots(TestEcriture):
    def lot(self, acteurId: int | None = ADMIN, chemin: int = ADMIN, **corps: Any):
        return self.requete("POST", f"/acteur/{chemin}/lots", acteurId, corps)

    def statuts(self, *ticketIds: int) -> list[Statut]:
        return [self.ticket(ticketId).status for ticketId in ticketIds]

    def test_refus_dans_le_rapport(self) -> None:
        """L'exemple du contrat : deux succès, un refus, et la réponse reste 200."""
        version = self.contexte.version
        reponse = self.lot(action="assigner", ticketIds=[6, 7, 3], assigneId=MIKE)
        self.assertEqual(reponse.status_code, 200, reponse.get_data(as_text=True))
        self.assertEqual(reponse.get_json(), RAPPORT_LOT)
        self.assertEqual(self.statuts(6, 7, 3), [Statut.ASSIGNE, Statut.ASSIGNE, Statut.FERME])
        self.assertGreater(self.contexte.version, version)

    def test_sauvegarde_rechargee(self) -> None:
        self.lot(action="assigner", ticketIds=[6, 7, 3], assigneId=MIKE)
        systeme = self.recharger()
        for ticketId in (6, 7):
            ticket = systeme.ticketParId(ticketId)
            self.assertIs(ticket.status, Statut.ASSIGNE)
            self.assertEqual(ticket.assignedUser.id, MIKE)
        self.assertIs(systeme.ticketParId(3).status, Statut.FERME)

    def test_desassigner(self) -> None:
        rapport = self.lot(action="desassigner", ticketIds=[2]).get_json()
        self.assertEqual(rapport["nombreSucces"], 1)
        self.assertIs(self.ticket(2).status, Statut.OUVERT)
        self.assertIsNone(self.ticket(2).assignedUser)

    def test_valider(self) -> None:
        rapport = self.lot(action="valider", ticketIds=[8]).get_json()
        self.assertEqual(rapport["nombreSucces"], 1)
        self.assertIs(self.ticket(8).status, Statut.TERMINE)

    def test_fermer(self) -> None:
        rapport = self.lot(action="fermer", ticketIds=[6, 2]).get_json()
        self.assertEqual(rapport["nombreSucces"], 2)
        self.assertEqual(self.statuts(6, 2), [Statut.FERME, Statut.FERME])

    def test_tout_refuse_ne_sauvegarde_rien(self) -> None:
        version = self.contexte.version
        reponse = self.lot(action="fermer", ticketIds=[1, 3])
        self.assertEqual(reponse.status_code, 200)
        rapport = reponse.get_json()
        self.assertEqual(rapport["nombreSucces"], 0)
        self.assertEqual(rapport["nombreRefus"], 2)
        self.verifierRienEcrit(version)

    def test_doublon_laisse_au_metier(self) -> None:
        rapport = self.lot(action="fermer", ticketIds=[6, 6]).get_json()
        self.assertEqual(rapport["nombreSucces"], 1)
        self.assertEqual(rapport["nombreRefus"], 1)

    def test_identifiant_inconnu_ne_modifie_rien(self) -> None:
        version = self.contexte.version
        reponse = self.lot(action="fermer", ticketIds=[6, 999, 7])
        self.verifierErreur(reponse, 404, "RessourceIntrouvable")
        self.assertEqual(reponse.get_json()["erreur"]["message"], "Ticket introuvable : 999")
        self.assertEqual(self.statuts(6, 7), [Statut.OUVERT, Statut.OUVERT])
        self.verifierRienEcrit(version)

    def test_assigne_inconnu_ne_modifie_rien(self) -> None:
        version = self.contexte.version
        reponse = self.lot(action="assigner", ticketIds=[6], assigneId=99)
        self.verifierErreur(reponse, 404, "RessourceIntrouvable")
        self.assertIs(self.ticket(6).status, Statut.OUVERT)
        self.verifierRienEcrit(version)

    def test_assigne_qui_n_est_pas_un_user(self) -> None:
        version = self.contexte.version
        reponse = self.lot(action="assigner", ticketIds=[6], assigneId=ADMIN)
        self.verifierErreur(reponse, 400, "RequeteInvalide")
        self.verifierRienEcrit(version)

    def test_format_du_corps(self) -> None:
        for corps in (
            {},
            {"action": "fermer"},
            {"ticketIds": [6]},
            {"action": "supprimer", "ticketIds": [6]},
            {"action": "FERMER", "ticketIds": [6]},
            {"action": "fermer", "ticketIds": []},
            {"action": "fermer", "ticketIds": 6},
            {"action": "fermer", "ticketIds": ["6"]},
            {"action": "fermer", "ticketIds": [True]},
            {"action": "fermer", "ticketIds": [6], "autre": 1},
            {"action": "assigner", "ticketIds": [6]},
            {"action": "assigner", "ticketIds": [6], "assigneId": "4"},
            {"action": "fermer", "ticketIds": [6], "assigneId": MIKE},
        ):
            with self.subTest(corps=corps):
                version = self.contexte.version
                self.verifierErreur(self.lot(**corps), 400, "RequeteInvalide")
                self.verifierRienEcrit(version)

    def test_reserve_aux_admin(self) -> None:
        """Un User, même sur son propre chemin, n'a pas accès aux lots."""
        reponse = self.lot(JULIEN, JULIEN, action="fermer", ticketIds=[6])
        self.verifierErreur(reponse, 403, "AccesRefuseException")
        self.assertIs(self.ticket(6).status, Statut.OUVERT)

    def test_acteur_du_chemin_different(self) -> None:
        for acteurId, chemin in ((JULIEN, ADMIN), (ADMIN, JULIEN), (ADMIN, 99)):
            with self.subTest(acteur=acteurId, chemin=chemin):
                reponse = self.lot(acteurId, chemin, action="fermer", ticketIds=[6])
                self.verifierErreur(reponse, 403, "AccesRefuseException")
        self.assertIs(self.ticket(6).status, Statut.OUVERT)

    def test_acteur_non_identifie(self) -> None:
        for acteurId in (None, 99):
            with self.subTest(acteur=acteurId):
                reponse = self.lot(acteurId, action="fermer", ticketIds=[6])
                self.verifierErreur(reponse, 401, "ActeurNonIdentifie")

    def test_ordre_des_controles(self) -> None:
        """401, puis 403 (chemin et rôle), puis 400, puis 404."""
        self.verifierErreur(self.lot(None), 401, "ActeurNonIdentifie")
        self.verifierErreur(self.lot(HEIN), 403, "AccesRefuseException")
        self.verifierErreur(self.lot(HEIN, HEIN), 403, "AccesRefuseException")
        self.verifierErreur(self.lot(action="fermer", ticketIds=[]), 400, "RequeteInvalide")
        self.verifierErreur(self.lot(action="fermer", ticketIds=[999]), 404, "RessourceIntrouvable")

    def test_pas_de_lecture_d_un_lot(self) -> None:
        """Un lot n'est pas conservé : GET répond 405."""
        reponse = self.requete("GET", f"/acteur/{ADMIN}/lots", ADMIN)
        self.verifierErreur(reponse, 405, "MethodeNonPermise")


if __name__ == "__main__":
    unittest.main()
