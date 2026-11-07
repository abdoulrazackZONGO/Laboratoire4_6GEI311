"""Routes des acteurs : lecture seule, sans X-Acteur-Id (la connexion F1 en a besoin avant)."""
from __future__ import annotations

from enum import Enum

from flask import Blueprint, jsonify

from api import representations
from api.contexte import contexteCourant
from api.erreurs import RessourceIntrouvable
from api.validation import enumParNom, lireParametres

blueprint = Blueprint("acteurs", __name__)


class Role(Enum):
    """Schéma Role de openapi.yaml ; le modèle n'expose le rôle que par UtilisateurSysteme.role."""

    User = "User"
    Admin = "Admin"


@blueprint.get("/acteurs")
def listerActeurs():
    """Tous les acteurs, triés par identifiant ; ?role=User pour le choix d'un assigné (F7)."""
    parametres = lireParametres(["role"])
    role = enumParNom(parametres, "role", Role) if "role" in parametres else None
    contexte = contexteCourant()
    with contexte.verrou:
        acteurs = sorted(contexte.systeme.utilisateurs, key=lambda a: a.id)
        return jsonify([
            representations.acteur(a) for a in acteurs
            if role is None or a.role == role.name
        ])


@blueprint.get("/acteur/<int:acteurId>")
def lireActeur(acteurId: int):
    contexte = contexteCourant()
    with contexte.verrou:
        acteur = contexte.systeme.utilisateurParId(acteurId)
        if acteur is None:
            raise RessourceIntrouvable(f"Acteur introuvable : {acteurId}")
        return jsonify(representations.acteur(acteur))
