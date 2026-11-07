"""Routes des brouillons : créer ou éditer un ticket en plusieurs requêtes.

Un brouillon est une session du modèle : ces routes ne font que la retrouver et l'appeler.
Une pause, un undo ou un ajout refusés le sont par la session, qui lève son exception. Rien
ne change dans le dépôt avant l'application : c'est la seule opération qui sauvegarde.

Ces routes reprennent côté serveur ce que ControleurEdition faisait côté GUI, en particulier
le ménage des copies d'images devenues inutiles.
"""
from __future__ import annotations

import base64
import binascii
import sys
from enum import Enum
from typing import TYPE_CHECKING, Any, cast

from flask import Blueprint, jsonify

from api import representations
from api.contexte import contexteCourant
from api.erreurs import RequeteInvalide, RequeteTropVolumineuse, RessourceIntrouvable
from api.identification import Role, acteurCourant, exigerActeurDuChemin, exigerRole
from api.routes_tickets import ticketExistant
from api.validation import (
    booleen,
    chaine,
    chaineNonVide,
    entier,
    enumParNom,
    lireCorps,
    lireCorpsFacultatif,
    verifierChamps,
)
from modele.enums import Priorite
from modele.ticket import Ticket

if TYPE_CHECKING:
    from collections.abc import Callable

    from acteurs.user import User
    from api.contexte import ContexteServeur
    from api.registre_brouillons import EntreeBrouillon

blueprint = Blueprint("brouillons", __name__)

# Une fois décodée. En base64, elle tient sous la limite du corps (8 Mo, voir api/__init__.py).
TAILLE_MAXIMALE_IMAGE = 5 * 1024 * 1024


class TypeBrouillon(Enum):
    """Champ type du schéma OuvertureBrouillon de openapi.yaml."""

    creation = "creation"
    edition = "edition"


class TypeModification(Enum):
    """Champ type du schéma NouvelleModification de openapi.yaml."""

    commentaire = "commentaire"
    texte = "texte"
    image = "image"


@blueprint.get("/acteur/<int:acteurId>/brouillons")
def listerBrouillons(acteurId: int):
    _userDuChemin(acteurId)
    contexte = contexteCourant()
    with contexte.verrou:
        entrees = contexte.brouillons.brouillonsDe(acteurId)
        return jsonify([representations.brouillon(entree) for entree in entrees])


@blueprint.post("/acteur/<int:acteurId>/brouillons")
def ouvrirBrouillon(acteurId: int):
    """Création : le ticket reste hors du dépôt jusqu'à l'application. Édition : le modèle
    refuse un autre que le créateur (403) et une deuxième session sur le ticket (409)."""
    user = _userDuChemin(acteurId)
    corps = lireCorps()
    if enumParNom(corps, "type", TypeBrouillon) is TypeBrouillon.creation:
        entree = _ouvrirCreation(corps, user)
    else:
        entree = _ouvrirEdition(corps, user)
    with contexteCourant().verrou:
        return (
            jsonify(representations.brouillon(entree)),
            201,
            {"Location": f"/acteur/{acteurId}/brouillon/{entree.id}"},
        )


def _ouvrirCreation(corps: dict[str, Any], user: User) -> EntreeBrouillon:
    verifierChamps(corps, ["type", "titre", "priorite"])
    # Le titre perd ses espaces de bord, comme dans la GUI et dans POST /tickets.
    titre = chaineNonVide(corps, "titre").strip()
    priorite = enumParNom(corps, "priorite", Priorite)
    contexte = contexteCourant()
    with contexte.verrou:
        ticket = Ticket(contexte.systeme.reserverIdentifiant(), titre, priorite)
        session = user.ouvrirSessionCreation(ticket)
        return contexte.brouillons.ouvrir(session, user, estCreation=True)


def _ouvrirEdition(corps: dict[str, Any], user: User) -> EntreeBrouillon:
    verifierChamps(corps, ["type", "ticketId"])
    ticketId = entier(corps, "ticketId")
    contexte = contexteCourant()
    with contexte.verrou:
        session = user.ouvrirSessionEdition(ticketExistant(contexte.systeme, ticketId))
        return contexte.brouillons.ouvrir(session, user, estCreation=False)


