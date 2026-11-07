"""Erreurs côté client : serveur injoignable, et reconstruction des erreurs reçues de l'API.

Le serveur répond à une erreur par {"erreur": {"type", "message"}}. Le client relève une
exception de même nom et de même message : FenetreBase.executer() l'affiche alors comme
au lab 3, sans savoir qu'elle a traversé le réseau.
"""
from __future__ import annotations

import json

from modele.exceptions import (
    AccesRefuseException,
    ArtefactInvalideException,
    SessionIndisponibleException,
    SuppressionInterditeException,
    TransitionInvalideException,
)


class ServeurInjoignable(Exception):
    """Le serveur ne répond pas : arrêté, mauvaise adresse, délai dépassé ou connexion coupée."""

    def __init__(self, url: str, motif: str) -> None:
        super().__init__(f"Serveur injoignable ({url}) : {motif}")
        self._url: str = url

    @property
    def url(self) -> str:
        return self._url


class ErreurServeur(Exception):
    """Erreur renvoyée par l'API qui ne vient pas du métier : format de la requête,
    identification, ressource introuvable ou panne du serveur.

    Les sous-classes portent les noms des erreurs de api/erreurs.py. Le client ne peut pas
    importer api (règle 3 de CLAUDE.md) : il les redéclare, avec le code HTTP reçu.
    """

    def __init__(self, message: str, code: int, typeErreur: str | None = None) -> None:
        super().__init__(message)
        self._code: int = code
        self._typeErreur: str = typeErreur if typeErreur is not None else type(self).__name__

    @property
    def code(self) -> int:
        return self._code

    @property
    def typeErreur(self) -> str:
        """Champ type de la réponse ; utile pour un type que le client ne connaît pas."""
        return self._typeErreur


class RequeteInvalide(ErreurServeur):
    """400 : corps JSON illisible, champ manquant ou en trop, type ou enum invalide."""


class ActeurNonIdentifie(ErreurServeur):
    """401 : en-tête X-Acteur-Id absent, non entier ou inconnu."""


class RessourceIntrouvable(ErreurServeur):
    """404 : acteur, ticket, brouillon, image ou chemin introuvable."""


class MethodeNonPermise(ErreurServeur):
    """405 : méthode HTTP absente sur ce chemin."""


class RequeteTropVolumineuse(ErreurServeur):
    """413 : corps au-delà de la limite du serveur (une image trop lourde, par exemple)."""


class ErreurInterne(ErreurServeur):
    """500 : erreur imprévue du serveur ; la trace complète est dans sa console."""


class ReponseInvalide(ErreurServeur):
    """Réponse que le client ne sait pas lire : corps qui n'est pas du JSON, ou erreur sans
    le format {"erreur": {"type", "message"}}. C'est un écart au contrat de openapi.yaml."""


# Exceptions que FenetreBase.executer() affichera en plus des cinq exceptions métier (C3).
EXCEPTIONS_PASSERELLE: tuple[type[Exception], ...] = (ServeurInjoignable, ErreurServeur)

_EXCEPTIONS_METIER: dict[str, type[Exception]] = {
    classe.__name__: classe
    for classe in (
        TransitionInvalideException,
        SessionIndisponibleException,
        SuppressionInterditeException,
        AccesRefuseException,
        ArtefactInvalideException,
    )
}

_ERREURS_API: dict[str, type[ErreurServeur]] = {
    classe.__name__: classe
    for classe in (
        RequeteInvalide,
        ActeurNonIdentifie,
        RessourceIntrouvable,
        MethodeNonPermise,
        RequeteTropVolumineuse,
        ErreurInterne,
    )
}


def exceptionDepuisReponse(code: int, corps: bytes) -> Exception:
    """Exception à relever pour une réponse d'erreur (code 4xx ou 5xx) du serveur."""
    try:
        erreur = json.loads(corps.decode("utf-8"))["erreur"]
        typeErreur, message = erreur["type"], erreur["message"]
    except (UnicodeDecodeError, ValueError, KeyError, TypeError):
        return ReponseInvalide(f"Réponse d'erreur illisible du serveur (code {code})", code)
    if not isinstance(typeErreur, str) or not isinstance(message, str):
        return ReponseInvalide(f"Réponse d'erreur illisible du serveur (code {code})", code)
    classeMetier = _EXCEPTIONS_METIER.get(typeErreur)
    if classeMetier is not None:
        return _reconstruire(classeMetier, message)
    classeAPI = _ERREURS_API.get(typeErreur)
    if classeAPI is not None:
        return classeAPI(message, code)
    # Type inconnu (serveur plus récent que le client) : le message reste affichable.
    return ErreurServeur(message, code, typeErreur)


def _reconstruire(classe: type[Exception], message: str) -> Exception:
    """Crée l'exception métier avec le message reçu, sans appeler son constructeur.

    TransitionInvalideException.__init__ attend deux statuts et compose lui-même son
    message ; le client n'a que ce message. On crée donc l'objet par __new__, puis on
    l'initialise comme une Exception ordinaire : même classe, même str(), et le modèle
    reste inchangé (option A, décidée le 7 novembre). Les autres exceptions métier
    passent par le même chemin, pour un traitement uniforme.
    """
    erreur = classe.__new__(classe)
    Exception.__init__(erreur, message)
    return erreur
