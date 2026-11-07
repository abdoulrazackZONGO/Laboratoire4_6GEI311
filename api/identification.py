"""Identification de l'acteur qui fait la requête, par l'en-tête X-Acteur-Id.

Il n'y a pas de mot de passe, comme au lab 3 : l'en-tête désigne l'acteur choisi à la
connexion. Identifier n'est pas autoriser : ce que l'acteur a le droit de faire reste
décidé par le métier (états, acteurs), qui lève ses propres exceptions. Ce module ne
vérifie que les règles d'accès propres au contrat : le rôle exigé par un chemin, et
l'acteur nommé dans le chemin.
"""
from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, cast

from flask import request

from api.contexte import contexteCourant
from api.erreurs import ActeurNonIdentifie, RequeteInvalide, RessourceIntrouvable
from modele.exceptions import AccesRefuseException

if TYPE_CHECKING:
    from acteurs.user import User
    from acteurs.utilisateur_systeme import UtilisateurSysteme
    from modele.systeme_tickets import SystemeTickets

EN_TETE_ACTEUR = "X-Acteur-Id"


class Role(Enum):
    """Schéma Role de openapi.yaml ; le modèle n'expose le rôle que par UtilisateurSysteme.role."""

    User = "User"
    Admin = "Admin"


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


def exigerRole(acteur: UtilisateurSysteme, role: Role) -> None:
    """403 si l'acteur n'a pas le rôle exigé par le chemin ou par l'action demandée."""
    if acteur.role != role.name:
        raise AccesRefuseException(f"{acteur.name} n'a pas le rôle {role.name} : action refusée")


def exigerActeurDuChemin(acteur: UtilisateurSysteme, acteurId: int) -> None:
    """403 si l'acteur de l'en-tête n'est pas celui que nomme /acteur/{acteurId}/..."""
    if acteur.id != acteurId:
        raise AccesRefuseException(f"{acteur.name} ne peut pas agir au nom de l'acteur {acteurId}")


def userDesigne(systeme: SystemeTickets, acteurId: int) -> User:
    """Le User à qui assigner un ticket : 404 s'il est inconnu, 400 si c'est un Admin.

    L'appelant tient le verrou du contexte.
    """
    acteur = systeme.utilisateurParId(acteurId)
    if acteur is None:
        raise RessourceIntrouvable(f"Acteur introuvable : {acteurId}")
    if acteur.role != Role.User.name:
        raise RequeteInvalide(f"L'acteur {acteurId} n'est pas un User : assignation impossible")
    return cast("User", acteur)
