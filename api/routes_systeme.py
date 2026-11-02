"""Routes du système : compteur de version (et, au bonus, service de la page web)."""
from __future__ import annotations

from flask import Blueprint, jsonify

from api.contexte import contexteCourant

blueprint = Blueprint("systeme", __name__)


@blueprint.get("/version")
def lireVersion():
    """Les clients l'interrogent chaque seconde et ne relisent les tickets que s'il change."""
    return jsonify({"version": contexteCourant().version})
