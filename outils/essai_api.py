"""Vérification rapide avant la démo : quelques requêtes réelles contre un serveur lancé.

Serveur démarré (python serveur.py), lancer :  python outils/essai_api.py [--url URL]

Chaque requête s'affiche avec son code et le code attendu. Les tickets de démonstration ne
sont que lus : le script crée son propre ticket, l'assigne, tente une transition refusée,
puis le désassigne par un lot. Ce ticket reste ensuite dans donnees/sauvegarde.json, car un
ticket déjà assigné ne peut plus être supprimé. Pour repartir de la démo : arrêter le
serveur, supprimer donnees/sauvegarde.json, relancer le serveur.

Bibliothèque standard seulement, comme la GUI. Code de sortie : 0 si chaque réponse a le
code attendu, 1 sinon, 2 si le serveur ne répond pas.
"""
from __future__ import annotations

import argparse
import http.client
import json
import sys
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, Any, TextIO

if TYPE_CHECKING:
    from collections.abc import Callable

URL_PAR_DEFAUT = "http://127.0.0.1:5000"
DELAI = 5.0
# Aucun proxy : un proxy système pourrait sinon intercepter 127.0.0.1.
_OUVREUR = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class ServeurInjoignable(Exception):
    """Le serveur ne répond pas : il n'est pas lancé, ou l'adresse est fausse."""


class Essai:
    """Envoie les requêtes, affiche chacune et compte celles dont le code surprend."""

    def __init__(self, url: str, sortie: TextIO) -> None:
        self._url: str = url.rstrip("/")
        self._sortie: TextIO = sortie
        self._ecarts: int = 0

    @property
    def ecarts(self) -> int:
        return self._ecarts

    def afficher(self, texte: str = "") -> None:
        print(texte, file=self._sortie)

    def requete(
        self,
        methode: str,
        chemin: str,
        attendu: int,
        acteurId: int | None = None,
        corps: object | None = None,
        resume: Callable[[Any], str] | None = None,
    ) -> Any:
        """Le corps JSON de la réponse, ou None ; un code inattendu est compté, pas levé."""
        code, reponse = self._envoyer(methode, chemin, acteurId, corps)
        conforme = code == attendu
        if not conforme:
            self._ecarts += 1
        if isinstance(reponse, dict) and isinstance(reponse.get("erreur"), dict):
            detail = f"{reponse['erreur'].get('type')} : {reponse['erreur'].get('message')}"
        elif conforme and resume is not None:
            detail = resume(reponse)
        else:
            detail = ""
        marque = "OK" if conforme else "KO"
        self.afficher(f"[{marque}] {code} (attendu {attendu})  {methode:<6} {chemin}  {detail}")
        return reponse

    def _envoyer(
        self, methode: str, chemin: str, acteurId: int | None, corps: object | None
    ) -> tuple[int, Any]:
        entetes = {} if acteurId is None else {"X-Acteur-Id": str(acteurId)}
        donnees = None
        if corps is not None:
            donnees = json.dumps(corps, ensure_ascii=False).encode("utf-8")
            entetes["Content-Type"] = "application/json"
        requete = urllib.request.Request(
            self._url + chemin, data=donnees, headers=entetes, method=methode
        )
        try:
            try:
                with _OUVREUR.open(requete, timeout=DELAI) as reponse:
                    return reponse.status, _lireJSON(reponse.read())
            except urllib.error.HTTPError as erreur:
                # Un code 4xx ou 5xx est une réponse du serveur : on la compare à l'attendu.
                with erreur:
                    return erreur.code, _lireJSON(erreur.read())
        except (OSError, http.client.HTTPException) as erreur:
            raise ServeurInjoignable(f"{self._url} : {erreur}") from erreur


def _lireJSON(octets: bytes) -> Any:
    try:
        return json.loads(octets.decode("utf-8")) if octets else None
    except (UnicodeDecodeError, ValueError):
        return None


