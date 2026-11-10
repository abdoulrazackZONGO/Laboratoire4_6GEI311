"""Routes du système : compteur de version, et service de la page web du bonus (W1)."""
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, Response, jsonify

from api.contexte import contexteCourant

blueprint = Blueprint("systeme", __name__)

DOSSIER_WEB = Path(__file__).resolve().parent.parent / "web"
# Types écrits ici et non devinés : sous Windows, mimetypes lit le registre, qui peut se
# tromper (pour .js, par exemple), et nosniff empêcherait alors le navigateur de corriger.
_TYPES_WEB: dict[str, str] = {
    "index.html": "text/html; charset=utf-8",
    "app.js": "text/javascript; charset=utf-8",
    "style.css": "text/css; charset=utf-8",
}


@blueprint.get("/version")
def lireVersion():
    """Les clients l'interrogent chaque seconde et ne relisent les tickets que s'il change."""
    return jsonify({"version": contexteCourant().version})


@blueprint.get("/")
def pageWeb():
    """La page web : un client de l'API comme la GUI, hors du contrat (voir openapi.yaml)."""
    return _fichierWeb("index.html")


@blueprint.get("/app.js")
def scriptWeb():
    return _fichierWeb("app.js")


@blueprint.get("/style.css")
def styleWeb():
    return _fichierWeb("style.css")


def _fichierWeb(nom: str) -> Response:
    """Un des trois fichiers de web/, jamais un nom venu de l'URL.

    Lu en mémoire plutôt que par send_file() : le fichier ne reste pas ouvert après la
    réponse. no-cache : une page modifiée se recharge vraiment, sans vider le cache.
    """
    reponse = Response((DOSSIER_WEB / nom).read_bytes(), content_type=_TYPES_WEB[nom])
    reponse.headers["Cache-Control"] = "no-cache"
    reponse.headers["X-Content-Type-Options"] = "nosniff"
    return reponse