@blueprint.get("/acteur/<int:acteurId>/brouillon/<int:brouillonId>")
def lireBrouillon(acteurId: int, brouillonId: int):
    _userDuChemin(acteurId)
    contexte = contexteCourant()
    with contexte.verrou:
        return jsonify(representations.brouillon(_brouillon(contexte, acteurId, brouillonId)))


@blueprint.patch("/acteur/<int:acteurId>/brouillon/<int:brouillonId>")
def modifierBrouillon(acteurId: int, brouillonId: int):
    """Le texte est gardé d'abord, puis la pause est appliquée (ordre du contrat)."""
    _userDuChemin(acteurId)
    corps = lireCorps()
    verifierChamps(corps, [], ["enPause", "texteBrouillon"])
    if not corps:
        raise RequeteInvalide("Champ obligatoire manquant : enPause ou texteBrouillon")
    enPause = booleen(corps, "enPause") if "enPause" in corps else None
    texte = chaine(corps, "texteBrouillon") if "texteBrouillon" in corps else None
    contexte = contexteCourant()
    with contexte.verrou:
        entree = _brouillon(contexte, acteurId, brouillonId)
        if texte is not None:
            entree.garderTexte(texte)
        if enPause is True:
            entree.session.mettreEnPause()
        elif enPause is False:
            entree.session.reprendre()
        return jsonify(representations.brouillon(entree))


@blueprint.delete("/acteur/<int:acteurId>/brouillon/<int:brouillonId>")
def abandonnerBrouillon(acteurId: int, brouillonId: int):
    """Le ticket reste inchangé, ou n'est pas créé ; les copies d'images deviennent inutiles."""
    _userDuChemin(acteurId)
    contexte = contexteCourant()
    with contexte.verrou:
        entree = _brouillon(contexte, acteurId, brouillonId)
        entree.session.abandonner()
        for copie in entree.viderCopies():
            _supprimerCopie(contexte, copie)
    return "", 204


@blueprint.get("/acteur/<int:acteurId>/brouillon/<int:brouillonId>/modifications")
def listerModifications(acteurId: int, brouillonId: int):
    _userDuChemin(acteurId)
    contexte = contexteCourant()
    with contexte.verrou:
        return jsonify(_brouillon(contexte, acteurId, brouillonId).session.modificationsEnAttente)


@blueprint.post("/acteur/<int:acteurId>/brouillon/<int:brouillonId>/modifications")
def ajouterModification(acteurId: int, brouillonId: int):
    _userDuChemin(acteurId)
    ajouter = _lireModification(lireCorps())
    contexte = contexteCourant()
    with contexte.verrou:
        entree = _brouillon(contexte, acteurId, brouillonId)
        ajouter(contexte, entree)
        return jsonify(representations.brouillon(entree)), 201


def _lireModification(corps: dict[str, Any]) -> Callable[[ContexteServeur, EntreeBrouillon], None]:
    """Vérifie le format du corps et rend l'ajout à exécuter ensuite, sous le verrou.

    L'image se décode ici, hors du verrou : une grosse image ne bloque pas les autres requêtes.
    """
    typeModification = enumParNom(corps, "type", TypeModification)
    if typeModification is TypeModification.image:
        verifierChamps(corps, ["type", "nomFichier", "contenuBase64"])
        nomFichier = chaine(corps, "nomFichier")
        octets = _decoderImage(chaineNonVide(corps, "contenuBase64"))

        def ajouterImage(contexte: ContexteServeur, entree: EntreeBrouillon) -> None:
            _ajouterImage(contexte, entree, nomFichier, octets)

        return ajouterImage

    verifierChamps(corps, ["type", "texte"])
    if typeModification is TypeModification.commentaire:
        # Le modèle n'a pas de règle pour un commentaire vide : seule la GUI le bloquait.
        # C'est donc une erreur de format ici. Le texte vide, lui, est refusé par le modèle.
        commentaire = chaineNonVide(corps, "texte").strip()

        def ajouterCommentaire(_: ContexteServeur, entree: EntreeBrouillon) -> None:
            entree.session.ajouterCommentaire(commentaire)
            entree.empilerCopie(None)

        return ajouterCommentaire

    texte = chaine(corps, "texte").strip()

    def ajouterTexte(_: ContexteServeur, entree: EntreeBrouillon) -> None:
        entree.session.ajouterTexteSaisi(texte)
        entree.empilerCopie(None)

    return ajouterTexte


