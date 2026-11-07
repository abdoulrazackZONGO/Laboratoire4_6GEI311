"""Erreurs de l'API : format JSON commun, table exception -> code HTTP, gestionnaires Flask."""
from __future__ import annotations

import traceback
from typing import TYPE_CHECKING

from flask import jsonify, request
from werkzeug.exceptions import HTTPException

from modele.exceptions import (
    AccesRefuseException,
    ArtefactInvalideException,
    SessionIndisponibleException,
    SuppressionInterditeException,
    TransitionInvalideException,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from flask import Flask, Response

MESSAGE_ERREUR_INTERNE = "Erreur interne du serveur"


class ErreurAPI(Exception):
    """Erreur propre à l'API, détectée avant d'atteindre le métier."""

    code: int = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)


class RequeteInvalide(ErreurAPI):
    """Corps JSON illisible, champ manquant ou en trop, type ou enum invalide."""

    code = 400


class ActeurNonIdentifie(ErreurAPI):
    """En-tête X-Acteur-Id absent, non entier ou inconnu."""

    code = 401


class RessourceIntrouvable(ErreurAPI):
    """Acteur, ticket, brouillon ou image introuvable."""

    code = 404


class RequeteTropVolumineuse(ErreurAPI):
    """Image au-delà de sa limite ; Flask lève lui-même le 413 au-delà de la limite du corps."""

    code = 413


# Table de CLAUDE.md. Le 403 « mauvais rôle » ou « acteur du chemin différent de
# l'en-tête » n'a pas de classe à lui : la route lève AccesRefuseException.
CODES_EXCEPTIONS: dict[type[Exception], int] = {
    TransitionInvalideException: 409,
    SessionIndisponibleException: 409,
    SuppressionInterditeException: 409,
    AccesRefuseException: 403,
    ArtefactInvalideException: 400,
    RequeteInvalide: RequeteInvalide.code,
    ActeurNonIdentifie: ActeurNonIdentifie.code,
    RessourceIntrouvable: RessourceIntrouvable.code,
    RequeteTropVolumineuse: RequeteTropVolumineuse.code,
}

# Erreurs HTTP levées par Flask lui-même (routage, taille du corps).
_TYPES_HTTP: dict[int, str] = {
    400: "RequeteInvalide",
    404: "RessourceIntrouvable",
    405: "MethodeNonPermise",
    413: "RequeteTropVolumineuse",
}


def reponseErreur(typeErreur: str, message: str, code: int) -> Response:
    """Réponse au format {"erreur": {"type", "message"}} de openapi.yaml."""
    reponse = jsonify({"erreur": {"type": typeErreur, "message": message}})
    reponse.status_code = code
    return reponse


def enregistrerGestionnaires(app: Flask) -> None:
    """Installe les gestionnaires : exceptions connues, erreurs HTTP, puis tout le reste."""
    for classe, code in CODES_EXCEPTIONS.items():
        app.register_error_handler(classe, _gestionnaireMetier(code))
    app.register_error_handler(HTTPException, _erreurHTTP)
    app.register_error_handler(Exception, _erreurInterne)


def _gestionnaireMetier(code: int) -> Callable[[Exception], Response]:
    """Le type et le message sont ceux de l'exception, tels quels : le client la relève."""

    def gerer(erreur: Exception) -> Response:
        return reponseErreur(type(erreur).__name__, str(erreur), code)

    return gerer


def _erreurHTTP(erreur: HTTPException) -> Response:
    code = erreur.code or 500
    if code == 404:
        message = f"Chemin inconnu : {request.path}"
    elif code == 405:
        message = f"Méthode {request.method} non permise sur {request.path}"
    elif code == 413:
        message = "Requête trop volumineuse (8 Mo au plus)"
    else:
        message = erreur.description or erreur.name
    reponse = reponseErreur(_TYPES_HTTP.get(code, erreur.name.replace(" ", "")), message, code)
    # Un 405 doit dire quelles méthodes sont permises (en-tête Allow, RFC 9110).
    for nom, valeur in erreur.get_headers():
        if nom.lower() == "allow":
            reponse.headers["Allow"] = valeur
    return reponse


def _erreurInterne(erreur: Exception) -> Response:
    """Message générique pour le client ; la trace complète reste dans la console du serveur."""
    traceback.print_exception(erreur)
    return reponseErreur("ErreurInterne", MESSAGE_ERREUR_INTERNE, 500)
