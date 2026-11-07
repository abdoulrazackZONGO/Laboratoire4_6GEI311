"""Route des lots de l'Admin : une même action sur plusieurs tickets, appliquée au mieux.

Un refus figure dans le rapport et ne bloque pas les autres tickets : la réponse reste 200.
Mais une requête mal formée ou un ticket inconnu refuse tout le lot, avant toute modification.
"""
from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any, cast

from flask import Blueprint, jsonify

from api import representations
from api.contexte import contexteCourant
from api.identification import (
    Role,
    acteurCourant,
    exigerActeurDuChemin,
    exigerRole,
    userDesigne,
)
from api.routes_tickets import ticketExistant
from api.validation import assigneIdSelon, enumParNom, lireCorps, listeEntiers, verifierChamps

if TYPE_CHECKING:
    from collections.abc import Callable

    from acteurs.admin import Admin
    from modele.ticket import Ticket
    from sessions.lot_admin import LotAdmin

blueprint = Blueprint("lots", __name__)


class ActionLot(Enum):
    """Champ action du schéma Lot de openapi.yaml."""

    assigner = "assigner"
    desassigner = "desassigner"
    valider = "valider"
    fermer = "fermer"


# Action -> ajout de l'opération au lot ; assigne ne vaut quelque chose que pour assigner.
_AJOUTS: dict[ActionLot, Callable[[LotAdmin, Ticket, Any], None]] = {
    ActionLot.assigner: lambda lot, ticket, assigne: lot.assigner(ticket, assigne),
    ActionLot.desassigner: lambda lot, ticket, _: lot.desassigner(ticket),
    ActionLot.valider: lambda lot, ticket, _: lot.validerTicket(ticket),
    ActionLot.fermer: lambda lot, ticket, _: lot.fermer(ticket),
}


@blueprint.post("/acteur/<int:acteurId>/lots")
def appliquerLot(acteurId: int):
    acteur = acteurCourant()
    exigerActeurDuChemin(acteur, acteurId)
    exigerRole(acteur, Role.Admin)
    corps = lireCorps()
    verifierChamps(corps, ["action", "ticketIds"], ["assigneId"])
    action = enumParNom(corps, "action", ActionLot)
    ticketIds = listeEntiers(corps, "ticketIds")
    assigneId = assigneIdSelon(corps, exige=action is ActionLot.assigner)
    contexte = contexteCourant()
    with contexte.verrou:
        # Toutes les recherches d'abord : un identifiant inconnu ne laisse aucun lot à moitié fait.
        tickets = [ticketExistant(contexte.systeme, ticketId) for ticketId in ticketIds]
        assigne = None if assigneId is None else userDesigne(contexte.systeme, assigneId)
        lot = cast("Admin", acteur).ouvrirLot()
        for ticket in tickets:
            _AJOUTS[action](lot, ticket, assigne)
        rapport = lot.appliquer()
        if rapport.nombreSucces > 0:
            contexte.sauvegarder()
        return jsonify(representations.rapport(rapport, lot.libelle))