@blueprint.delete("/acteur/<int:acteurId>/brouillon/<int:brouillonId>/modification/derniere")
def annulerDerniereModification(acteurId: int, brouillonId: int):
    _userDuChemin(acteurId)
    contexte = contexteCourant()
    with contexte.verrou:
        entree = _brouillon(contexte, acteurId, brouillonId)
        libelle = entree.session.annulerDerniere()
        copie = entree.depilerCopie()
        if copie is not None:
            _supprimerCopie(contexte, copie)
        return jsonify({
            "libelleRetire": libelle,
            "brouillon": representations.brouillon(entree),
        })


@blueprint.post("/acteur/<int:acteurId>/brouillon/<int:brouillonId>/application")
def appliquerBrouillon(acteurId: int, brouillonId: int):
    """Applique au mieux : un refus figure dans le rapport. Le brouillon disparaît ensuite."""
    _userDuChemin(acteurId)
    corps = lireCorpsFacultatif()
    verifierChamps(corps, [], ["texte"])
    texte = chaine(corps, "texte").strip() if "texte" in corps else ""
    contexte = contexteCourant()
    with contexte.verrou:
        entree = _brouillon(contexte, acteurId, brouillonId)
        session = entree.session
        if texte:
            session.ajouterTexteSaisi(texte)
        try:
            rapport = session.appliquer()
        except Exception:
            # Le texte est retiré pour ne pas être ajouté deux fois au prochain essai.
            if texte:
                session.annulerDerniere()
            raise
        if entree.estCreation or rapport.nombreSucces > 0:
            contexte.sauvegarder()
        if entree.estCreation:
            ticketId = session.ticket.ticketID
            resultat = representations.rapport(rapport, session.libelle, ticketId)
            return jsonify(resultat), 201, {"Location": f"/ticket/{ticketId}"}
        return jsonify(representations.rapport(rapport, session.libelle))


# ------------------------------------------------------------------ accès et images


def _userDuChemin(acteurId: int) -> User:
    """Règles d'accès communes : 401, puis l'acteur du chemin, puis le rôle (403)."""
    acteur = acteurCourant()
    exigerActeurDuChemin(acteur, acteurId)
    exigerRole(acteur, Role.User)
    return cast("User", acteur)


def _brouillon(contexte: ContexteServeur, acteurId: int, brouillonId: int) -> EntreeBrouillon:
    entree = contexte.brouillons.trouver(acteurId, brouillonId)
    if entree is None:
        raise RessourceIntrouvable(f"Brouillon introuvable : {brouillonId}")
    return entree


def _decoderImage(contenuBase64: str) -> bytes:
    try:
        octets = base64.b64decode(contenuBase64, validate=True)
    except (binascii.Error, ValueError):
        raise RequeteInvalide("Le champ contenuBase64 n'est pas du base64 valide") from None
    if len(octets) > TAILLE_MAXIMALE_IMAGE:
        raise RequeteTropVolumineuse("Image trop volumineuse (5 Mo au plus)")
    return octets


def _ajouterImage(
    contexte: ContexteServeur, entree: EntreeBrouillon, nomFichier: str, octets: bytes
) -> None:
    """La copie doit exister pour que le modèle valide l'élément : s'il refuse, elle disparaît."""
    copie = contexte.stockage.enregistrer(nomFichier, octets)
    try:
        entree.session.ajouterElement("image", copie)
    except Exception:
        _supprimerCopie(contexte, copie)
        raise
    entree.empilerCopie(copie)


def _supprimerCopie(contexte: ContexteServeur, copie: str) -> None:
    """L'opération a déjà réussi : une copie qui résiste est signalée, sans la faire échouer."""
    try:
        contexte.stockage.supprimer(copie)
    except OSError as erreur:
        print(f"Copie d'image non supprimée : {erreur}", file=sys.stderr)
