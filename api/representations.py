"""Objets du modèle -> dictionnaires JSON de l'API, selon les schémas de openapi.yaml.

Distinct de DepotJSON : la sauvegarde garde tout (chemins disque compris) pour
recharger le système, alors que l'API expose ce dont un client a besoin, avec les
noms de champs du contrat. Les fonctions ne lisent que les propriétés publiques du
modèle et ne le modifient jamais ; l'appelant tient le verrou du contexte.
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import quote

from modele.enums import Statut

if TYPE_CHECKING:
    from acteurs.utilisateur_systeme import UtilisateurSysteme
    from description.description_texte import DescriptionTexte
    from description.element_description import ElementDescription
    from modele.commentaire import Commentaire
    from modele.ticket import Ticket
    from sessions.rapport_execution import RapportExecution

NOM_TEXTE_SAISI = "texte saisi"


def acteur(a: UtilisateurSysteme) -> dict[str, Any]:
    return {"id": a.id, "nom": a.name, "courriel": a.email, "role": a.role}


def referenceActeur(a: UtilisateurSysteme | None) -> dict[str, Any] | None:
    """Référence courte, dans un ticket ou un commentaire ; None si personne."""
    if a is None:
        return None
    return {"id": a.id, "nom": a.name}


def commentaire(c: Commentaire) -> dict[str, Any]:
    return {"texte": c.texte, "auteur": referenceActeur(c.auteur), "date": c.date.isoformat()}


def elementDescription(e: ElementDescription, ticketId: int) -> dict[str, Any]:
    """Les champs dépendent du type : contenu pour les textes, url pour une image."""
    # Même règle que DepotJSON._elementVersDict(), sans isinstance : le texte saisi
    # partage le type "texte" mais n'a pas de chemin (seule la fabrique connaît les
    # sous-classes concrètes).
    if e.typeArtefact == "texte" and not e.chemin:
        return {
            "type": "texte_saisi",
            "nom": NOM_TEXTE_SAISI,
            "resume": e.resume,
            "contenu": cast("DescriptionTexte", e).contenu,
        }
    nom = os.path.basename(e.chemin)
    representation: dict[str, Any] = {"type": e.typeArtefact, "nom": nom, "resume": e.resume}
    if e.typeArtefact == "texte":
        representation["contenu"] = cast("DescriptionTexte", e).contenu
    elif e.typeArtefact == "image":
        # Le chemin disque n'est jamais exposé : seulement l'URI qui sert l'image.
        representation["url"] = f"/ticket/{ticketId}/image/{quote(nom)}"
    return representation


def transitionsPermises(t: Ticket) -> list[str]:
    """Dans l'ordre de l'enum Statut : Ticket.transitionsPermises est un ensemble."""
    return [statut.name for statut in Statut if statut in t.transitionsPermises]


def ticketResume(t: Ticket) -> dict[str, Any]:
    return {
        "id": t.ticketID,
        "titre": t.title,
        "priorite": t.priority.name,
        "statut": t.status.name,
        "createur": referenceActeur(t.creator),
        "assigne": referenceActeur(t.assignedUser),
        "dateCreation": t.creationDate.isoformat(),
        "dateMiseAJour": t.updateDate.isoformat(),
        "dejaAssigne": t.aDejaEteAssigne,
        "transitionsPermises": transitionsPermises(t),
        "nombreCommentaires": len(t.comments),
    }


def ticketDetail(t: Ticket) -> dict[str, Any]:
    detail = ticketResume(t)
    detail["commentaires"] = [commentaire(c) for c in t.comments]
    detail["description"] = [elementDescription(e, t.ticketID) for e in t.description.elements]
    return detail


def rapport(r: RapportExecution, libelle: str, ticketId: int | None = None) -> dict[str, Any]:
    """Un refus figure ici sans être une erreur HTTP ; le modèle ne porte ni libellé ni ticket."""
    return {
        "libelle": libelle,
        "succes": r.succes,
        "refus": [{"operation": operation, "motif": motif} for operation, motif in r.refus],
        "nombreSucces": r.nombreSucces,
        "nombreRefus": r.nombreRefus,
        "ticketId": ticketId,
    }
