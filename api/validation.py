"""Lecture du corps JSON et des paramètres des requêtes : forme, champs, types et enums.

Chaque fonction lève RequeteInvalide (400) avec un message qui nomme le champ fautif.
Elles ne vérifient que la forme : ce qui est permis ou non reste l'affaire du métier.
"""
from __future__ import annotations

import json
from enum import Enum
from typing import TYPE_CHECKING, Any, TypeVar

from flask import request

from api.erreurs import RequeteInvalide

if TYPE_CHECKING:
    from collections.abc import Iterable

E = TypeVar("E", bound=Enum)


def lireCorps() -> dict[str, Any]:
    """Corps de la requête courante, qui doit être un objet JSON."""
    # get_data() lève 413 au-delà de MAX_CONTENT_LENGTH, avant tout décodage.
    brut = request.get_data()
    if not brut.strip():
        raise RequeteInvalide("Corps JSON absent")
    try:
        corps = json.loads(brut)
    except (UnicodeDecodeError, json.JSONDecodeError) as erreur:
        raise RequeteInvalide(f"Corps JSON illisible : {erreur}") from erreur
    if not isinstance(corps, dict):
        raise RequeteInvalide("Le corps JSON doit être un objet")
    return corps


def verifierChamps(
    corps: dict[str, Any], obligatoires: Iterable[str], facultatifs: Iterable[str] = ()
) -> None:
    """Tous les champs obligatoires sont là, et aucun champ inconnu (faute de frappe)."""
    obligatoires = list(obligatoires)
    for nom in obligatoires:
        if nom not in corps:
            raise RequeteInvalide(f"Champ obligatoire manquant : {nom}")
    permis = set(obligatoires) | set(facultatifs)
    for nom in corps:
        if nom not in permis:
            raise RequeteInvalide(f"Champ inconnu : {nom}")


def entier(corps: dict[str, Any], nom: str) -> int:
    valeur = _valeur(corps, nom)
    # bool est une sous-classe d'int en Python : true ne doit pas passer pour 1.
    if isinstance(valeur, bool) or not isinstance(valeur, int):
        raise RequeteInvalide(f"Le champ {nom} doit être un entier")
    return valeur


def booleen(corps: dict[str, Any], nom: str) -> bool:
    valeur = _valeur(corps, nom)
    if not isinstance(valeur, bool):
        raise RequeteInvalide(f"Le champ {nom} doit être un booléen")
    return valeur


def chaineNonVide(corps: dict[str, Any], nom: str) -> str:
    """Chaîne qui contient autre chose que des blancs ; elle est rendue telle quelle."""
    valeur = _valeur(corps, nom)
    if not isinstance(valeur, str):
        raise RequeteInvalide(f"Le champ {nom} doit être une chaîne")
    if not valeur.strip():
        raise RequeteInvalide(f"Le champ {nom} ne doit pas être vide")
    return valeur


def enumParNom(corps: dict[str, Any], nom: str, typeEnum: type[E]) -> E:
    """Membre de l'enum désigné par son nom exact ("HAUTE", pas "haute")."""
    valeur = _valeur(corps, nom)
    if isinstance(valeur, str) and valeur in typeEnum.__members__:
        return typeEnum[valeur]
    permises = ", ".join(typeEnum.__members__)
    raise RequeteInvalide(f"Valeur invalide pour {nom} : {valeur!r} (attendu : {permises})")


# ------------------------------------------------------------------ paramètres de requête
# Ils arrivent toujours sous forme de texte. enumParNom() s'y applique telle quelle.


def lireParametres(permis: Iterable[str]) -> dict[str, str]:
    """Paramètres de la requête courante ; un nom inconnu (faute de frappe) est refusé.

    Sans ce refus, ?statu=FERME renverrait tous les tickets, sans aucune erreur.
    """
    permis = set(permis)
    parametres = request.args.to_dict()
    for nom in parametres:
        if nom not in permis:
            raise RequeteInvalide(f"Paramètre inconnu : {nom}")
    return parametres


def parametreEntier(parametres: dict[str, str], nom: str) -> int:
    valeur = _valeur(parametres, nom)
    try:
        return int(valeur)
    except ValueError:
        raise RequeteInvalide(f"Le paramètre {nom} doit être un entier : {valeur!r}") from None


def _valeur(corps: dict[str, Any], nom: str) -> Any:
    if nom not in corps:
        raise RequeteInvalide(f"Champ obligatoire manquant : {nom}")
    return corps[nom]
