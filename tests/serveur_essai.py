"""Serveur d'essai pour les tests de la GUI : la vraie application Flask, sans réseau.

La passerelle reçoit un transport qui passe chaque requête au client de test de Flask. Les
contrôleurs de la GUI sont ainsi testés contre les vraies routes, sur les données de
démonstration, avec une sauvegarde dans un dossier temporaire.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from api import creerApplication
from api.contexte import ContexteServeur
from ihm.passerelle.client_api import ClientAPI, ReponseHTTP
from ihm.passerelle.objets_lecture import ActeurLu
from ihm.passerelle.source_tickets import SourceTickets

URL_ESSAI = "http://serveur.essai"

# Acteurs de donnees/demo.json.
ADMIN, ABDOUL, JULIEN, MIKE, HEIN = 1, 2, 3, 4, 5


class ServeurEssai:
    """Un serveur neuf sur les données de démonstration ; fermer() efface son dossier."""

    def __init__(self) -> None:
        self._dossier = tempfile.TemporaryDirectory()
        dossier = Path(self._dossier.name)
        self.contexte = ContexteServeur(
            cheminSauvegarde=dossier / "sauvegarde.json", dossierImages=str(dossier / "images")
        )
        self._flask = creerApplication(self.contexte).test_client()
        # (méthode, chemin) de chaque requête reçue, pour vérifier ce que le client envoie.
        self.requetes: list[tuple[str, str]] = []

    def fermer(self) -> None:
        self._dossier.cleanup()

    def transport(
        self, methode: str, url: str, entetes: dict[str, str], corps: bytes | None, delai: float
    ) -> ReponseHTTP:
        chemin = url.removeprefix(URL_ESSAI)
        self.requetes.append((methode, chemin))
        reponse = self._flask.open(chemin, method=methode, headers=entetes, data=corps)
        return ReponseHTTP(reponse.status_code, reponse.get_data())

    def client(self, acteurId: int | None) -> ClientAPI:
        return ClientAPI(URL_ESSAI, acteurId, transport=self.transport)

    def acteur(self, acteurId: int) -> ActeurLu:
        return ActeurLu.depuisJSON(self.client(None).lireActeur(acteurId))

    def session(self, acteurId: int) -> tuple[ActeurLu, ClientAPI, SourceTickets]:
        """Ce que ControleurPrincipal.ouvrirSession() prépare : acteur, client, source chargée."""
        client = self.client(acteurId)
        source = SourceTickets(client)
        source.rafraichir()
        return self.acteur(acteurId), client, source
