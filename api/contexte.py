"""État partagé du serveur : le système de tickets unique et ce qui l'entoure."""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from flask import current_app

from api.registre_brouillons import RegistreBrouillons
from modele.observateur import ObservateurTickets
from persistance.depot_json import DepotJSON, PersistanceException
from persistance.stockage_images import StockageImages

if TYPE_CHECKING:
    from modele.systeme_tickets import SystemeTickets
    from modele.ticket import Ticket

CHEMIN_SAUVEGARDE = "donnees/sauvegarde.json"
CHEMIN_DEMO = "donnees/demo.json"
DOSSIER_IMAGES = "donnees/images"
# Attentes entre les essais de sauvegarde (secondes) : 0,6 s au pire, sous le délai du client.
ATTENTES_SAUVEGARDE: tuple[float, ...] = (0.02, 0.04, 0.08, 0.16, 0.3)


class CompteurVersion(ObservateurTickets):
    """Compte les changements du dépôt ; les clients relisent les tickets quand il bouge.

    C'est ce qui remplace le patron Observateur entre deux processus : la GUI ne peut
    pas s'abonner au SystemeTickets du serveur, elle interroge GET /version.
    """

    def __init__(self) -> None:
        self._valeur: int = 0

    @property
    def valeur(self) -> int:
        return self._valeur

    def ticketModifie(self, ticket: Ticket) -> None:
        self._valeur += 1

    def ticketAjoute(self, ticket: Ticket) -> None:
        self._valeur += 1

    def ticketRetire(self, ticket: Ticket) -> None:
        self._valeur += 1


class ContexteServeur:
    """Détient le SystemeTickets unique du serveur, sa sauvegarde et son verrou.

    Le serveur Flask sert plusieurs requêtes à la fois : tout accès au système passe
    par le verrou. Il est réentrant pour qu'une route puisse le prendre puis appeler
    sauvegarder(), qui le reprend.
    """

    def __init__(
        self,
        cheminSauvegarde: str | os.PathLike[str] = CHEMIN_SAUVEGARDE,
        cheminDemo: str | os.PathLike[str] = CHEMIN_DEMO,
        dossierImages: str = DOSSIER_IMAGES,
    ) -> None:
        self._depot: DepotJSON = DepotJSON(cheminSauvegarde)
        self._stockage: StockageImages = StockageImages(dossierImages)
        self._brouillons: RegistreBrouillons = RegistreBrouillons()
        self._verrou: threading.RLock = threading.RLock()
        self._systeme, self._sourceChargee = self._charger(Path(cheminDemo))
        # Abonné après le chargement : la version vaut 0 au démarrage.
        self._compteur: CompteurVersion = CompteurVersion()
        self._systeme.abonner(self._compteur)

    @property
    def systeme(self) -> SystemeTickets:
        return self._systeme

    @property
    def depot(self) -> DepotJSON:
        return self._depot

    @property
    def stockage(self) -> StockageImages:
        return self._stockage

    @property
    def brouillons(self) -> RegistreBrouillons:
        """Brouillons ouverts, en mémoire seulement : ils ne survivent pas à un redémarrage."""
        return self._brouillons

    @property
    def verrou(self) -> threading.RLock:
        return self._verrou

    @property
    def sourceChargee(self) -> Path:
        """Fichier réellement chargé au démarrage : la sauvegarde, ou à défaut la démo."""
        return self._sourceChargee

    @property
    def version(self) -> int:
        with self._verrou:
            return self._compteur.valeur

    def sauvegarder(self) -> None:
        """Écrit tout le système dans la sauvegarde ; ne touche pas à la version.

        Sous Windows, un autre processus (indexation, antivirus) peut tenir le fichier
        quelques millisecondes juste après son remplacement : os.replace() lève alors
        PermissionError. Le lab 3 sauvegardait rarement ; le serveur le fait à chaque
        modification, d'où ces nouveaux essais. Après le dernier, l'erreur remonte (500).
        """
        with self._verrou:
            for attente in ATTENTES_SAUVEGARDE:
                try:
                    self._depot.sauvegarder(self._systeme)
                    return
                except PermissionError:
                    time.sleep(attente)
            self._depot.sauvegarder(self._systeme)

    # ------------------------------------------------------------------ chargement

    def _charger(self, cheminDemo: Path) -> tuple[SystemeTickets, Path]:
        """Même règle que ControleurPrincipal._charger(), mais les messages vont à la console."""
        if self._depot.existe():
            try:
                return self._lire(self._depot), self._depot.chemin
            except PersistanceException as erreur:
                print(
                    f"{erreur}\nLe serveur démarre sur les données de démonstration.",
                    file=sys.stderr,
                )
        # Une démonstration illisible n'est pas rattrapée : sans elle, aucun acteur.
        demo = DepotJSON(cheminDemo)
        return self._lire(demo), demo.chemin

    @staticmethod
    def _lire(depot: DepotJSON) -> SystemeTickets:
        """Charge un fichier et signale ses avertissements (artefacts introuvables)."""
        systeme = depot.charger()
        if depot.avertissements:
            print(
                f"Chargement de {depot.chemin.as_posix()} :\n" + "\n".join(depot.avertissements),
                file=sys.stderr,
            )
        return systeme


def contexteCourant() -> ContexteServeur:
    """Contexte de l'application Flask qui traite la requête (rangé par creerApplication)."""
    return current_app.extensions["contexte"]