def executer(url: str, sortie: TextIO | None = None) -> int:
    """Lecture, création, assignation, transition refusée et lot ; rend le code de sortie.

    sys.stdout est lu à l'appel, pas à l'import : redirect_stdout() peut alors le remplacer.
    """
    essai = Essai(url, sortie if sortie is not None else sys.stdout)
    essai.afficher(f"Essai de l'API sur {url}")
    try:
        return _scenario(essai)
    except ServeurInjoignable as erreur:
        essai.afficher(f"Serveur injoignable ({erreur}). Est-il lancé (python serveur.py) ?")
        return 2


def _scenario(essai: Essai) -> int:
    version = essai.requete("GET", "/version", 200, resume=lambda v: f"version {v['version']}")
    acteurs = essai.requete("GET", "/acteurs", 200, resume=lambda a: f"{len(a)} acteurs")
    admins = [a for a in acteurs or [] if a.get("role") == "Admin"]
    users = [a for a in acteurs or [] if a.get("role") == "User"]
    if not admins or len(users) < 2:
        essai.afficher("Arrêt : il faut au moins un Admin et deux User dans les données.")
        return 1
    admin, createur, assigne = admins[0], users[0], users[1]
    essai.requete(
        "GET", "/tickets", 200, admin["id"], resume=lambda t: f"{len(t)} tickets (lecture seule)"
    )

    cree = essai.requete(
        "POST",
        "/tickets",
        201,
        createur["id"],
        {"titre": "Essai avant la démo", "priorite": "BASSE", "texte": "Créé par essai_api.py"},
        resume=lambda r: f"ticket #{r['ticket']['id']} créé par {createur['nom']}",
    )
    ticketId = cree.get("ticket", {}).get("id") if isinstance(cree, dict) else None
    if not isinstance(ticketId, int):
        essai.afficher("Arrêt : sans ticket créé, la suite de l'essai n'a pas de sens.")
        return 1
    chemin = f"/ticket/{ticketId}"
    essai.requete("GET", chemin, 200, createur["id"], resume=lambda t: f"statut {t['statut']}")
    essai.requete(
        "PATCH",
        chemin,
        200,
        admin["id"],
        {"statut": "ASSIGNE", "assigneId": assigne["id"]},
        resume=lambda t: f"assigné à {t['assigne']['nom']}",
    )
    # ASSIGNE -> TERMINE n'existe pas : il faut passer par VALIDATION. L'état refuse (409).
    essai.requete("PATCH", chemin, 409, admin["id"], {"statut": "TERMINE"})
    essai.requete(
        "POST",
        f"/acteur/{admin['id']}/lots",
        200,
        admin["id"],
        {"action": "desassigner", "ticketIds": [ticketId]},
        resume=lambda r: f"lot : {r['nombreSucces']} succès, {r['nombreRefus']} refus",
    )
    essai.requete(
        "GET",
        "/version",
        200,
        resume=lambda v: f"version {v['version']} (au départ : {version['version']})",
    )

    essai.afficher()
    if essai.ecarts:
        essai.afficher(f"{essai.ecarts} réponse(s) inattendue(s) : à corriger avant la démo.")
    else:
        essai.afficher("Toutes les réponses sont celles attendues.")
    essai.afficher(
        f"Le ticket #{ticketId} reste dans les données. Pour repartir de la démo : arrêter le "
        "serveur, supprimer donnees/sauvegarde.json, relancer le serveur."
    )
    return 1 if essai.ecarts else 0


def main(argv: list[str] | None = None) -> int:
    lecteur = argparse.ArgumentParser(description="Vérification rapide de l'API avant la démo.")
    lecteur.add_argument("--url", default=URL_PAR_DEFAUT, help=f"défaut : {URL_PAR_DEFAUT}")
    arguments = lecteur.parse_args(argv)
    return executer(arguments.url)


if __name__ == "__main__":
    # Une console qui ne sait pas afficher un accent ne doit pas faire échouer l'essai.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    sys.exit(main())
