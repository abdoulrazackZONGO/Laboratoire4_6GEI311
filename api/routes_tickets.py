"""Routes des tickets. Partie lecture : la liste filtrée, le détail, les commentaires, la description.

Chaque route identifie l'acteur, vérifie ses paramètres, puis lit le système sous le
verrou, conversion en JSON comprise : un autre fil pourrait sinon modifier le ticket
pendant qu'on le lit.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, cast

from flask import Blueprint, jsonify

from api import representations
from api.contexte import contexteCourant
from api.erreurs import RessourceIntrouvable
from api.identification import acteurCourant
from api.validation import enumParNom, lireParametres, parametreEntier
from modele.enums import Statut

if TYPE_CHECKING:
    from acteurs.user import User
    from modele.systeme_tickets import SystemeTickets
    from modele.ticket import Ticket

blueprint = Blueprint("tickets", __name__)


@blueprint.get("/tickets")
def listerTickets():
    """Résumés triés par identifiant ; les filtres se combinent (ET).

    Un créateur ou un assigné inconnu donne une liste vide, pas une erreur.
    """
    acteurCourant()
    parametres = lireParametres(["statut", "createur", "assigne"])
    statut = enumParNom(parametres, "statut", Statut) if "statut" in parametres else None
    createurId = parametreEntier(parametres, "createur") if "createur" in parametres else None
    assigneId = parametreEntier(parametres, "assigne") if "assigne" in parametres else None
    contexte = contexteCourant()
    with contexte.verrou:
        systeme = contexte.systeme
        tickets = systeme.tickets
        if createurId is not None:
            tickets = _garder(tickets, _ticketsDe(systeme, createurId))
        if assigneId is not None:
            tickets = _garder(tickets, _ticketsAssignesA(systeme, assigneId))
        if statut is not None:
            tickets = [t for t in tickets if t.status is statut]
        tickets.sort(key=lambda t: t.ticketID)
        return jsonify([representations.ticketResume(t) for t in tickets])


@blueprint.get("/ticket/<int:ticketId>")
def lireTicket(ticketId: int):
    acteurCourant()
    contexte = contexteCourant()
    with contexte.verrou:
        return jsonify(representations.ticketDetail(_ticket(contexte.systeme, ticketId)))


@blueprint.get("/ticket/<int:ticketId>/commentaires")
def listerCommentaires(ticketId: int):
    acteurCourant()
    contexte = contexteCourant()
    with contexte.verrou:
        ticket = _ticket(contexte.systeme, ticketId)
        return jsonify([representations.commentaire(c) for c in ticket.comments])


@blueprint.get("/ticket/<int:ticketId>/description")
def lireDescription(ticketId: int):
    acteurCourant()
    contexte = contexteCourant()
    with contexte.verrou:
        ticket = _ticket(contexte.systeme, ticketId)
        return jsonify([
            representations.elementDescription(e, ticket.ticketID)
            for e in ticket.description.elements
        ])


# ------------------------------------------------------------------ recherche

def _ticket(systeme: SystemeTickets, ticketId: int) -> Ticket:
    ticket = systeme.ticketParId(ticketId)
    if ticket is None:
        raise RessourceIntrouvable(f"Ticket introuvable : {ticketId}")
    return ticket


def _ticketsDe(systeme: SystemeTickets, acteurId: int) -> list[Ticket]:
    """SystemeTickets.ticketsDe() ; un Admin n'a jamais créé de ticket, la liste est vide."""
    acteur = systeme.utilisateurParId(acteurId)
    return [] if acteur is None else systeme.ticketsDe(cast("User", acteur))


def _ticketsAssignesA(systeme: SystemeTickets, acteurId: int) -> list[Ticket]:
    """SystemeTickets.ticketsAssignesA() ; TERMINE et FERME compris (assigné conservé)."""
    acteur = systeme.utilisateurParId(acteurId)
    return [] if acteur is None else systeme.ticketsAssignesA(cast("User", acteur))


def _garder(tickets: list[Ticket], retenus: list[Ticket]) -> list[Ticket]:
    """Intersection par identité : Ticket ne définit pas __eq__."""
    return [t for t in tickets if any(t is r for r in retenus)]
