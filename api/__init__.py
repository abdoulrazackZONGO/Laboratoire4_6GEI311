"""Serveur de l'API REST : le contrôleur, au sens MVC du rapport."""
from __future__ import annotations

from typing import TYPE_CHECKING

from flask import Flask

from api import routes_acteurs, routes_lots, routes_systeme, routes_tickets
from api.erreurs import enregistrerGestionnaires

if TYPE_CHECKING:
    from api.contexte import ContexteServeur

TAILLE_MAXIMALE_REQUETE = 8 * 1024 * 1024


def creerApplication(contexte: ContexteServeur) -> Flask:
    """Fabrique de l'application : aucun état global, les tests en créent une par contexte."""
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = TAILLE_MAXIMALE_REQUETE
    # Accents lisibles et champs dans l'ordre des représentations, pas triés.
    app.json.ensure_ascii = False  # type: ignore[attr-defined]
    app.json.sort_keys = False  # type: ignore[attr-defined]
    app.extensions["contexte"] = contexte
    enregistrerGestionnaires(app)
    app.register_blueprint(routes_systeme.blueprint)
    app.register_blueprint(routes_acteurs.blueprint)
    app.register_blueprint(routes_tickets.blueprint)
    app.register_blueprint(routes_lots.blueprint)
    return app
