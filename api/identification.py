"""Identification de l'acteur qui fait la requête, par l'en-tête X-Acteur-Id.

Il n'y a pas de mot de passe, comme au lab 3 : l'en-tête désigne l'acteur choisi à la
connexion. Identifier n'est pas autoriser : ce que l'acteur a le droit de faire reste
décidé par le métier (états, acteurs), qui lève ses propres exceptions.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from flask import request

from api.contexte import contexteCourant
from api.erreurs import ActeurNonIdentifie

if TYPE_CHECKING:
    from acteurs.utilisateur_systeme import UtilisateurSysteme

EN_TETE_ACTEUR = "X-Acteur-Id"


def acteurCourant() -> UtilisateurSysteme:
    """Première étape de toute route qui exige un acteur : 401 s'il n'est pas identifié."""
    valeur = request.headers.get(EN_TETE_ACTEUR)
    if valeur is None:
        raise ActeurNonIdentifie(f"En-tête {EN_TETE_ACTEUR} absent")
    try:
        identifiant = int(valeur)
    except ValueError:
        raise ActeurNonIdentifie(f"En-tête {EN_TETE_ACTEUR} non entier : {valeur!r}") from None
    contexte = contexteCourant()
    with contexte.verrou:
        acteur = contexte.systeme.utilisateurParId(identifiant)
    if acteur is None:
        raise ActeurNonIdentifie(f"Acteur inconnu : {identifiant}")
    return acteur
