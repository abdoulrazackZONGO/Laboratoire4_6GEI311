"""Routes des tickets : la liste filtrée, le détail, les commentaires, la description,
et l'écriture (création, changement de statut, suppression).

Chaque route identifie l'acteur, vérifie ses paramètres, puis travaille sous le verrou,
conversion en JSON comprise : un autre fil pourrait sinon modifier le ticket pendant
qu'on le lit. Une écriture appelle une méthode métier qui existe déjà : c'est elle qui
accepte ou lève une exception, jamais la route. La sauvegarde n'a lieu qu'après un succès.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from flask import Blueprint, Response, jsonify

from api import representations
from api.contexte import contexteCourant
from api.erreurs import RessourceIntrouvable
from api.identification import Role, acteurCourant, exigerRole, userDesigne
from api.validation import (
    assigneIdSelon,
    chaineNonVide,
    enumParNom,
    lireCorps,
    lireParametres,
    parametreEntier,
    verifierChamps,
)
from modele.enums import Priorite, Statut
from modele.ticket import Ticket

if TYPE_CHECKING:
    from collections.abc import Callable

    from acteurs.user import User
    from api.contexte import ContexteServeur
    from modele.systeme_tickets import SystemeTickets

blueprint = Blueprint("tickets", __name__)

# Les images de démonstration sont versionnées dans le dossier des copies : jamais supprimées.
# Une copie envoyée commence par un préfixe aléatoire, même si son original s'appelait demo_x.
PREFIXE_IMAGES_DEMO = "demo_"
TYPES_IMAGES: dict[str, str] = {".png": "image/png", ".gif": "image/gif"}

# Statut demandé -> rôle exigé et méthode métier (table de PATCH dans openapi.yaml).
# L'acteur a le rôle exigé quand l'action s'exécute, d'où Any pour son type.
_ACTIONS_STATUT: dict[Statut, tuple[Role, Callable[[Any, Ticket, Any], None]]] = {
    Statut.ASSIGNE: (Role.Admin, lambda admin, ticket, user: admin.assignTicket(ticket, user)),
    Statut.OUVERT: (Role.Admin, lambda admin, ticket, _: admin.desassignerTicket(ticket)),
    Statut.TERMINE: (Role.Admin, lambda admin, ticket, _: admin.validerTicket(ticket)),
    Statut.FERME: (Role.Admin, lambda admin, ticket, _: admin.closeTicket(ticket)),
    Statut.VALIDATION: (Role.User, lambda user, ticket, _: user.soumettreValidation(ticket)),
}


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
        return jsonify(representations.ticketDetail(ticketExistant(contexte.systeme, ticketId)))


@blueprint.get("/ticket/<int:ticketId>/commentaires")
def listerCommentaires(ticketId: int):
    acteurCourant()
    contexte = contexteCourant()
    with contexte.verrou:
        ticket = ticketExistant(contexte.systeme, ticketId)
        return jsonify([representations.commentaire(c) for c in ticket.comments])


@blueprint.get("/ticket/<int:ticketId>/description")
def lireDescription(ticketId: int):
    acteurCourant()
    contexte = contexteCourant()
    with contexte.verrou:
        ticket = ticketExistant(contexte.systeme, ticketId)
        return jsonify([
            representations.elementDescription(e, ticket.ticketID)
            for e in ticket.description.elements
        ])


@blueprint.get("/ticket/<int:ticketId>/image/<nomImage>")
def lireImage(ticketId: int, nomImage: str):
    """Sans acteur, pour qu'une balise <img> de la page web puisse l'afficher.

    Le nom reçu n'entre jamais dans un chemin de fichier : il ne sert qu'à choisir parmi les
    images de ce ticket. ../ ou le nom d'un autre fichier du serveur ne désignent donc rien.
    Le contenu n'est pas vérifié à l'envoi, seulement l'extension : nosniff interdit au
    navigateur de le prendre pour autre chose qu'une image.
    """
    contexte = contexteCourant()
    with contexte.verrou:
        ticket = ticketExistant(contexte.systeme, ticketId)
        chemin = _cheminImage(ticket, nomImage)
        try:
            # Lu ici et non par send_file() : le fichier ne reste pas ouvert après la réponse,
            # ce qui empêcherait sa suppression sous Windows.
            octets = Path(chemin).read_bytes()
        except FileNotFoundError:
            raise RessourceIntrouvable(f"Image introuvable : {nomImage}") from None
    reponse = Response(
        octets, mimetype=TYPES_IMAGES.get(Path(chemin).suffix.lower(), "application/octet-stream")
    )
    reponse.headers["X-Content-Type-Options"] = "nosniff"
    return reponse


@blueprint.post("/tickets")
def creerTicket():
    """Création en une requête : session de création, texte saisi, application.

    Le titre et le texte perdent leurs espaces de bord, comme dans la GUI : un ticket est
    le même quel que soit le client qui le crée.
    """
    acteur = acteurCourant()
    exigerRole(acteur, Role.User)
    corps = lireCorps()
    verifierChamps(corps, ["titre", "priorite", "texte"])
    titre = chaineNonVide(corps, "titre").strip()
    priorite = enumParNom(corps, "priorite", Priorite)
    texte = chaineNonVide(corps, "texte").strip()
    contexte = contexteCourant()
    with contexte.verrou:
        ticket = Ticket(contexte.systeme.reserverIdentifiant(), titre, priorite)
        session = cast("User", acteur).ouvrirSessionCreation(ticket)
        session.ajouterTexteSaisi(texte)
        rapport = session.appliquer()
        contexte.sauvegarder()
        resultat = {
            "ticket": representations.ticketDetail(ticket),
            "rapport": representations.rapport(rapport, session.libelle, ticket.ticketID),
        }
        return jsonify(resultat), 201, {"Location": f"/ticket/{ticket.ticketID}"}


@blueprint.patch("/ticket/<int:ticketId>")
def changerStatut(ticketId: int):
    """Le statut demandé désigne l'action ; l'état courant du ticket l'accepte ou la refuse.

    Le format passe avant le rôle, parce que le rôle exigé dépend du statut demandé.
    """
    acteur = acteurCourant()
    corps = lireCorps()
    verifierChamps(corps, ["statut"], ["assigneId"])
    statut = enumParNom(corps, "statut", Statut)
    assigneId = assigneIdSelon(corps, exige=statut is Statut.ASSIGNE)
    role, action = _ACTIONS_STATUT[statut]
    exigerRole(acteur, role)
    contexte = contexteCourant()
    with contexte.verrou:
        ticket = ticketExistant(contexte.systeme, ticketId)
        assigne = None if assigneId is None else userDesigne(contexte.systeme, assigneId)
        action(acteur, ticket, assigne)
        contexte.sauvegarder()
        return jsonify(representations.ticketDetail(ticket))


@blueprint.delete("/ticket/<int:ticketId>")
def supprimerTicket(ticketId: int):
    """User.supprimerTicket() décide (créateur, jamais assigné) ; la route range ensuite les images.

    Les images partent après la sauvegarde : si celle-ci échoue, le fichier JSON cite encore
    le ticket et ses images doivent rester, car un élément introuvable est ignoré au chargement.
    """
    acteur = acteurCourant()
    exigerRole(acteur, Role.User)
    contexte = contexteCourant()
    with contexte.verrou:
        ticket = ticketExistant(contexte.systeme, ticketId)
        cast("User", acteur).supprimerTicket(ticket)
        contexte.sauvegarder()
        _supprimerCopiesImages(contexte, ticket)
    return "", 204


def _supprimerCopiesImages(contexte: ContexteServeur, ticket: Ticket) -> None:
    """Supprime les images d'un ticket retiré du dépôt, sauf celles qu'il faut garder.

    Restent en place une image de démonstration et un fichier cité par un autre ticket.
    StockageImages.supprimer() ne touche de toute façon à rien hors de son dossier. Le
    ticket est déjà supprimé : un fichier qui résiste est signalé, sans faire échouer la requête.
    """
    citesAilleurs = {
        Path(element.chemin).resolve()
        for autre in contexte.systeme.tickets
        for element in autre.description.elements
        if element.chemin
    }
    for element in ticket.description.elements:
        if element.typeArtefact != "image":
            continue
        chemin = Path(element.chemin)
        if chemin.name.startswith(PREFIXE_IMAGES_DEMO) or chemin.resolve() in citesAilleurs:
            continue
        try:
            contexte.stockage.supprimer(element.chemin)
        except OSError as erreur:
            print(f"Image du ticket {ticket.ticketID} non supprimée : {erreur}", file=sys.stderr)


# ------------------------------------------------------------------ recherche

def ticketExistant(systeme: SystemeTickets, ticketId: int) -> Ticket:
    ticket = systeme.ticketParId(ticketId)
    if ticket is None:
        raise RessourceIntrouvable(f"Ticket introuvable : {ticketId}")
    return ticket


def _cheminImage(ticket: Ticket, nomImage: str) -> str:
    """Chemin de l'image de ce ticket qui porte ce nom, celui de son URL dans la description."""
    for element in ticket.description.elements:
        if element.typeArtefact == "image" and os.path.basename(element.chemin) == nomImage:
            return element.chemin
    raise RessourceIntrouvable(f"Image introuvable : {nomImage}")


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
