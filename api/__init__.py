"""Serveur de l'API REST : le contrôleur, au sens MVC du rapport."""
from __future__ import annotations

from typing import TYPE_CHECKING

from flask import Flask

from api import routes_acteurs, routes_brouillons, routes_lots, routes_systeme, routes_tickets
from api.erreurs import enregistrerGestionnaires

if TYPE_CHECKING:
    from api.contexte import ContexteServeur

TAILLE_MAXIMALE_REQUETE = 8 * 1024 * 1024


def creerApplication(contexte: ContexteServeur) -> Flask:
    """Fabrique de l'application : aucun état global, les tests en créent une par contexte."""
    # Sans dossier static : Flask ajouterait sinon GET /static/<filename>, hors du contrat.
    # La page web du bonus est servie par routes_systeme, comme toute autre route.
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = TAILLE_MAXIMALE_REQUETE
    # Accents lisibles et champs dans l'ordre des représentations, pas triés.
    app.json.ensure_ascii = False  # type: ignore[attr-defined]
    app.json.sort_keys = False  # type: ignore[attr-defined]
    # JSON est toujours en UTF-8, mais Windows PowerShell 5.1 lit autrement une réponse qui
    # ne le dit pas (« Ã© » au lieu de « é »). Erreurs comprises : elles passent par jsonify().
    app.json.mimetype = "application/json; charset=utf-8"  # type: ignore[attr-defined]
    app.extensions["contexte"] = contexte
    enregistrerGestionnaires(app)
    app.register_blueprint(routes_systeme.blueprint)
    app.register_blueprint(routes_acteurs.blueprint)
    app.register_blueprint(routes_tickets.blueprint)
    app.register_blueprint(routes_lots.blueprint)
    app.register_blueprint(routes_brouillons.blueprint)
    return app
